"""Tests for the agentic race engineer (api/services/agent.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api.services.agent import (
    TOOLS,
    AgenticError,
    RaceEngineerAgent,
)
from tests.unit.api.mock_pool import FakeCursor, FakePool


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "id": "call_1",
        "function": {"index": 0, "name": name, "arguments": arguments},
    }


class TestToolsDefined:
    def test_eight_tools(self):
        names = {t["function"]["name"] for t in TOOLS}
        assert names == {
            "query_laps",
            "query_telemetry",
            "compare_laps",
            "predict_tire_life",
            "predict_pit_window",
            "vector_search_laps",
            "search_documents",
            "query_setup",
        }


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_tool_then_answer(self):
        """Tool result is fed back and the final answer returned."""
        ollama = AsyncMock()

        async def fake_chat(**kwargs):
            # First call: request predict_tire_life. Second call: final answer.
            messages = kwargs.get("messages", [])
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            if not tool_msgs:
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            _tool_call("predict_tire_life", {"tire_compound": "SOFT", "tire_age_laps": 12})
                        ],
                    }
                }
            return {"message": {"content": "You have 12 laps of life left."}}

        ollama.chat.side_effect = fake_chat
        agent = RaceEngineerAgent(pool=FakePool(), ollama_client=ollama, model="qwen3.5:9b")

        result = await agent.run("How much tire life left?")
        assert result.response == "You have 12 laps of life left."
        assert result.tool_calls == ["predict_tire_life"]
        assert result.iterations == 2
        assert result.used_tools is True

        # Verify the tool message was appended with real numbers
        call = ollama.chat.call_args_list[0]
        sent_tools = call.kwargs["tools"]
        assert sent_tools[0]["function"]["name"] == "query_laps"

    @pytest.mark.asyncio
    async def test_unknown_tool_reported_to_llm(self):
        ollama = AsyncMock()

        async def fake_chat(**kwargs):
            messages = kwargs.get("messages", [])
            if not any(m.get("role") == "tool" for m in messages):
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [_tool_call("nonexistent_tool", {})],
                    }
                }
            return {"message": {"content": "done"}}

        ollama.chat.side_effect = fake_chat
        agent = RaceEngineerAgent(pool=FakePool(), ollama_client=ollama, model="m")
        result = await agent.run("hi")
        assert result.response == "done"
        # The tool result should mention the error
        tool_msg = ollama.chat.call_args_list[-1].kwargs["messages"][-1]
        assert "Unknown tool" in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_ollama_error_raises_agentic_error(self):
        ollama = AsyncMock()
        ollama.chat.side_effect = RuntimeError("ollama down")
        agent = RaceEngineerAgent(pool=FakePool(), ollama_client=ollama, model="m")
        with pytest.raises(AgenticError):
            await agent.run("hi")

    @pytest.mark.asyncio
    async def test_empty_final_answer_raises(self):
        ollama = AsyncMock()
        ollama.chat.return_value = {"message": {"content": "", "tool_calls": None}}
        agent = RaceEngineerAgent(pool=FakePool(), ollama_client=ollama, model="m")
        with pytest.raises(AgenticError):
            await agent.run("hi")

    @pytest.mark.asyncio
    async def test_max_iterations_raises(self):
        ollama = AsyncMock()
        ollama.chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [_tool_call("predict_tire_life", {"tire_compound": "SOFT", "tire_age_laps": 1})],
            }
        }
        agent = RaceEngineerAgent(pool=FakePool(), ollama_client=ollama, model="m")
        with pytest.raises(AgenticError):
            await agent.run("loop forever")

    @pytest.mark.asyncio
    async def test_tool_failure_does_not_crash(self):
        """A failing tool surfaces an error dict to the LLM, loop continues."""
        ollama = AsyncMock()

        async def fake_chat(**kwargs):
            messages = kwargs.get("messages", [])
            if not any(m.get("role") == "tool" for m in messages):
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [_tool_call("query_setup", {"session_id": "nope"})],
                    }
                }
            return {"message": {"content": "No setup found."}}

        ollama.chat.side_effect = fake_chat

        class RaisingCursor(FakeCursor):
            async def execute(self, sql, binds=None):
                raise RuntimeError("db gone")

        pool = FakePool(cursor=RaisingCursor())
        agent = RaceEngineerAgent(pool=pool, ollama_client=ollama, model="m")
        result = await agent.run("setup?")
        assert result.response == "No setup found."
