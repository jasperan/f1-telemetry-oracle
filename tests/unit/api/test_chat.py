"""Tests for the Ollama client and chat router.

Verifies:
- OllamaClient wraps native /api/chat correctly with think=false
- Chat router POST /chat/message returns grounded response
- WebSocket /ws/chat streams response chunks
- Error handling for Ollama unavailability
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from api.services.ollama import OllamaClient


class TestOllamaClient:
    """Test the native Ollama API client."""

    @pytest.mark.asyncio
    async def test_chat_sends_think_false(self):
        """Ollama client must send think: false to suppress reasoning tokens."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "Box box box, pit this lap."},
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            client = OllamaClient(base_url="http://localhost:11434")
            result = await client.chat(
                model="qwen3.5:35b-a3b",
                messages=[{"role": "user", "content": "When should I pit?"}],
            )

            assert result["message"]["content"] == "Box box box, pit this lap."

            call_kwargs = mock_post.call_args
            body = call_kwargs.kwargs.get("json", {})
            assert body.get("think") is False, "Must send think: false"

    @pytest.mark.asyncio
    async def test_chat_with_options(self):
        """Options like temperature should be passed through."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "Response"},
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            client = OllamaClient(base_url="http://localhost:11434")
            result = await client.chat(
                model="qwen3.5:35b-a3b",
                messages=[{"role": "user", "content": "test"}],
                options={"temperature": 0.0},
            )
            assert result["message"]["content"] == "Response"

            call_kwargs = mock_post.call_args
            body = call_kwargs.kwargs.get("json", {})
            assert body.get("options", {}).get("temperature") == 0.0

    @pytest.mark.asyncio
    async def test_chat_raises_on_error(self):
        """Should raise on non-200 responses."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            client = OllamaClient(base_url="http://localhost:11434")
            with pytest.raises(Exception):
                await client.chat(
                    model="qwen3.5:35b-a3b",
                    messages=[{"role": "user", "content": "test"}],
                )


class TestChatRouter:
    """Test the chat REST and WebSocket endpoints."""

    @pytest.fixture
    def app(self):
        from api.routers.chat import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        # Mock dependencies
        app.state.oracle_pool = AsyncMock()
        app.state.ollama_client = AsyncMock()
        app.state.query_understanding = AsyncMock()
        app.state.context_assembler = AsyncMock()
        app.state.response_generator = AsyncMock()

        return app

    @pytest.mark.asyncio
    async def test_post_chat_message(self, app):
        """POST /chat/message should return a grounded response."""
        from api.services.rag import ParsedQuery

        app.state.query_understanding.parse.return_value = ParsedQuery(
            intent="tire_strategy",
            entities={},
            filters={},
            raw_question="When should I pit?",
        )
        app.state.context_assembler.execute_retrieval.return_value = {
            "sql": [{"lap_number": 15, "tire_compound": "SOFT", "tire_age_laps": 12}],
            "vector": [],
            "graph": [],
        }
        app.state.context_assembler.assemble.return_value = "CONTEXT: tire data..."
        app.state.response_generator.generate.return_value = (
            "Based on your tire data, **pit on lap 18**. "
            "Your softs are 12 laps old and degradation is increasing."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/message",
                json={"message": "When should I pit?"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "pit" in data["response"].lower()
        assert data["intent"] == "tire_strategy"

    @pytest.mark.asyncio
    async def test_post_chat_message_422_on_empty(self, app):
        """Empty message should return 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/message",
                json={"message": ""},
            )
        assert response.status_code == 422

    def test_websocket_chat(self, app):
        """WebSocket /ws/chat should stream response chunks."""
        from api.services.rag import ParsedQuery

        app.state.query_understanding.parse.return_value = ParsedQuery(
            intent="general",
            entities={},
            filters={},
            raw_question="Hello",
        )
        app.state.context_assembler.execute_retrieval.return_value = {
            "sql": [], "vector": [], "graph": [],
        }
        app.state.context_assembler.assemble.return_value = "CONTEXT"
        app.state.response_generator.generate.return_value = "Hello! I'm your race engineer."

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat") as ws:
            ws.send_json({"message": "Hello"})
            data = ws.receive_json()
            assert data["type"] in ("response", "chunk", "complete", "intent")
