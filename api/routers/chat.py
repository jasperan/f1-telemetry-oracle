"""Chat router — AI Race Engineer REST + WebSocket endpoints.

Provides:
  POST /chat/message -- chat with a retrieval trace
  WS   /ws/chat      -- streaming chat via WebSocket

Two pipelines:
  * Agentic (default): the LLM plans its own retrieval by calling
    database tools (see api/services/agent.py).
  * Classic RAG: QueryUnderstanding -> ContextAssembler -> ResponseGenerator
    (SQL + vector + graph + in-database document search).

The agentic path is tried first and falls back to classic RAG whenever
tool-calling is unavailable. Every response carries a ``trace`` object
so the frontend can show exactly what the database did.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from api.config import settings
from api.services.agent import AgenticError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for POST /chat/message."""

    message: str = Field(..., min_length=1, max_length=2000, description="User's question")
    session_id: str | None = Field(None, description="Optional session context for follow-ups")
    include_telemetry: bool = Field(True, description="Include telemetry data in context")

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be blank")
        return v.strip()


class RetrievalTrace(BaseModel):
    """Transparency record of how an answer was produced."""

    path: str = Field(..., description="'agent' (tool-calling) or 'rag' (classic pipeline)")
    intent: str | None = Field(None, description="Detected intent (rag path)")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    tool_calls: list[str] = Field(default_factory=list, description="Tools called (agent path)")
    iterations: int = Field(0, description="Agent loop iterations")
    sources: dict[str, int] = Field(
        default_factory=dict, description="Counts per data source (sql, vector, graph, docs, tools)"
    )
    stages_ms: dict[str, int] = Field(default_factory=dict, description="Per-stage latency in ms")


class ChatResponse(BaseModel):
    """Response body for POST /chat/message."""

    response: str = Field(..., description="AI race engineer response")
    intent: str = Field(..., description="Detected query intent")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    sources: dict[str, int] = Field(
        default_factory=dict,
        description="Count of data sources used (sql, vector, graph, docs)",
    )
    elapsed_ms: int = Field(..., description="Total processing time in milliseconds")
    trace: RetrievalTrace = Field(default_factory=dict, description="Retrieval transparency trace")


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------
async def _classic_turn(app, question: str) -> tuple[str, RetrievalTrace]:
    """Run the classic RAG pipeline; returns (response_text, trace)."""
    stages: dict[str, int] = {}

    start = time.monotonic()
    parsed = await app.state.query_understanding.parse(question)
    stages["parse_ms"] = int((time.monotonic() - start) * 1000)

    start = time.monotonic()
    retrieval = await app.state.context_assembler.execute_retrieval(parsed)
    stages["retrieve_ms"] = int((time.monotonic() - start) * 1000)

    start = time.monotonic()
    context = await app.state.context_assembler.assemble(
        parsed,
        sql_results=retrieval.get("sql"),
        vector_results=retrieval.get("vector"),
        graph_results=retrieval.get("graph"),
        docs_results=retrieval.get("docs"),
    )
    stages["assemble_ms"] = int((time.monotonic() - start) * 1000)

    start = time.monotonic()
    response_text = await app.state.response_generator.generate(context, stream=False)
    stages["generate_ms"] = int((time.monotonic() - start) * 1000)

    sources = {k: len(v) for k, v in retrieval.items() if isinstance(v, list)}

    trace = RetrievalTrace(
        path="rag",
        intent=parsed.intent,
        entities=parsed.entities,
        sources=sources,
        stages_ms=stages,
    )
    return response_text, trace


async def _agent_turn(app, question: str) -> tuple[str, RetrievalTrace]:
    """Run the agentic tool-calling pipeline; returns (response_text, trace)."""
    start = time.monotonic()
    result = await app.state.agent.run(question)
    elapsed = int((time.monotonic() - start) * 1000)

    trace = RetrievalTrace(
        path="agent",
        tool_calls=result.tool_calls,
        iterations=result.iterations,
        sources={"tools": len(result.tool_calls)},
        stages_ms={"agent_ms": elapsed},
    )
    return result.response, trace


async def _answer(app, question: str) -> tuple[str, RetrievalTrace]:
    """Agentic-first with classic RAG fallback."""
    agent = getattr(app.state, "agent", None)
    if settings.agentic_chat and agent is not None:
        try:
            return await _agent_turn(app, question)
        except AgenticError as exc:
            logger.info("Agentic path unavailable (%s); falling back to RAG", exc)
    return await _classic_turn(app, question)


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------
@router.post("/chat/message", response_model=ChatResponse)
async def chat_message(request: Request, body: ChatRequest):
    """Process a chat message through the AI race engineer pipeline."""
    start = time.monotonic()
    response_text, trace = await _answer(request.app, body.message)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    return ChatResponse(
        response=response_text,
        intent=trace.intent or "agent",
        entities=trace.entities,
        sources=trace.sources,
        elapsed_ms=elapsed_ms,
        trace=trace,
    )


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat responses.

    Client sends: {"message": "..."}
    Server sends:
      {"type": "intent", "intent": "...", "entities": {...}}
      {"type": "chunk", "content": "..."}  (classic RAG streaming)
      {"type": "response", "content": "..."}  (agentic, full response)
      {"type": "complete", "elapsed_ms": N, "sources": {...}, "trace": {...}}
    """
    await websocket.accept()
    app = websocket.scope["app"]

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            question = msg.get("message", "").strip()
            if not question:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue

            start = time.monotonic()

            try:
                agent = getattr(app.state, "agent", None)
                if settings.agentic_chat and agent is not None:
                    try:
                        response_text, trace = await _agent_turn(app, question)
                        await websocket.send_json({"type": "response", "content": response_text})
                    except AgenticError as exc:
                        logger.info("Agentic path unavailable (%s); falling back to RAG", exc)
                        await _classic_ws_stream(app, websocket, question)
                        continue
                else:
                    await _classic_ws_stream(app, websocket, question)
                    continue

                elapsed_ms = int((time.monotonic() - start) * 1000)
                await websocket.send_json({
                    "type": "complete",
                    "elapsed_ms": elapsed_ms,
                    "sources": trace.sources,
                    "trace": trace.model_dump(),
                })

            except Exception as exc:
                logger.error("Chat WebSocket error: %s", exc, exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {exc!s}",
                })

    except WebSocketDisconnect:
        logger.info("Chat WebSocket client disconnected")
    except Exception:
        logger.info("Chat WebSocket connection closed")


async def _classic_ws_stream(app, websocket: WebSocket, question: str) -> None:
    """Stream a classic RAG answer, sending intent/chunk/complete events."""
    parsed = await app.state.query_understanding.parse(question)
    await websocket.send_json({
        "type": "intent",
        "intent": parsed.intent,
        "entities": parsed.entities,
    })

    retrieval = await app.state.context_assembler.execute_retrieval(parsed)
    context = await app.state.context_assembler.assemble(
        parsed,
        sql_results=retrieval.get("sql"),
        vector_results=retrieval.get("vector"),
        graph_results=retrieval.get("graph"),
        docs_results=retrieval.get("docs"),
    )

    # Streaming generation with fallback to blocking
    try:
        stream = await app.state.response_generator.generate(context, stream=True)
        async for chunk in stream:
            await websocket.send_json({"type": "chunk", "content": chunk})
    except (TypeError, AttributeError):
        response_text = await app.state.response_generator.generate(context, stream=False)
        await websocket.send_json({"type": "response", "content": response_text})

    sources = {k: len(v) for k, v in retrieval.items() if isinstance(v, list)}
    await websocket.send_json({
        "type": "complete",
        "elapsed_ms": 0,
        "sources": sources,
        "trace": {
            "path": "rag",
            "intent": parsed.intent,
            "entities": parsed.entities,
            "sources": sources,
        },
    })
