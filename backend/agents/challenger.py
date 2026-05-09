"""
agents/challenger.py
---------------------
Challenger Node — an adversarial debater that argues the opposing position.

Unlike the User Twin, the Challenger has NO access to RAG / personal context.
It relies entirely on the LLM's parametric knowledge plus the debate history
in its context window.  This intentional asymmetry:

* Tests how well the Twin's grounded evidence withstands general counterarguments.
* Avoids the Challenger "learning" about the user's persona and gaming it.

The Challenger is instructed to use Socratic questioning, steelmanning
its own position, and precise factual rebuttals.
"""

from __future__ import annotations

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

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

def _build_system_prompt(topic: str) -> str:
    return f"""You are the "Challenger" — a rigorous, intellectually aggressive AI debater.

DEBATE TOPIC: {topic}

Your role is to argue the OPPOSING side to whatever position the User Twin advocates.
Dynamically identify the Twin's stance from the conversation and counter it.

INSTRUCTIONS:
- Lead with your strongest factual or logical counterargument.
- Use one of: (a) a well-known study or statistic, (b) a logical fallacy identification,
  or (c) an economic / historical precedent.
- Keep arguments to 150–250 words. Dense, specific, and relentless.
- Do NOT agree with the User Twin at any point — steelman your own position.
- End with a sharp question or challenge that forces the Twin to justify their claim.
- Write in confident, academic prose. No hedging.
"""


def _build_conversation_messages(state: DebateState) -> list[dict]:
    """
    Map debate history to Anthropic messages.

    The Challenger sees itself as "assistant" and the Twin as "user".
    This reverses the Twin's mapping, giving each agent its own perspective
    without needing separate conversation objects.
    """
    messages = []
    for turn in state.history:
        if turn.role == AgentRole.CHALLENGER:
            role = "assistant"
        else:
            role = "user"
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
def challenger_node(state: dict) -> dict:
    """
    LangGraph node: Challenger.

    Reads the full debate history, formulates a counter-argument,
    and streams it to the frontend via the callback.
    """
    debate = DebateState(**state)
    callback = state.get("stream_callback")

    logger.info(
        "Challenger node firing",
        round=debate.current_round,
        history_turns=len(debate.history),
    )

    if callback:
        callback(
            StreamEvent(
                event_type=StreamEventType.TURN_START,
                role=AgentRole.CHALLENGER,
                round_number=debate.current_round,
            )
        )

    system_prompt = _build_system_prompt(debate.topic)
    messages = _build_conversation_messages(debate)

    # Challenger always responds to the Twin's most recent argument
    # If history is empty (shouldn't happen in normal flow), bootstrap it
    if not messages:
        messages = [
            {
                "role": "user",
                "content": f"Start the debate on: {debate.topic}",
            }
        ]

    full_response = ""
    try:
        stream = _client.chat.completions.create(
            model=settings.challenger_model,
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
                            role=AgentRole.CHALLENGER,
                            round_number=debate.current_round,
                            data=text_chunk,
                        )
                    )
    except openai.APIError as exc:
        logger.error("OpenAI API error in Challenger", error=str(exc))
        raise

    if callback:
        callback(
            StreamEvent(
                event_type=StreamEventType.TURN_END,
                role=AgentRole.CHALLENGER,
                round_number=debate.current_round,
            )
        )

    turn = AgentTurn(
        role=AgentRole.CHALLENGER,
        round_number=debate.current_round,
        content=full_response,
        rag_sources=[],
        token_count=len(full_response.split()),
    )

    logger.info("Challenger turn complete", words=turn.token_count)

    # After the Challenger responds, advance the round counter
    return {
        **state,
        "history": debate.history + [turn],
        "current_round": debate.current_round + 1,
        "stream_callback": callback,
    }
