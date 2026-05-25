"""
schemas/models.py
-----------------
Pydantic v2 data models for the GenAI Debate Twin system.

All inter-module data is validated through these schemas, giving us:
  - Runtime type safety across the FastAPI ↔ LangGraph boundary.
  - A single source of truth for the WebSocket message protocol.
  - Clear extension points: add new agent types by subclassing AgentTurn.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    USER_TWIN = "user_twin"
    CHALLENGER = "challenger"
    JUDGE = "judge"
    SYSTEM = "system"


class DebateStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    JUDGING = "judging"
    COMPLETED = "completed"
    ERROR = "error"


class StreamEventType(str, Enum):
    """WebSocket message types understood by the frontend."""
    TOKEN = "token"           # Streaming text chunk
    TURN_START = "turn_start" # Agent begins speaking
    TURN_END = "turn_end"     # Agent finishes
    SCORES = "scores"         # Judge emits final rubric
    STATUS = "status"         # Debate lifecycle event
    ERROR = "error"           # Fatal error


# ---------------------------------------------------------------------------
# Core debate data structures
# ---------------------------------------------------------------------------

class AgentTurn(BaseModel):
    """A single complete turn by one agent in the debate."""
    role: AgentRole
    round_number: int = Field(ge=1)
    content: str = Field(min_length=1)
    rag_sources: list[str] = Field(
        default_factory=list,
        description="Document chunk IDs used as context (Twin only).",
    )
    token_count: int | None = None


class JudgeRubric(BaseModel):
    """
    Structured output from the Judge Agent.

    Scores are integers 1–10. The winner field names the AgentRole
    whose cumulative performance was stronger across all rounds.
    """
    winner: AgentRole
    twin_logic: Annotated[int, Field(ge=1, le=10)]
    twin_evidence: Annotated[int, Field(ge=1, le=10)]
    twin_rebuttal: Annotated[int, Field(ge=1, le=10)]
    challenger_logic: Annotated[int, Field(ge=1, le=10)]
    challenger_evidence: Annotated[int, Field(ge=1, le=10)]
    challenger_rebuttal: Annotated[int, Field(ge=1, le=10)]
    summary: str = Field(min_length=20)

    @model_validator(mode="after")
    def compute_total(self) -> "JudgeRubric":
        # Expose totals
        object.__setattr__(
            self,
            "_twin_total",
            self.twin_logic + self.twin_evidence + self.twin_rebuttal,
        )
        object.__setattr__(
            self,
            "_challenger_total",
            self.challenger_logic + self.challenger_evidence + self.challenger_rebuttal,
        )
        return self

    @property
    def twin_total_score(self) -> int:
        return getattr(self, "_twin_total", 0)

    @property
    def challenger_total_score(self) -> int:
        return getattr(self, "_challenger_total", 0)



# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class DebateState(BaseModel):
    """
    Immutable snapshot of the debate at any graph node.

    LangGraph will pass this dict (serialised) between nodes.
    We use TypedDict-compatible field names so LangGraph can merge
    partial updates returned by each node.
    """
    model_config = {"arbitrary_types_allowed": True}

    topic: str
    persona_id: str = "default"
    history: list[AgentTurn] = Field(default_factory=list)
    current_round: int = 1
    max_rounds: int = 3
    status: DebateStatus = DebateStatus.PENDING
    scores: JudgeRubric | None = None
    concede_signal: bool = False
    concede_event: Any | None = Field(default=None, exclude=True)
    error_message: str | None = None

    # Streaming callback — not serialised, injected at runtime
    stream_callback: Any | None = Field(default=None, exclude=True)


# ---------------------------------------------------------------------------
# RAG / memory models
# ---------------------------------------------------------------------------

class DocumentChunk(BaseModel):
    """A text chunk stored in ChromaDB."""
    chunk_id: str
    persona_id: str
    text: str
    source_file: str
    chunk_index: int
    embedding_model: str


class RAGResult(BaseModel):
    """Result returned by the retrieval step."""
    chunks: list[DocumentChunk]
    query: str
    persona_id: str


class IngestRequest(BaseModel):
    persona_id: str = "default"
    # file content supplied as base64 or path; actual ingestion via CLI
    file_path: str


# ---------------------------------------------------------------------------
# WebSocket / API wire protocol
# ---------------------------------------------------------------------------

class StreamEvent(BaseModel):
    """
    Every message sent over the WebSocket follows this schema.

    The frontend discriminates on `event_type` and routes accordingly:
      - TOKEN → append to the current speaker's bubble
      - TURN_START / TURN_END → manage UI state
      - SCORES → render the Scoreboard sidebar
      - STATUS → show progress / completion banners
      - ERROR → display error toast
    """
    event_type: StreamEventType
    role: AgentRole | None = None
    round_number: int | None = None
    data: str | dict | None = None  # text for TOKEN; JudgeRubric dict for SCORES

    def to_json(self) -> str:
        return self.model_dump_json()


class DebateStartRequest(BaseModel):
    """Payload sent by the client to initiate a debate session."""
    topic: str = Field(min_length=10, max_length=500)
    persona_id: str = "default"
    max_rounds: int = Field(default=3, ge=1, le=5)

    @field_validator("topic")
    @classmethod
    def sanitize_topic(cls, v: str) -> str:
        return v.strip()


class HealthResponse(BaseModel):
    status: str = "ok"
    chroma_documents: int
    models: dict[str, str]
