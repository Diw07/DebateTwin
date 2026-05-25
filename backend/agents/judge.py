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
Score BOTH debaters on three dimensions (1 = very poor, 10 = exceptional):

1. LOGIC SCORE — Are arguments logically structured? Free of fallacies?
   Are claims connected with clear reasoning chains?

2. EVIDENCE SCORE — Are arguments grounded in specific facts, data, or
   documented examples? (The User Twin may reference personal context;
   the Challenger should use general knowledge.)

3. REBUTTAL SCORE — Does the debater directly address the opponent's
   strongest points? Do they neutralise counterarguments effectively?
"""

_JSON_SCHEMA_INSTRUCTION = """
Your final output MUST end with a valid JSON block enclosed in ```json ... ``` code fences.
Do NOT output anything else after the closing ```.

JSON Schema format:
{
  "winner": "user_twin" | "challenger",
  "twin_logic": <int 1-10>,
  "twin_evidence": <int 1-10>,
  "twin_rebuttal": <int 1-10>,
  "challenger_logic": <int 1-10>,
  "challenger_evidence": <int 1-10>,
  "challenger_rebuttal": <int 1-10>,
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
    Robustly extract the JSON object from the Judge's single-pass response.
    Handles JSON wrapped in ```json ... ``` code fences.
    """
    # Find the JSON block starting with ```json and ending with ```
    match = re.search(r"```json\s*(.*?)\s*```", raw, flags=re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # Fallback to finding the first { ... } block
        match_braces = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match_braces:
            json_str = match_braces.group(0).strip()
        else:
            raise ValueError(f"No JSON object found in response: {raw[:300]}")
    
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
def judge_node(state: dict) -> dict:
    """
    LangGraph node: Judge.

    Single-pass evaluation:
      - The judge is asked to write its step-by-step reasoning first (streamed to the frontend).
      - Then it appends a structured JSON block containing the final scores.
      - The tokens corresponding to the JSON block are suppressed from streaming to keep the UI clean.
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

    judge_prompt = f"""You are an impartial expert debate judge.
Evaluate the following debate topic and transcript.

{transcript}

SCORING CRITERIA:
{_SCORING_RUBRIC}

INSTRUCTIONS:
1. First, perform a detailed step-by-step evaluation of BOTH debaters (User Twin and Challenger) for each of the three scoring criteria (Logic, Evidence, Rebuttal).
   CRITICAL: Keep your evaluation for each debater extremely concise (maximum 1-2 sentences per debater per criterion). Do NOT write long paragraphs. This is essential to stay within output token limits.
2. After your concise evaluation, output a final structured JSON block containing the quantitative scores and winner decision. The JSON block MUST be enclosed in a ```json markdown block.

{_JSON_SCHEMA_INSTRUCTION}
"""

    full_response = ""
    in_json_block = False
    try:
        stream = _client.chat.completions.create(
            model=settings.judge_model,
            max_tokens=1500,
            messages=[{"role": "user", "content": judge_prompt}],
            stream=True,
        )
        for chunk in stream:
            text_chunk = chunk.choices[0].delta.content or ""
            if text_chunk:
                full_response += text_chunk
                
                # Once we encounter the json code fence, we stop streaming to frontend
                if "```json" in full_response and not in_json_block:
                    in_json_block = True
                
                if not in_json_block and callback:
                    callback(
                        StreamEvent(
                            event_type=StreamEventType.TOKEN,
                            role=AgentRole.JUDGE,
                            round_number=debate.current_round,
                            data=text_chunk,
                        )
                    )
    except Exception as exc:
        logger.error("API error in Judge during generation", error=str(exc))

    try:
        score_dict = _extract_json(full_response)

        # Validate via Pydantic
        rubric = JudgeRubric(**score_dict)
        logger.info(
            "Judge scored debate",
            winner=rubric.winner,
            twin_total=rubric.twin_total_score,
            challenger_total=rubric.challenger_total_score,
        )
    except (openai.APIError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Judge scoring failed", error=str(exc))
        # Fallback rubric — never crash the debate
        rubric = JudgeRubric(
            winner=AgentRole.USER_TWIN,
            twin_logic=5,
            twin_evidence=5,
            twin_rebuttal=5,
            challenger_logic=5,
            challenger_evidence=5,
            challenger_rebuttal=5,
            summary="Scoring failed due to a rate limit or technical error. Default scores applied.",
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

