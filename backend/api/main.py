"""
api/main.py
-----------
FastAPI application with WebSocket debate streaming and REST helpers.

WebSocket protocol
~~~~~~~~~~~~~~~~~~
Client connects to ``/ws/debate`` and immediately sends a JSON payload
matching ``DebateStartRequest``.  The server then streams ``StreamEvent``
JSON objects in real-time until the debate concludes.

Message flow:

  Client → Server: { "topic": "...", "persona_id": "default", "max_rounds": 3 }
  Server → Client: { "event_type": "status",     "data": { "status": "running" } }
  Server → Client: { "event_type": "turn_start",  "role": "user_twin", "round_number": 1 }
  Server → Client: { "event_type": "token",       "role": "user_twin", "data": "I believe..." }
  ...                                                                    (many tokens)
  Server → Client: { "event_type": "turn_end",    "role": "user_twin", "round_number": 1 }
  ...                                                                    (challenger turns)
  Server → Client: { "event_type": "scores",      "data": { "winner": "...", ... } }
  Server → Client: { "event_type": "status",      "data": { "status": "completed" } }
  Connection closes.

Concede signal
~~~~~~~~~~~~~~
The client can send ``{ "concede": true }`` at any point during the debate.
The server sets ``concede_signal = True`` in the state; the router will
route to the Judge at the next opportunity.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from engine import run_debate
from rag.memory import get_memory
from schemas import (
    DebateStartRequest,
    HealthResponse,
    IngestRequest,
    StreamEvent,
    StreamEventType,
)
from utils import get_logger, get_settings

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up ChromaDB + embedding model on startup."""
    logger.info("Warming up ChromaDB and embedding model…")
    memory = get_memory()  # triggers model load + collection init
    logger.info("Ready", chroma_docs=memory.collection_count())
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="GenAI Debate Twin",
    description="Multi-agent debate system powered by LangGraph and Claude.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Service health check — useful for Kubernetes liveness probes."""
    memory = get_memory()
    return HealthResponse(
        chroma_documents=memory.collection_count(),
        models={
            "twin": settings.twin_model,
            "challenger": settings.challenger_model,
            "judge": settings.judge_model,
        },
    )


@app.post("/ingest", status_code=201)
async def ingest_document(request: IngestRequest) -> dict:
    """
    Ingest a local file path into the persona vector store.

    For production, replace this with a multipart upload endpoint.
    """
    memory = get_memory()
    try:
        count = memory.ingest_file(request.file_path, persona_id=request.persona_id)
        return {"chunks_ingested": count, "persona_id": request.persona_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# WebSocket debate endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/debate")
async def debate_websocket(websocket: WebSocket) -> None:
    """
    Real-time debate streaming over WebSocket.

    1. Accept the connection.
    2. Read the initial ``DebateStartRequest`` JSON.
    3. Create a thread-safe queue to bridge the sync LangGraph callbacks
       with the async WebSocket send loop.
    4. Run the debate in the thread-pool executor; stream events to client.
    5. Handle concede signals sent by the client during the debate.
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    # --- Read initial request ---
    try:
        raw = await websocket.receive_json()
        request = DebateStartRequest(**raw)
    except Exception as exc:
        error_event = StreamEvent(
            event_type=StreamEventType.ERROR,
            data=f"Invalid start request: {exc}",
        )
        await websocket.send_text(error_event.to_json())
        await websocket.close()
        return

    logger.info("Debate starting", topic=request.topic[:60], persona=request.persona_id)

    # --- Shared concede flag (thread-safe via asyncio Event + threading.Event) ---
    concede_event = threading.Event()

    # --- Thread-safe event queue (sync producer → async consumer) ---
    event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def stream_callback(event: StreamEvent) -> None:
        """Called from the sync LangGraph thread; enqueues to async loop."""
        loop.call_soon_threadsafe(event_queue.put_nowait, event)

    # --- Kick off debate in background task ---
    async def run_debate_task() -> None:
        try:
            await run_debate(request, stream_callback, concede_event)
        except Exception as exc:
            stream_callback(
                StreamEvent(event_type=StreamEventType.ERROR, data=str(exc))
            )
        finally:
            # Sentinel to stop the send loop
            await event_queue.put(None)

    debate_task = asyncio.create_task(run_debate_task())

    # --- Listen for incoming client messages (concede) concurrently ---
    async def listen_for_client() -> None:
        try:
            while True:
                msg = await websocket.receive_json()
                if msg.get("concede"):
                    logger.info("Concede signal received")
                    concede_event.set()
        except WebSocketDisconnect:
            debate_task.cancel()
        except Exception:
            pass

    client_listener = asyncio.create_task(listen_for_client())

    # --- Stream events to client until sentinel ---
    try:
        while True:
            event = await event_queue.get()
            if event is None:  # Sentinel: debate finished
                break
            try:
                await websocket.send_text(event.to_json())
            except WebSocketDisconnect:
                logger.info("Client disconnected mid-debate")
                debate_task.cancel()
                break
    finally:
        client_listener.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("WebSocket closed")
