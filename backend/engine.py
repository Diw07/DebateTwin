"""
engine.py
---------
LangGraph debate orchestration engine.

Graph topology
~~~~~~~~~~~~~~

    [START]
       │
       ▼
  ┌──────────────┐
  │  user_twin   │◄─────────────────────────────────────────┐
  └──────┬───────┘                                          │
         │                                                  │
         ▼                                                  │
  ┌──────────────┐                                          │
  │  challenger  │                                          │
  └──────┬───────┘                                          │
         │                                                  │
         ▼                                                  │
  ┌──────────────────────────────┐   continue               │
  │         router()             │──────────────────────────┘
  └──────────────────────────────┘
         │ end / concede
         ▼
  ┌──────────────┐
  │    judge     │
  └──────┬───────┘
         │
       [END]

Routing logic
~~~~~~~~~~~~~
After each Challenger turn the ``router`` function decides:
  * ``"judge"``    → max rounds reached OR concede_signal set.
  * ``"user_twin"``→ debate continues.

State merging
~~~~~~~~~~~~~
LangGraph merges partial dict returns from each node into the full state.
We return only the keys that changed — the graph handles the rest.

Extension
~~~~~~~~~
Add a "Moderator" node between Twin and Challenger for structured debate formats
(e.g., Oxford-style rebuttal + summary phases) by inserting it into the graph
and adjusting the router.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncGenerator
from typing import Any, Callable

from langgraph.graph import END, StateGraph

from agents.challenger import challenger_node
from agents.judge import judge_node
from agents.user_twin import user_twin_node
from schemas import (
    AgentRole,
    DebateStartRequest,
    DebateState,
    DebateStatus,
    StreamEvent,
    StreamEventType,
)
from utils import get_logger, get_settings

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def debate_router(state: dict) -> str:
    """
    Conditional edge function for LangGraph.

    Called after every ``challenger_node`` turn.  Returns the name of the
    next node to execute.

    Decision table
    ~~~~~~~~~~~~~~
    concede == True   → "judge"   (early termination)
    current_round > max_rounds → "judge" (natural end)
    otherwise                → "user_twin" (next round)
    """
    concede_event = state.get("concede_event")
    concede = concede_event.is_set() if concede_event else False
    current_round = state.get("current_round", 1)
    max_rounds = state.get("max_rounds", settings.max_debate_rounds)

    if concede or current_round > max_rounds:
        logger.info(
            "Router → judge",
            reason="concede" if concede else "max_rounds",
            round=current_round,
        )
        return "judge"

    logger.info("Router → user_twin", next_round=current_round)
    return "user_twin"


def twin_router(state: dict) -> str:
    """
    Conditional edge function after the User Twin node.
    Routes to the Judge immediately if the user conceded.
    """
    concede_event = state.get("concede_event")
    concede = concede_event.is_set() if concede_event else False
    if concede:
        logger.info("Twin Router → judge", reason="concede")
        return "judge"
    return "challenger"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_debate_graph() -> Any:
    """
    Construct and compile the LangGraph debate graph.

    Returns a compiled ``CompiledGraph`` ready to invoke or stream.
    The graph is stateless between invocations — all state lives in the
    ``DebateState`` dict passed to ``invoke`` / ``astream``.
    """
    builder = StateGraph(dict)  # dict state — Pydantic model serialises in/out

    # Register nodes
    builder.add_node("user_twin", user_twin_node)
    builder.add_node("challenger", challenger_node)
    builder.add_node("judge", judge_node)

    # Entry point
    builder.set_entry_point("user_twin")

    # Conditional routing after User Twin speaks
    builder.add_conditional_edges(
        "user_twin",
        twin_router,
        {
            "challenger": "challenger",
            "judge": "judge",
        },
    )

    # Conditional routing after Challenger speaks
    builder.add_conditional_edges(
        "challenger",
        debate_router,
        {
            "user_twin": "user_twin",
            "judge": "judge",
        },
    )

    # Judge always terminates
    builder.add_edge("judge", END)

    compiled = builder.compile()
    logger.info("Debate graph compiled")
    return compiled


# ---------------------------------------------------------------------------
# High-level async runner
# ---------------------------------------------------------------------------

async def run_debate(
    request: DebateStartRequest,
    stream_callback: Callable[[StreamEvent], None],
    concede_event: threading.Event | None = None,
) -> DebateState:
    """
    Run a full debate asynchronously.

    Parameters
    ----------
    request:         Validated ``DebateStartRequest`` from the WebSocket handler.
    stream_callback: Sync callback invoked with each ``StreamEvent``.  The
                     WebSocket handler wraps this to send JSON over the wire.

    Returns the final ``DebateState`` including scores.

    The graph runs synchronously inside a thread-pool executor so we don't
    block the async event loop during LLM calls.
    """
    graph = build_debate_graph()

    initial_state: dict = {
        "topic": request.topic,
        "persona_id": request.persona_id,
        "history": [],
        "current_round": 1,
        "max_rounds": request.max_rounds,
        "status": DebateStatus.RUNNING,
        "scores": None,
        "concede_event": concede_event,
        "error_message": None,
        "stream_callback": stream_callback,
    }

    # Emit status: debate starting
    stream_callback(
        StreamEvent(
            event_type=StreamEventType.STATUS,
            data={"status": DebateStatus.RUNNING, "topic": request.topic},
        )
    )

    try:
        # Run the synchronous LangGraph in a thread pool to keep the event loop free
        loop = asyncio.get_running_loop()
        final_state = await loop.run_in_executor(
            None,
            lambda: graph.invoke(initial_state),
        )
    except Exception as exc:
        logger.error("Debate graph error", error=str(exc))
        stream_callback(
            StreamEvent(
                event_type=StreamEventType.ERROR,
                data=str(exc),
            )
        )
        raise

    # Emit status: completed
    stream_callback(
        StreamEvent(
            event_type=StreamEventType.STATUS,
            data={"status": DebateStatus.COMPLETED},
        )
    )

    return DebateState(**{k: v for k, v in final_state.items() if k not in ("stream_callback", "concede_event")})
