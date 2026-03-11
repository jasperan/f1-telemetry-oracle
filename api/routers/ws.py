"""WebSocket router — live telemetry broadcast to connected clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class WebSocketManager:
    """Singleton manager that tracks connected WebSocket clients and broadcasts frames."""

    _instance: WebSocketManager | None = None

    def __new__(cls) -> WebSocketManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._clients: list[WebSocket] = []
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (useful for tests)."""
        cls._instance = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection and add to clients list."""
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)
        logger.info("WebSocket client connected (%d total)", self.client_count)

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket client."""
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)
        logger.info("WebSocket client disconnected (%d remaining)", self.client_count)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients.

        Disconnected clients are cleaned up automatically.
        """
        message = json.dumps(data)
        dead: list[WebSocket] = []
        async with self._lock:
            for ws in self._clients:
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_text(message)
                    else:
                        dead.append(ws)
                except (WebSocketDisconnect, RuntimeError):
                    dead.append(ws)
            for ws in dead:
                if ws in self._clients:
                    self._clients.remove(ws)


# Module-level singleton
manager = WebSocketManager()


@router.websocket("/ws/live")
async def websocket_live(ws: WebSocket) -> None:
    """WebSocket endpoint for live telemetry streaming.

    Clients connect here to receive real-time telemetry frames.
    The broadcast is driven by the collector pipeline calling
    manager.broadcast() when new frames arrive.

    Clients can also send JSON messages to subscribe to specific
    sessions/drivers (future enhancement).
    """
    await manager.connect(ws)
    try:
        while True:
            # Keep the connection alive by waiting for client messages
            # Clients can send ping/subscribe messages
            data = await ws.receive_text()
            # For now, just acknowledge
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
