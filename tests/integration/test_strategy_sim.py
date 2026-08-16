"""Integration tests — Monte Carlo strategy simulator + predict API.

Verifies the in-database ONNX scoring path through the API contract and
the strategy simulator's output shape and ranking.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from api.services.oracle import OraclePool
from api.services.strategy import monte_carlo_strategy, tire_life

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest_asyncio.fixture(loop_scope="session")
async def app(pool: OraclePool):
    """Create FastAPI app wired to the test Oracle pool."""
    application = create_app()
    application.state.pool = pool
    return application


@pytest_asyncio.fixture(loop_scope="session")
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_tire_life_uses_onnx(pool):
    """Tire life prediction should report the in-database ONNX engine."""
    result = await tire_life(pool, "SOFT", 12, 38.0, 55.0)
    assert result["model_used"] == "onnx" or result["model_used"] == "heuristic"
    assert 0 <= result["current_grip_pct"] <= 100


async def test_monte_carlo_shape(pool):
    result = await monte_carlo_strategy(pool, total_laps=30, n_sims=100, seed=42)
    assert result["total_laps"] == 30
    assert result["n_sims"] == 100
    assert len(result["strategies"]) >= 10
    top = result["strategies"][0]
    assert top["rank"] == 1
    assert top["win_probability"] == 1.0
    assert top["median_race_time_s"] > 0


async def test_strategy_sim_endpoint(client):
    """POST /api/predict/strategy-sim returns ranked strategies."""
    resp = await client.post(
        "/api/predict/strategy-sim",
        json={"total_laps": 30, "track_temp_c": 30.0, "n_sims": 100},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_laps"] == 30
    assert body["strategies"]
    assert body["strategies"][0]["rank"] == 1
    assert all(0 <= s["win_probability"] <= 1 for s in body["strategies"])


async def test_tire_life_endpoint(client):
    """POST /api/predict/tire-life returns grip + remaining laps."""
    resp = await client.post(
        "/api/predict/tire-life",
        json={
            "tire_compound": "MEDIUM",
            "tire_age_laps": 10,
            "track_temp_c": 35.0,
            "fuel_load_kg": 70.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "current_grip_pct" in body
    assert "predicted_remaining_laps" in body
    assert body["model_used"] in ("onnx", "heuristic")


async def test_pit_window_endpoint(client):
    """POST /api/predict/pit-window returns a bounded recommendation."""
    resp = await client.post(
        "/api/predict/pit-window",
        json={
            "current_lap": 18,
            "total_laps": 53,
            "tire_compound": "MEDIUM",
            "tire_age_laps": 18,
            "position": 5,
            "gap_ahead_ms": 1500,
            "gap_behind_ms": 8000,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 18 < body["optimal_pit_lap"] < 53
    assert body["recommended_compound"] in ("SOFT", "MEDIUM", "HARD")


async def test_chat_endpoint_contract(client, monkeypatch):
    """POST /api/chat/message returns the full response + trace contract."""
    from unittest.mock import AsyncMock

    import api.main as main_module
    from api.services.rag import ParsedQuery

    app = client._transport.app  # type: ignore[attr-defined]

    # Disable the agentic path and stub the classic RAG pipeline so no
    # live LLM or database calls are needed.
    monkeypatch.setattr(main_module.settings, "agentic_chat", False)
    app.state.agent = None  # type: ignore[attr-defined]
    app.state.query_understanding = AsyncMock()  # type: ignore[attr-defined]
    app.state.query_understanding.parse.return_value = ParsedQuery(
        intent="tire_strategy", entities={}, filters={}, raw_question="test"
    )
    app.state.context_assembler = AsyncMock()  # type: ignore[attr-defined]
    app.state.context_assembler.execute_retrieval.return_value = {
        "sql": [{"lap_number": 15}],
        "vector": [],
        "graph": [],
        "docs": [],
    }
    app.state.context_assembler.assemble.return_value = "CONTEXT"
    app.state.response_generator = AsyncMock()  # type: ignore[attr-defined]
    app.state.response_generator.generate.return_value = "Grounded stub answer."

    resp = await client.post(
        "/api/chat/message",
        json={"message": "How much tire life do I have left?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Grounded stub answer."
    assert body["trace"]["path"] == "rag"
    assert body["trace"]["intent"] == "tire_strategy"
    assert "sql" in body["trace"]["sources"]
