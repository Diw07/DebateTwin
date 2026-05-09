"""
agents/user_twin.py
--------------------
User Twin Node — the RAG-grounded debater that represents the user.

Agentic design
~~~~~~~~~~~~~~
1. Retrieve relevant context from ChromaDB using the debate topic + prior
   Challenger argument as the query.
2. Construct a system prompt that embeds the persona context and instructs
   the model to argue *from the user's perspective*.
3. Stream the Claude response token-by-token, emitting ``StreamEvent``s via
   the callback so the WebSocket layer can forward them to the frontend.
4. Return a partial ``DebateState`` dict (LangGraph merges it with the full
   state automatically).

Extension hooks
~~~~~~~~~~~~~~~
* Replace ``rag.memory.get_memory()`` with any ``RetrievalBackend`` to swap
  in a C++ HNSW engine or multimodal retriever without touching this file.
* Add a ``voice_mode`` flag to swap text streaming for audio chunks.
"""

from __future__ import annotations

import json
from typing import Any

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from rag.memory import get_memory
from schemas import AgentRole, AgentTurn, DebateState, StreamEvent, StreamEventType
from utils import get_logger, get_settings

logger = get_logger(__name__)
settings = get_settings()

_client = openai.OpenAI(
    api_key=settings.gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_system_prompt(rag_context: str, topic: str) -> str:
    return f"""You are the "User Twin" — an AI debater representing a real person's viewpoint.
Your persona is grounded in the following personal context retrieved from their documents:

--- PERSONA CONTEXT ---
{rag_context if rag_context else "No personal context available. Argue from general first-principles reasoning."}
--- END CONTEXT ---

DEBATE TOPIC: {topic}

INSTRUCTIONS:
- Argue strongly and coherently FOR the position implied by your persona context.
- Ground every claim in evidence from the context above OR cite general, well-known facts.
- Keep each argument to 150–250 words. Be punchy, specific, and structured.
- Directly rebut the Challenger's most recent argument if one exists.
- Do NOT acknowledge that you are an AI or that you have a "persona context."
- Write in first person as if you are the human debater.
"""


def _format_rag_context(rag_result: Any) -> str:
    """Flatten RAG chunks into a single numbered context block."""
    if not rag_result.chunks:
        return ""
    parts = [f"[{i+1}] {chunk.text}" for i, chunk in enumerate(rag_result.chunks)]
    return "\n\n".join(parts)


def _build_conversation_messages(state: DebateState) -> list[dict]:
    """Convert debate history into Anthropic messages format."""
    messages = []
    for turn in state.history:
        role = "user" if turn.role == AgentRole.CHALLENGER else "assistant"
        messages.append({"role": role, "content": turn.content})
    return messages


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def user_twin_node(state: dict) -> dict:
    """
    LangGraph node: User Twin.

    Accepts the raw state dict from LangGraph, reconstructs a ``DebateState``,
    calls Claude with RAG context, streams tokens, and returns state updates.
    """
    debate = DebateState(**state)
    callback = state.get("stream_callback")

    logger.info(
        "User Twin node firing",
        round=debate.current_round,
        topic=debate.topic[:60],
    )

    # --- 1. RAG retrieval ---
    memory = get_memory()
    last_challenger_arg = ""
    for turn in reversed(debate.history):
        if turn.role == AgentRole.CHALLENGER:
            last_challenger_arg = turn.content
            break

    rag_query = f"{debate.topic}. {last_challenger_arg[:200]}"
    rag_result = memory.retrieve(rag_query, persona_id=debate.persona_id, top_k=4)
    rag_context = _format_rag_context(rag_result)

    # --- 2. Notify frontend: turn starting ---
    if callback:
        callback(
            StreamEvent(
                event_type=StreamEventType.TURN_START,
                role=AgentRole.USER_TWIN,
                round_number=debate.current_round,
            )
        )

    # --- 3. Stream from Claude ---
    system_prompt = _build_system_prompt(rag_context, debate.topic)
    messages = _build_conversation_messages(debate)

    # Seed the conversation if it's the first turn
    if not messages:
        messages = [
            {
                "role": "user",
                "content": f"Begin the debate. The topic is: {debate.topic}",
            }
        ]

    full_response = ""
    try:
        stream = _client.chat.completions.create(
            model=settings.twin_model,
            max_tokens=600,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            stream=True,
        )
        for chunk in stream:
            text_chunk = chunk.choices[0].delta.content or ""
            if text_chunk:
                full_response += text_chunk
                if callback:
                    callback(
                        StreamEvent(
                            event_type=StreamEventType.TOKEN,
                            role=AgentRole.USER_TWIN,
                            round_number=debate.current_round,
                            data=text_chunk,
                        )
                    )
    except openai.APIError as exc:
        logger.error("OpenAI API error in User Twin", error=str(exc))
        raise

    # --- 4. Notify frontend: turn complete ---
    if callback:
        callback(
            StreamEvent(
                event_type=StreamEventType.TURN_END,
                role=AgentRole.USER_TWIN,
                round_number=debate.current_round,
            )
        )

    # --- 5. Build turn record and return state delta ---
    turn = AgentTurn(
        role=AgentRole.USER_TWIN,
        round_number=debate.current_round,
        content=full_response,
        rag_sources=[c.chunk_id for c in rag_result.chunks],
        token_count=len(full_response.split()),
    )

    logger.info("User Twin turn complete", words=turn.token_count)

    return {
        **state,
        "history": debate.history + [turn],
        "stream_callback": callback,
    }
