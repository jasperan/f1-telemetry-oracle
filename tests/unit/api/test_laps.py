"""Unit tests for the laps router (list, detail, telemetry, similar).

Uses FastAPI TestClient with a mocked OraclePool — no real Oracle DB required.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.laps import router as laps_router

# ============================================================
# Sample data
# ============================================================
NOW = datetime(2025, 3, 15, 12, 0, 0)

SAMPLE_LAP = (
    "lap-001", "sess-001", "driver-ver", 5,
    28500, 33200, 24800, 86500,
    "SOFT", 3, 42.5, 75.0,
    1, 1, NOW,
)

SAMPLE_LAP_2 = (
    "lap-002", "sess-001", "driver-ham", 5,
    28700, 33400, 25000, 87100,
    "MEDIUM", 8, 38.0, 80.0,
    1, 2, NOW,
)

SAMPLE_FRAME = (
    "frame-001", "lap-001", 1000, 150.5,
    285.3, 0.95, 0.0, -0.02,
    7, 11200, 1,
    100.5, 200.3, 10.1,
    0.15, -0.30,
    95.0, 97.0, 92.0, 94.0,
    450.0, 460.0, 420.0, 430.0,
)

SAMPLE_FRAME_2 = (
    "frame-002", "lap-001", 1100, 180.2,
    290.1, 1.0, 0.0, 0.01,
    7, 11500, 0,
    110.5, 210.3, 10.2,
    0.10, -0.25,
    96.0, 98.0, 93.0, 95.0,
    455.0, 465.0, 425.0, 435.0,
)


# ============================================================
# Mock pool infrastructure
# ============================================================
class MockCursor:
    """Mock async cursor with call tracking for SQL-dependent responses."""

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
    test_app.include_router(laps_router, prefix="/api")
    test_app.state.pool = mock_pool
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ============================================================
# Lap list / detail tests
# ============================================================
class TestLapsList:
    def test_list_laps(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([SAMPLE_LAP, SAMPLE_LAP_2])
        resp = client.get("/api/laps")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["lap_id"] == "lap-001"
        assert data[0]["sector1_ms"] == 28500

    def test_list_laps_filter_session(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([SAMPLE_LAP])
        resp = client.get("/api/laps?session_id=sess-001")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_laps_filter_driver(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([SAMPLE_LAP])
        resp = client.get("/api/laps?driver_id=driver-ver")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_laps_empty(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([])
        resp = client.get("/api/laps")
        assert resp.status_code == 200
        assert resp.json() == []


class TestLapDetail:
    def test_get_lap_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([SAMPLE_LAP])
        resp = client.get("/api/laps/lap-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lap_id"] == "lap-001"
        assert data["tire_compound"] == "SOFT"
        assert data["lap_time_ms"] == 86500

    def test_get_lap_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([])
        resp = client.get("/api/laps/nonexistent")
        assert resp.status_code == 404


# ============================================================
# Telemetry endpoint tests
# ============================================================
class TestLapTelemetry:
    def test_get_telemetry_basic(self, client: TestClient, mock_pool: MockPool) -> None:
        # First call: lap existence check; second call: frames query
        mock_pool._cursor.queue_result([("lap-001",)])
        mock_pool._cursor.queue_result([SAMPLE_FRAME, SAMPLE_FRAME_2])
        resp = client.get("/api/laps/lap-001/telemetry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is False
        assert len(data["items"]) == 2
        assert data["items"][0]["frame_id"] == "frame-001"
        assert data["items"][0]["speed_kph"] == 285.3

    def test_get_telemetry_with_cursor(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([("lap-001",)])
        mock_pool._cursor.queue_result([SAMPLE_FRAME_2])
        resp = client.get("/api/laps/lap-001/telemetry?cursor_after=1000")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    def test_get_telemetry_has_more(self, client: TestClient, mock_pool: MockPool) -> None:
        # Return page_size+1 rows to trigger has_more=True
        mock_pool._cursor.queue_result([("lap-001",)])
        # page_size=1, so 2 rows = has_more
        mock_pool._cursor.queue_result([SAMPLE_FRAME, SAMPLE_FRAME_2])
        resp = client.get("/api/laps/lap-001/telemetry?page_size=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert len(data["items"]) == 1

    def test_get_telemetry_lap_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([])
        resp = client.get("/api/laps/nonexistent/telemetry")
        assert resp.status_code == 404


# ============================================================
# Similar laps tests
# ============================================================
class TestSimilarLaps:
    def test_similar_laps_found(self, client: TestClient, mock_pool: MockPool) -> None:
        # First call: get target embedding
        mock_pool._cursor.queue_result([("some_embedding_data",)])
        # Second call: vector search results (lap columns + distance)
        similar_row = SAMPLE_LAP_2 + (0.15,)
        mock_pool._cursor.queue_result([similar_row])
        resp = client.get("/api/laps/lap-001/similar?top_n=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["lap"]["lap_id"] == "lap-002"
        assert data[0]["distance"] == 0.15

    def test_similar_laps_no_embedding(self, client: TestClient, mock_pool: MockPool) -> None:
        # Target lap exists but has no embedding
        mock_pool._cursor.queue_result([(None,)])
        resp = client.get("/api/laps/lap-001/similar")
        assert resp.status_code == 422
        assert "no embedding" in resp.json()["detail"].lower()

    def test_similar_laps_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool._cursor.queue_result([])
        resp = client.get("/api/laps/nonexistent/similar")
        assert resp.status_code == 404
