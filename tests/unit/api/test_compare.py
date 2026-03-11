"""Unit tests for the compare router (multi-lap comparison, sim-vs-real).

Uses FastAPI TestClient with a mocked OraclePool — no real Oracle DB required.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.compare import _align_telemetry, _interpolate_at
from api.routers.compare import router as compare_router

# ============================================================
# Sample data
# ============================================================
NOW = datetime(2025, 3, 15, 12, 0, 0)

# Lap row layout: lap_id, session_id, driver_id, lap_number,
#   sector1_ms, sector2_ms, sector3_ms, lap_time_ms,
#   tire_compound, tire_age_laps, fuel_load_kg, ers_deploy_pct,
#   is_valid, position, created_at
SAMPLE_SIM_LAP = (
    "lap-sim-001", "sess-sim-001", "sim-player", 5,
    28500, 33200, 24800, 86500,
    "SOFT", 3, 42.5, 75.0,
    1, 1, NOW,
)

SAMPLE_REAL_LAP = (
    "lap-real-001", "sess-real-001", "driver-ver", 5,
    28300, 33000, 24600, 85900,
    "SOFT", 5, 40.0, 80.0,
    1, 1, NOW,
)

# Telemetry frame row layout (24 columns):
# frame_id, lap_id, timestamp_ms, distance_m,
# speed_kph, throttle_pct, brake_pct, steering,
# gear, rpm, drs, pos_x, pos_y, pos_z, g_lat, g_lon,
# tire_temp_fl/fr/rl/rr, brake_temp_fl/fr/rl/rr

def _make_frame(frame_id: str, lap_id: str, ts: int, dist: float,
                speed: float, throttle: float, brake: float, steering: float) -> tuple:
    return (
        frame_id, lap_id, ts, dist,
        speed, throttle, brake, steering,
        7, 11200, 0, 100.0, 200.0, 10.0, 0.1, -0.2,
        95.0, 97.0, 92.0, 94.0,
        450.0, 460.0, 420.0, 430.0,
    )


FRAMES_SIM = [
    _make_frame("f-s-1", "lap-sim-001", 1000, 0.0, 100.0, 0.5, 0.0, 0.01),
    _make_frame("f-s-2", "lap-sim-001", 1100, 50.0, 200.0, 0.8, 0.0, -0.02),
    _make_frame("f-s-3", "lap-sim-001", 1200, 100.0, 280.0, 1.0, 0.0, 0.0),
    _make_frame("f-s-4", "lap-sim-001", 1300, 150.0, 290.0, 1.0, 0.0, 0.01),
]

FRAMES_REAL = [
    _make_frame("f-r-1", "lap-real-001", 2000, 0.0, 105.0, 0.6, 0.0, 0.0),
    _make_frame("f-r-2", "lap-real-001", 2100, 50.0, 210.0, 0.85, 0.0, -0.01),
    _make_frame("f-r-3", "lap-real-001", 2200, 100.0, 285.0, 1.0, 0.0, 0.0),
    _make_frame("f-r-4", "lap-real-001", 2300, 150.0, 295.0, 1.0, 0.0, 0.005),
]


# ============================================================
# Mock pool infrastructure
# ============================================================
class MockCursor:
    """Mock cursor with a queue of results — each execute() consumes one."""

    def __init__(self) -> None:
        self._results: list[list[tuple]] = []
        self._call_idx: int = 0

    def queue_result(self, rows: list[tuple]) -> None:
        self._results.append(rows)

    async def execute(self, sql: str, params: list | None = None) -> None:
        pass

    async def fetchall(self) -> list[tuple]:
        if self._call_idx < len(self._results):
            result = self._results[self._call_idx]
            self._call_idx += 1
            return result
        return []

    async def fetchone(self) -> tuple | None:
        if self._call_idx < len(self._results):
            result = self._results[self._call_idx]
            self._call_idx += 1
            return result[0] if result else None
        return None


class MockConnection:
    def __init__(self, cursor: MockCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> MockCursor:
        return self._cursor


class MockPool:
    def __init__(self) -> None:
        self._cursor = MockCursor()

    @contextlib.asynccontextmanager
    async def connection(self) -> AsyncIterator[MockConnection]:
        yield MockConnection(self._cursor)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture()
def mock_pool() -> MockPool:
    return MockPool()


@pytest.fixture()
def app(mock_pool: MockPool) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(compare_router, prefix="/api")
    test_app.state.pool = mock_pool
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ============================================================
# Interpolation helper tests
# ============================================================
class TestInterpolation:
    def test_interpolate_within_range(self) -> None:
        distances = [0.0, 50.0, 100.0]
        values = [100.0, 200.0, 300.0]
        # At 25.0, should be 150.0
        result = _interpolate_at(distances, values, 25.0)
        assert abs(result - 150.0) < 0.01

    def test_interpolate_at_boundary(self) -> None:
        distances = [0.0, 100.0]
        values = [10.0, 20.0]
        assert _interpolate_at(distances, values, 0.0) == 10.0
        assert _interpolate_at(distances, values, 100.0) == 20.0

    def test_interpolate_before_range(self) -> None:
        distances = [10.0, 20.0]
        values = [100.0, 200.0]
        assert _interpolate_at(distances, values, 5.0) == 100.0

    def test_interpolate_after_range(self) -> None:
        distances = [10.0, 20.0]
        values = [100.0, 200.0]
        assert _interpolate_at(distances, values, 30.0) == 200.0

    def test_interpolate_empty(self) -> None:
        assert _interpolate_at([], [], 10.0) == 0.0


class TestAlignTelemetry:
    def test_alignment_produces_deltas(self) -> None:
        deltas = _align_telemetry(FRAMES_SIM, FRAMES_REAL, step_m=50.0)
        assert len(deltas) > 0
        # At distance 0.0: sim speed 100 - real speed 105 = -5
        assert abs(deltas[0].speed_delta - (-5.0)) < 0.01
        assert deltas[0].distance_m == 0.0

    def test_alignment_empty_frames(self) -> None:
        assert _align_telemetry([], FRAMES_REAL) == []
        assert _align_telemetry(FRAMES_SIM, []) == []
        assert _align_telemetry([], []) == []


# ============================================================
# Compare laps endpoint tests
# ============================================================
class TestCompareLaps:
    def test_compare_two_laps(self, client: TestClient, mock_pool: MockPool) -> None:
        # Queue: fetch lap row for lap-sim-001, fetch lap row for lap-real-001,
        #   fetch frames for lap-sim-001, fetch frames for lap-real-001
        mock_pool._cursor.queue_result([SAMPLE_SIM_LAP])
        mock_pool._cursor.queue_result([SAMPLE_REAL_LAP])
        mock_pool._cursor.queue_result(FRAMES_SIM)
        mock_pool._cursor.queue_result(FRAMES_REAL)
        resp = client.get("/api/compare/laps?ids=lap-sim-001,lap-real-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lap_ids"] == ["lap-sim-001", "lap-real-001"]
        assert len(data["deltas"]) > 0
        assert "sector1_ms" in data["sector_deltas"]
        assert len(data["sector_deltas"]["sector1_ms"]) == 2

    def test_compare_requires_two_ids(self, client: TestClient, mock_pool: MockPool) -> None:
        resp = client.get("/api/compare/laps?ids=lap-001")
        assert resp.status_code == 400
        assert "2 lap IDs" in resp.json()["detail"]

    def test_compare_lap_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([])  # first lap not found
        resp = client.get("/api/compare/laps?ids=nonexistent,lap-real-001")
        assert resp.status_code == 404


# ============================================================
# Sim-vs-real endpoint tests
# ============================================================
class TestSimVsReal:
    def test_sim_vs_real_success(self, client: TestClient, mock_pool: MockPool) -> None:
        # Queue: fetch sim lap, fetch session (circuit_id, source), find real lap,
        #   fetch sim frames, fetch real frames
        mock_pool._cursor.queue_result([SAMPLE_SIM_LAP])
        mock_pool._cursor.queue_result([("monza", "sim")])
        mock_pool._cursor.queue_result([SAMPLE_REAL_LAP])
        mock_pool._cursor.queue_result(FRAMES_SIM)
        mock_pool._cursor.queue_result(FRAMES_REAL)
        resp = client.get("/api/compare/sim-vs-real?lap_id=lap-sim-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sim_lap_id"] == "lap-sim-001"
        assert data["real_lap_id"] == "lap-real-001"
        assert data["circuit_id"] == "monza"
        assert len(data["comparison"]["deltas"]) > 0

    def test_sim_vs_real_lap_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([])
        resp = client.get("/api/compare/sim-vs-real?lap_id=nonexistent")
        assert resp.status_code == 404

    def test_sim_vs_real_not_sim_source(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([SAMPLE_REAL_LAP])
        mock_pool._cursor.queue_result([("monza", "openf1")])
        resp = client.get("/api/compare/sim-vs-real?lap_id=lap-real-001")
        assert resp.status_code == 400
        assert "not 'sim'" in resp.json()["detail"]

    def test_sim_vs_real_no_real_lap(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([SAMPLE_SIM_LAP])
        mock_pool._cursor.queue_result([("monza", "sim")])
        mock_pool._cursor.queue_result([])  # no real lap found
        resp = client.get("/api/compare/sim-vs-real?lap_id=lap-sim-001")
        assert resp.status_code == 404
        assert "No real-world lap" in resp.json()["detail"]
