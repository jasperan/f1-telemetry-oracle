"""Tests for the RAG query understanding and context assembly pipeline.

Verifies:
- Query parsing extracts intent + entities from natural language
- SQL generation produces valid query skeletons
- Vector search params are correctly derived
- Context assembly combines multiple data sources
- Response generation produces grounded answers
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.rag import (
    ContextAssembler,
    ParsedQuery,
    QueryUnderstanding,
    ResponseGenerator,
)


class TestQueryUnderstanding:
    """Test intent + entity extraction from natural language questions."""

    @pytest.fixture
    def query_parser(self):
        mock_ollama = AsyncMock()
        return QueryUnderstanding(ollama_client=mock_ollama)

    @pytest.mark.asyncio
    async def test_sector_analysis_intent(self, query_parser):
        """'Why am I slow in sector 2 at Silverstone?' -> sector_analysis intent."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "sector_analysis",
                    "entities": {
                        "sector": 2,
                        "circuit": "silverstone",
                    },
                    "filters": {},
                })
            }
        }

        result = await query_parser.parse("Why am I slow in sector 2 at Silverstone?")
        assert isinstance(result, ParsedQuery)
        assert result.intent == "sector_analysis"
        assert result.entities["sector"] == 2
        assert result.entities["circuit"] == "silverstone"

    @pytest.mark.asyncio
    async def test_comparison_intent(self, query_parser):
        """'Compare my lap to Verstappen' -> comparison intent."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "comparison",
                    "entities": {
                        "driver": "verstappen",
                        "comparison_type": "lap",
                    },
                    "filters": {},
                })
            }
        }

        result = await query_parser.parse("Compare my lap to Verstappen at Monza")
        assert result.intent == "comparison"
        assert result.entities["driver"] == "verstappen"

    @pytest.mark.asyncio
    async def test_tire_strategy_intent(self, query_parser):
        """'When should I pit?' -> tire_strategy intent."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "tire_strategy",
                    "entities": {},
                    "filters": {},
                })
            }
        }

        result = await query_parser.parse("When should I pit?")
        assert result.intent == "tire_strategy"

    @pytest.mark.asyncio
    async def test_historical_intent(self, query_parser):
        """'Who won the 2023 British GP?' -> historical intent."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "historical",
                    "entities": {
                        "season": 2023,
                        "circuit": "silverstone",
                    },
                    "filters": {"season": 2023},
                })
            }
        }

        result = await query_parser.parse("Who won the 2023 British GP?")
        assert result.intent == "historical"
        assert result.entities["season"] == 2023

    @pytest.mark.asyncio
    async def test_generates_sql_query(self, query_parser):
        """Parsed query should produce parameterized SQL for retrieval."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "sector_analysis",
                    "entities": {"sector": 2, "circuit": "silverstone"},
                    "filters": {},
                })
            }
        }

        result = await query_parser.parse("Why am I slow in sector 2 at Silverstone?")
        sql_parts = result.to_sql_queries()
        assert len(sql_parts) > 0
        # Each item is a (sql, bind_params) tuple
        for sql, params in sql_parts:
            assert isinstance(sql, str)
            assert isinstance(params, dict)
        # Should reference the laps/telemetry tables
        assert any("laps" in q.lower() or "telemetry" in q.lower() for q, _ in sql_parts)
        # Bind params should contain circuit filter
        assert any("circuit" in p for _, p in sql_parts)
        # SQL must NOT contain raw user input (no f-string interpolation)
        assert all("silverstone" not in q for q, _ in sql_parts)

    @pytest.mark.asyncio
    async def test_generates_vector_search_params(self, query_parser):
        """Parsed query should produce vector search parameters."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "comparison",
                    "entities": {"driver": "verstappen"},
                    "filters": {},
                })
            }
        }

        result = await query_parser.parse("Find laps similar to my fastest")
        vs_params = result.to_vector_search_params()
        assert "top_k" in vs_params
        assert vs_params["top_k"] > 0

    @pytest.mark.asyncio
    async def test_fallback_on_unparseable(self, query_parser):
        """Unparseable LLM output falls back to general intent."""
        query_parser._ollama.chat.return_value = {
            "message": {"content": "I don't understand the format"}
        }

        result = await query_parser.parse("random gibberish query")
        assert result.intent == "general"
        assert result.raw_question == "random gibberish query"

    @pytest.mark.asyncio
    async def test_graph_traversal_for_historical(self, query_parser):
        """Historical queries with a driver entity should generate a graph traversal."""
        query_parser._ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "historical",
                    "entities": {"driver": "verstappen", "season": 2023},
                    "filters": {"season": 2023},
                })
            }
        }

        result = await query_parser.parse("Verstappen results history")
        graph_result = result.to_graph_traversal()
        assert graph_result is not None
        graph_q, graph_params = graph_result
        assert isinstance(graph_q, str)
        assert isinstance(graph_params, dict)
        # Driver value should be in bind params, not in the SQL string
        assert "verstappen" in graph_params.get("driver", "")
        assert ":driver" in graph_q


class TestContextAssembler:
    """Test context assembly from multiple data sources."""

    @pytest.mark.asyncio
    async def test_assemble_with_sql_results(self):
        assembler = ContextAssembler(oracle_pool=MagicMock())
        parsed = ParsedQuery(intent="tire_strategy", raw_question="When should I pit?")

        context = await assembler.assemble(
            parsed,
            sql_results=[{"lap_number": 15, "tire_compound": "SOFT"}],
        )
        assert "tire_strategy" in context
        assert "SOFT" in context
        assert "DATA FROM DATABASE" in context

    @pytest.mark.asyncio
    async def test_assemble_with_no_data(self):
        assembler = ContextAssembler(oracle_pool=MagicMock())
        parsed = ParsedQuery(intent="general", raw_question="Hello")

        context = await assembler.assemble(parsed)
        assert "NO DATA FOUND" in context

    @pytest.mark.asyncio
    async def test_assemble_with_vector_results(self):
        assembler = ContextAssembler(oracle_pool=MagicMock())
        parsed = ParsedQuery(intent="comparison", raw_question="Compare laps")

        context = await assembler.assemble(
            parsed,
            vector_results=[{"lap_id": "abc", "similarity": 0.95}],
        )
        assert "SIMILAR LAPS" in context
        assert "0.95" in context


class TestResponseGenerator:
    """Test response generation via Ollama."""

    @pytest.mark.asyncio
    async def test_generate_non_streaming(self):
        mock_ollama = AsyncMock()
        mock_ollama.chat.return_value = {
            "message": {
                "content": "Based on your tire data, pit on lap 18."
            }
        }

        generator = ResponseGenerator(ollama_client=mock_ollama)
        response = await generator.generate("CONTEXT: tire data...")

        assert "pit on lap 18" in response
        mock_ollama.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_passes_system_prompt(self):
        mock_ollama = AsyncMock()
        mock_ollama.chat.return_value = {
            "message": {"content": "Response"}
        }

        generator = ResponseGenerator(ollama_client=mock_ollama)
        await generator.generate("CONTEXT")

        call_kwargs = mock_ollama.chat.call_args
        messages = call_kwargs.kwargs.get("messages", [])
        assert any(m["role"] == "system" for m in messages)
