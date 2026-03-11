"""Unit tests for the predict router (tire life, pit window heuristics).

No DB required — these are pure heuristic endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.predict import router as predict_router


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture()
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(predict_router, prefix="/api")
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ============================================================
# Tire life prediction tests
# ============================================================
class TestTireLifePrediction:
    def test_soft_tire_fresh(self, client: TestClient) -> None:
        resp = client.post("/api/predict/tire-life", json={
            "tire_compound": "SOFT",
            "tire_age_laps": 0,
            "track_temp_c": 30.0,
            "fuel_load_kg": 50.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_grip_pct"] == 100.0
        assert data["predicted_remaining_laps"] > 0
        assert data["degradation_rate_pct_per_lap"] > 0
        assert "OK" in data["recommendation"]

    def test_soft_tire_old(self, client: TestClient) -> None:
        resp = client.post("/api/predict/tire-life", json={
            "tire_compound": "SOFT",
            "tire_age_laps": 25,
            "track_temp_c": 30.0,
            "fuel_load_kg": 50.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_grip_pct"] < 50.0
        assert "CRITICAL" in data["recommendation"] or "WARNING" in data["recommendation"]

    def test_hard_tire_lasts_longer(self, client: TestClient) -> None:
        soft = client.post("/api/predict/tire-life", json={
            "tire_compound": "SOFT",
            "tire_age_laps": 5,
            "track_temp_c": 30.0,
            "fuel_load_kg": 30.0,
        }).json()

        hard = client.post("/api/predict/tire-life", json={
            "tire_compound": "HARD",
            "tire_age_laps": 5,
            "track_temp_c": 30.0,
            "fuel_load_kg": 30.0,
        }).json()

        assert hard["predicted_remaining_laps"] > soft["predicted_remaining_laps"]
        assert hard["degradation_rate_pct_per_lap"] < soft["degradation_rate_pct_per_lap"]

    def test_hot_track_increases_degradation(self, client: TestClient) -> None:
        cool = client.post("/api/predict/tire-life", json={
            "tire_compound": "MEDIUM",
            "tire_age_laps": 5,
            "track_temp_c": 20.0,
            "fuel_load_kg": 30.0,
        }).json()

        hot = client.post("/api/predict/tire-life", json={
            "tire_compound": "MEDIUM",
            "tire_age_laps": 5,
            "track_temp_c": 50.0,
            "fuel_load_kg": 30.0,
        }).json()

        assert hot["degradation_rate_pct_per_lap"] > cool["degradation_rate_pct_per_lap"]
        assert hot["current_grip_pct"] < cool["current_grip_pct"]

    def test_unknown_compound_uses_defaults(self, client: TestClient) -> None:
        resp = client.post("/api/predict/tire-life", json={
            "tire_compound": "UNKNOWN_COMPOUND",
            "tire_age_laps": 3,
            "track_temp_c": 30.0,
            "fuel_load_kg": 30.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicted_remaining_laps"] >= 0

    def test_case_insensitive_compound(self, client: TestClient) -> None:
        resp = client.post("/api/predict/tire-life", json={
            "tire_compound": "soft",
            "tire_age_laps": 0,
            "track_temp_c": 30.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_grip_pct"] == 100.0


# ============================================================
# Pit window prediction tests
# ============================================================
class TestPitWindowPrediction:
    def test_basic_pit_window(self, client: TestClient) -> None:
        resp = client.post("/api/predict/pit-window", json={
            "current_lap": 10,
            "total_laps": 50,
            "tire_compound": "MEDIUM",
            "tire_age_laps": 10,
            "position": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["optimal_pit_lap"] > 10
        assert data["optimal_pit_lap"] < 50
        assert data["recommended_compound"] in ("SOFT", "MEDIUM", "HARD")
        assert len(data["strategy_description"]) > 0

    def test_pit_window_near_end_recommends_soft(self, client: TestClient) -> None:
        resp = client.post("/api/predict/pit-window", json={
            "current_lap": 40,
            "total_laps": 50,
            "tire_compound": "HARD",
            "tire_age_laps": 30,
            "position": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_compound"] == "SOFT"

    def test_undercut_viable(self, client: TestClient) -> None:
        resp = client.post("/api/predict/pit-window", json={
            "current_lap": 15,
            "total_laps": 50,
            "tire_compound": "MEDIUM",
            "tire_age_laps": 15,
            "position": 3,
            "gap_ahead_ms": 2000,
            "gap_behind_ms": 5000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["undercut_viable"] is True

    def test_overcut_viable(self, client: TestClient) -> None:
        resp = client.post("/api/predict/pit-window", json={
            "current_lap": 15,
            "total_laps": 50,
            "tire_compound": "MEDIUM",
            "tire_age_laps": 10,
            "position": 3,
            "gap_ahead_ms": 5000,
            "gap_behind_ms": 3000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["overcut_viable"] is True

    def test_no_undercut_without_gap(self, client: TestClient) -> None:
        resp = client.post("/api/predict/pit-window", json={
            "current_lap": 15,
            "total_laps": 50,
            "tire_compound": "MEDIUM",
            "tire_age_laps": 15,
            "position": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["undercut_viable"] is False
        assert data["overcut_viable"] is False

    def test_pit_window_doesnt_exceed_race(self, client: TestClient) -> None:
        resp = client.post("/api/predict/pit-window", json={
            "current_lap": 1,
            "total_laps": 5,
            "tire_compound": "HARD",
            "tire_age_laps": 0,
            "position": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["optimal_pit_lap"] < 5
