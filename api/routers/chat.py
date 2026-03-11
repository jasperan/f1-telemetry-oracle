"""Chat router -- AI Race Engineer REST + WebSocket endpoints.

Provides:
  POST /chat/message -- synchronous RAG-powered chat
  WS   /ws/chat      -- streaming chat via WebSocket

Both endpoints use the QueryUnderstanding -> ContextAssembler ->
ResponseGenerator pipeline backed by Ollama.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

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


class ChatResponse(BaseModel):
    """Response body for POST /chat/message."""

    response: str = Field(..., description="AI race engineer response")
    intent: str = Field(..., description="Detected query intent")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    sources: dict[str, int] = Field(
        default_factory=dict,
        description="Count of data sources used (sql, vector, graph)",
    )
    elapsed_ms: int = Field(..., description="Total processing time in milliseconds")


@router.post("/chat/message", response_model=ChatResponse)
async def chat_message(request: Request, body: ChatRequest):
    """Process a chat message through the RAG pipeline.

    Pipeline:
    1. QueryUnderstanding parses the question into intent + entities
    2. ContextAssembler retrieves data via SQL, vector search, graph
    3. ResponseGenerator produces a grounded answer via Ollama
    """
    start = time.monotonic()

    query_understanding = request.app.state.query_understanding
    context_assembler = request.app.state.context_assembler
    response_generator = request.app.state.response_generator

    # Step 1: Parse the question
    parsed = await query_understanding.parse(body.message)
    logger.info("Parsed intent=%s entities=%s", parsed.intent, parsed.entities)

    # Step 2: Retrieve context
    retrieval_results = await context_assembler.execute_retrieval(parsed)

    # Step 3: Assemble context
    context = await context_assembler.assemble(
        parsed,
        sql_results=retrieval_results.get("sql"),
        vector_results=retrieval_results.get("vector"),
        graph_results=retrieval_results.get("graph"),
    )

    # Step 4: Generate response
    response_text = await response_generator.generate(context, stream=False)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return ChatResponse(
        response=response_text,
        intent=parsed.intent,
        entities=parsed.entities,
        sources={
            "sql": len(retrieval_results.get("sql", [])),
            "vector": len(retrieval_results.get("vector", [])),
            "graph": len(retrieval_results.get("graph", [])),
        },
        elapsed_ms=elapsed_ms,
    )


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat responses.

    Client sends: {"message": "...", "session_id": "..."}
    Server sends:
      {"type": "intent", "intent": "...", "entities": {...}}
      {"type": "chunk", "content": "..."}  (repeated)
      {"type": "complete", "elapsed_ms": N, "sources": {...}}
    """
    await websocket.accept()
    app = websocket.app

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
                query_understanding = app.state.query_understanding
                context_assembler = app.state.context_assembler
                response_generator = app.state.response_generator

                # Parse
                parsed = await query_understanding.parse(question)
                await websocket.send_json({
                    "type": "intent",
                    "intent": parsed.intent,
                    "entities": parsed.entities,
                })

                # Retrieve + assemble
                retrieval_results = await context_assembler.execute_retrieval(parsed)
                context = await context_assembler.assemble(
                    parsed,
                    sql_results=retrieval_results.get("sql"),
                    vector_results=retrieval_results.get("vector"),
                    graph_results=retrieval_results.get("graph"),
                )

                # Generate -- try streaming, fall back to blocking
                try:
                    stream = await response_generator.generate(context, stream=True)
                    async for chunk in stream:
                        await websocket.send_json({"type": "chunk", "content": chunk})
                except (TypeError, AttributeError):
                    # Streaming not supported or mocked -- fall back
                    response_text = await response_generator.generate(context, stream=False)
                    await websocket.send_json({"type": "response", "content": response_text})

                elapsed_ms = int((time.monotonic() - start) * 1000)
                await websocket.send_json({
                    "type": "complete",
                    "elapsed_ms": elapsed_ms,
                    "sources": {
                        "sql": len(retrieval_results.get("sql", [])),
                        "vector": len(retrieval_results.get("vector", [])),
                        "graph": len(retrieval_results.get("graph", [])),
                    },
                })

            except Exception as exc:
                logger.error("Chat WebSocket error: %s", exc, exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {str(exc)}",
                })

    except WebSocketDisconnect:
        logger.info("Chat WebSocket client disconnected")
    except Exception:
        logger.info("Chat WebSocket connection closed")
