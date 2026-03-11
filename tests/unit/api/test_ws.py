"""Unit tests for the WebSocket live telemetry endpoint and WebSocketManager.

Uses Starlette/FastAPI WebSocket TestClient.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ws import WebSocketManager
from api.routers.ws import router as ws_router


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(autouse=True)
def reset_manager() -> None:
    """Reset the WebSocketManager singleton between tests."""
    WebSocketManager.reset()


@pytest.fixture()
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(ws_router)
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ============================================================
# WebSocketManager unit tests
# ============================================================
class TestWebSocketManager:
    def test_singleton(self) -> None:
        m1 = WebSocketManager()
        m2 = WebSocketManager()
        assert m1 is m2

    def test_reset_creates_new_instance(self) -> None:
        m1 = WebSocketManager()
        WebSocketManager.reset()
        m2 = WebSocketManager()
        assert m1 is not m2

    def test_initial_client_count(self) -> None:
        mgr = WebSocketManager()
        assert mgr.client_count == 0


# ============================================================
# WebSocket endpoint tests
# ============================================================
class TestWebSocketLive:
    def test_connect_and_ping(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/live") as ws:
            # Send a ping message
            ws.send_text(json.dumps({"type": "ping"}))
            resp = ws.receive_text()
            data = json.loads(resp)
            assert data["type"] == "pong"

    def test_invalid_json_does_not_crash(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/live") as ws:
            # Send invalid JSON — should not crash the connection
            ws.send_text("not-json")
            # Send a valid ping after to verify connection is still alive
            ws.send_text(json.dumps({"type": "ping"}))
            resp = ws.receive_text()
            data = json.loads(resp)
            assert data["type"] == "pong"

    def test_non_ping_message_no_response(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/live") as ws:
            # Send a message that's not ping — should not respond
            ws.send_text(json.dumps({"type": "subscribe", "session_id": "abc"}))
            # Now send ping to verify we can still communicate
            ws.send_text(json.dumps({"type": "ping"}))
            resp = ws.receive_text()
            data = json.loads(resp)
            assert data["type"] == "pong"
