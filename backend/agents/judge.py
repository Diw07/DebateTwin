"""
agents/judge.py
---------------
Judge Node — evaluates the completed debate and produces a quantitative rubric.

Scoring methodology
~~~~~~~~~~~~~~~~~~~
The Judge receives the FULL debate transcript and scores each debater on:

  * ``logic_score``    (1-10) — structural validity of arguments, absence of fallacies.
  * ``evidence_score`` (1-10) — use of facts, data, citations, and grounded claims.
  * ``rebuttal_score`` (1-10) — quality of direct responses to opponent's arguments.

The Judge is prompted with a strict JSON-only response format.  We use a
two-pass approach:

  Pass 1 — ask Claude to reason step-by-step about each criterion (chain-of-thought).
  Pass 2 — ask Claude to emit ONLY the final JSON based on its reasoning.

This prevents JSON hallucination from short-circuiting the scoring logic.

Extension
~~~~~~~~~
Add new rubric dimensions (``rhetoric_score``, ``creativity_score``) by:
  1. Extending ``JudgeRubric`` in ``schemas/models.py``.
  2. Adding the new dimension to ``_SCORING_RUBRIC`` below.
"""

from __future__ import annotations

import json
import re

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from schemas import AgentRole, DebateState, JudgeRubric, StreamEvent, StreamEventType
from utils import get_logger, get_settings

logger = get_logger(__name__)
settings = get_settings()

_client = openai.OpenAI(
    api_key=settings.gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

_SCORING_RUBRIC = """
Score each debater on three dimensions (1 = very poor, 10 = exceptional):

1. LOGIC SCORE — Are arguments logically structured? Free of fallacies?
   Are claims connected with clear reasoning chains?

2. EVIDENCE SCORE — Are arguments grounded in specific facts, data, or
   documented examples? (The User Twin may reference personal context;
   the Challenger should use general knowledge.)

3. REBUTTAL SCORE — Does the debater directly address the opponent's
   strongest points? Do they neutralise counterarguments effectively?
"""

_JSON_SCHEMA_INSTRUCTION = """
Respond with ONLY a valid JSON object matching this exact schema.
No markdown. No preamble. No trailing text.

{
  "winner": "<user_twin | challenger>",
  "logic_score": <int 1-10>,
  "evidence_score": <int 1-10>,
  "rebuttal_score": <int 1-10>,
  "summary": "<2-3 sentence explanation of the result>"
}
"""


def _build_transcript(state: DebateState) -> str:
    """Format the full debate history as a readable transcript."""
    lines = [f"DEBATE TOPIC: {state.topic}\n"]
    for turn in state.history:
        speaker = "USER TWIN" if turn.role == AgentRole.USER_TWIN else "CHALLENGER"
        lines.append(f"--- Round {turn.round_number} | {speaker} ---")
        lines.append(turn.content)
        lines.append("")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict:
    """
    Robustly extract a JSON object from Claude's response.

    Handles: bare JSON, JSON wrapped in ```json ... ```, stray whitespace.
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("` \n")

    # Find the first { ... } block
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in Judge response: {raw[:300]}")

    return json.loads(match.group())


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def judge_node(state: dict) -> dict:
    """
    LangGraph node: Judge.

    Two-pass evaluation:
      Pass 1 → chain-of-thought reasoning (streamed to frontend as analysis).
      Pass 2 → structured JSON scores (emitted as SCORES event).
    """
    debate = DebateState(**state)
    callback = state.get("stream_callback")

    logger.info("Judge node firing", total_turns=len(debate.history))

    transcript = _build_transcript(debate)

    if callback:
        callback(
            StreamEvent(
                event_type=StreamEventType.TURN_START,
                role=AgentRole.JUDGE,
                round_number=debate.current_round,
            )
        )

    # ------------------------------------------------------------------
    # Pass 1: Chain-of-thought analysis (streamed)
    # ------------------------------------------------------------------
    analysis_prompt = f"""{transcript}

You are an impartial expert debate judge. Analyse the debate above.
{_SCORING_RUBRIC}

Think step-by-step about each criterion for BOTH debaters before scoring.
Do NOT produce JSON yet — just your analysis.
"""

    cot_response = ""
    try:
        stream = _client.chat.completions.create(
            model=settings.judge_model,
            max_tokens=800,
            messages=[{"role": "user", "content": analysis_prompt}],
            stream=True,
        )
        for chunk in stream:
            text_chunk = chunk.choices[0].delta.content or ""
            if text_chunk:
                cot_response += text_chunk
                if callback:
                    callback(
                        StreamEvent(
                            event_type=StreamEventType.TOKEN,
                            role=AgentRole.JUDGE,
                            round_number=debate.current_round,
                            data=text_chunk,
                        )
                    )
    except openai.APIError as exc:
        logger.error("OpenAI API error in Judge (Pass 1)", error=str(exc))
        raise

    # ------------------------------------------------------------------
    # Pass 2: Structured JSON output
    # ------------------------------------------------------------------
    scoring_prompt = f"""{cot_response}

Based on your analysis above:
{_JSON_SCHEMA_INSTRUCTION}
"""

    try:
        score_message = _client.chat.completions.create(
            model=settings.judge_model,
            max_tokens=800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "user", "content": analysis_prompt},
                {"role": "assistant", "content": cot_response},
                {"role": "user", "content": scoring_prompt},
            ],
        )
        raw_json = score_message.choices[0].message.content or ""
        score_dict = _extract_json(raw_json)

        # Validate via Pydantic
        rubric = JudgeRubric(**score_dict)
        logger.info(
            "Judge scored debate",
            winner=rubric.winner,
            total=rubric.total_score,
        )
    except (openai.APIError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Judge scoring failed", error=str(exc))
        # Fallback rubric — never crash the debate
        rubric = JudgeRubric(
            winner=AgentRole.USER_TWIN,
            logic_score=5,
            evidence_score=5,
            rebuttal_score=5,
            summary="Scoring failed due to a technical error. Scores are defaults.",
        )

    # Emit scores event to frontend
    if callback:
        callback(
            StreamEvent(
                event_type=StreamEventType.TURN_END,
                role=AgentRole.JUDGE,
                round_number=debate.current_round,
                data=rubric.model_dump(),
            )
        )
        callback(
            StreamEvent(
                event_type=StreamEventType.SCORES,
                data=rubric.model_dump(),
            )
        )

    return {
        **state,
        "scores": rubric,
        "stream_callback": callback,
    }
