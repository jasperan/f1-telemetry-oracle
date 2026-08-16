"""Tests for the shared race-strategy service (api/services/strategy.py)."""

from __future__ import annotations

import pytest

from api.services import strategy
from tests.unit.api.mock_pool import FakePool


class TestTireLife:
    @pytest.mark.asyncio
    async def test_onnx_path(self, monkeypatch):
        async def fake_score(pool, model, inputs):
            if model == "TIRE_GRIP_MODEL":
                return 48.0
            return 10.0

        monkeypatch.setattr(strategy, "score_regression", fake_score)
        result = await strategy.tire_life(FakePool(), "SOFT", 12, 38.0, 55.0)
        assert result["model_used"] == "onnx"
        assert result["current_grip_pct"] == 48.0
        assert result["predicted_remaining_laps"] == 10
        assert result["degradation_rate_pct_per_lap"] == pytest.approx(4.333, abs=0.01)

    @pytest.mark.asyncio
    async def test_heuristic_fallback(self, monkeypatch):
        async def none_score(*args, **kwargs):
            return None

        monkeypatch.setattr(strategy, "score_regression", none_score)
        result = await strategy.tire_life(FakePool(), "HARD", 10, 20.0, 40.0)
        assert result["model_used"] == "heuristic"
        assert 0 <= result["current_grip_pct"] <= 100
        assert result["predicted_remaining_laps"] >= 0

    @pytest.mark.asyncio
    async def test_onnx_grip_clamped(self, monkeypatch):
        async def fake_score(pool, model, inputs):
            return 120.0 if model == "TIRE_GRIP_MODEL" else 30.0

        monkeypatch.setattr(strategy, "score_regression", fake_score)
        result = await strategy.tire_life(FakePool(), "SOFT", 1, 30.0, 50.0)
        assert result["current_grip_pct"] == 100.0


class TestPitWindow:
    @pytest.mark.asyncio
    async def test_recommendation_bounds(self, monkeypatch):
        async def fake_score(pool, model, inputs):
            return 30.0 if model == "TIRE_GRIP_MODEL" else 5.0

        monkeypatch.setattr(strategy, "score_regression", fake_score)
        result = await strategy.pit_window(
            FakePool(), current_lap=18, total_laps=53, tire_compound="MEDIUM", tire_age_laps=18
        )
        assert result["optimal_pit_lap"] > 18
        assert result["optimal_pit_lap"] < 53
        assert result["recommended_compound"] in ("SOFT", "MEDIUM", "HARD")
        assert result["model_used"] == "onnx"

    @pytest.mark.asyncio
    async def test_undercut_and_overcut(self, monkeypatch):
        async def none_score(*args, **kwargs):
            return None

        monkeypatch.setattr(strategy, "score_regression", none_score)
        result = await strategy.pit_window(
            FakePool(),
            current_lap=18,
            total_laps=53,
            tire_compound="SOFT",
            tire_age_laps=14,
            gap_ahead_ms=1500,
            gap_behind_ms=8000,
        )
        assert result["undercut_viable"] is True
        assert result["overcut_viable"] is True
        assert result["model_used"] == "heuristic"


class TestMonteCarlo:
    @pytest.mark.asyncio
    async def test_deterministic_and_ranked(self):
        r1 = await strategy.monte_carlo_strategy(FakePool(), total_laps=30, n_sims=100, seed=42)
        r2 = await strategy.monte_carlo_strategy(FakePool(), total_laps=30, n_sims=100, seed=42)
        assert r1 == r2, "Same seed must produce identical simulations"

        strategies = r1["strategies"]
        assert len(strategies) >= 10
        # Ranks are assigned in order of median race time
        medians = [s["median_race_time_s"] for s in strategies]
        assert medians == sorted(medians)
        # Win probabilities decrease with rank
        assert strategies[0]["win_probability"] >= strategies[-1]["win_probability"]
        assert strategies[0]["rank"] == 1
        assert 0 <= strategies[0]["win_probability"] <= 1

    @pytest.mark.asyncio
    async def test_single_stop_preferred_in_short_race(self):
        result = await strategy.monte_carlo_strategy(
            FakePool(), total_laps=20, n_sims=100, seed=7
        )
        top = result["strategies"][0]["strategy"]
        assert len(top) == 1, "A 20-lap race should favor a single stint"

    @pytest.mark.asyncio
    async def test_custom_compounds(self):
        result = await strategy.monte_carlo_strategy(
            FakePool(), total_laps=40, n_sims=50, seed=1, compounds=["SOFT", "HARD"]
        )
        for s in result["strategies"]:
            assert set(s["strategy"]).issubset({"SOFT", "HARD"})
