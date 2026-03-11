"""Unit tests for core API routers (circuits, sessions, drivers).

Uses FastAPI TestClient with a mocked OraclePool — no real Oracle DB required.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.circuits import router as circuits_router
from api.routers.drivers import router as drivers_router
from api.routers.sessions import router as sessions_router

# ============================================================
# Sample data
# ============================================================
NOW = datetime(2025, 3, 15, 12, 0, 0)

SAMPLE_CIRCUITS = [
    ("monza", "Monza", "Italy", "Monza", 5793.0, 45.6156, 9.2811, NOW),
    ("silverstone", "Silverstone", "UK", "Silverstone", 5891.0, 52.0786, -1.0169, NOW),
]

SAMPLE_SESSIONS = [
    ("sess-001", "monza", "race", "sim", 2025, 16, 28.5, 42.0, NOW, NOW),
    ("sess-002", "silverstone", "qualifying", "openf1", 2025, 12, 22.0, 35.0, NOW, NOW),
]

SAMPLE_DRIVERS = [
    ("driver-ver", "VER", "Max", "Verstappen", 1, "Dutch", 0, NOW),
    ("sim-player", "PLR", "Sim", "Player", 99, None, 1, NOW),
]


# ============================================================
# Mock pool infrastructure
# ============================================================
class MockCursor:
    """Mock async cursor that returns pre-configured rows."""

    def __init__(self) -> None:
        self._rows: list[tuple] = []

    async def execute(self, sql: str, params: list | None = None) -> None:
        pass

    async def fetchall(self) -> list[tuple]:
        return self._rows

    async def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


class MockConnection:
    """Mock async connection that yields a MockCursor."""

    def __init__(self, cursor: MockCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> MockCursor:
        return self._cursor


class MockPool:
    """Mock OraclePool with pre-configured cursor data."""

    def __init__(self) -> None:
        self._cursor = MockCursor()

    def set_rows(self, rows: list[tuple]) -> None:
        self._cursor._rows = rows

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
    """Create a FastAPI app with mocked pool on state."""
    test_app = FastAPI()
    test_app.include_router(circuits_router, prefix="/api")
    test_app.include_router(sessions_router, prefix="/api")
    test_app.include_router(drivers_router, prefix="/api")
    test_app.state.pool = mock_pool
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ============================================================
# Circuit tests
# ============================================================
class TestCircuits:
    def test_list_circuits(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows(SAMPLE_CIRCUITS)
        resp = client.get("/api/circuits")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["circuit_id"] == "monza"
        assert data[0]["circuit_name"] == "Monza"
        assert data[0]["country"] == "Italy"
        assert data[1]["circuit_id"] == "silverstone"

    def test_list_circuits_empty(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([])
        resp = client.get("/api/circuits")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_circuit_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_CIRCUITS[0]])
        resp = client.get("/api/circuits/monza")
        assert resp.status_code == 200
        data = resp.json()
        assert data["circuit_id"] == "monza"
        assert data["track_length_m"] == 5793.0

    def test_get_circuit_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([])
        resp = client.get("/api/circuits/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ============================================================
# Session tests
# ============================================================
class TestSessions:
    def test_list_sessions(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows(SAMPLE_SESSIONS)
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_sessions_filter_source(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_SESSIONS[0]])
        resp = client.get("/api/sessions?source=sim")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source"] == "sim"

    def test_list_sessions_filter_circuit(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_SESSIONS[1]])
        resp = client.get("/api/sessions?circuit_id=silverstone")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_list_sessions_filter_season(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows(SAMPLE_SESSIONS)
        resp = client.get("/api/sessions?season=2025")
        assert resp.status_code == 200

    def test_get_session_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_SESSIONS[0]])
        resp = client.get("/api/sessions/sess-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-001"
        assert data["circuit_id"] == "monza"
        assert data["session_type"] == "race"

    def test_get_session_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([])
        resp = client.get("/api/sessions/nonexistent")
        assert resp.status_code == 404


# ============================================================
# Driver tests
# ============================================================
class TestDrivers:
    def test_list_drivers(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows(SAMPLE_DRIVERS)
        resp = client.get("/api/drivers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["driver_id"] == "driver-ver"
        assert data[0]["first_name"] == "Max"

    def test_list_drivers_filter_nationality(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_DRIVERS[0]])
        resp = client.get("/api/drivers?nationality=Dutch")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_drivers_filter_sim_player(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_DRIVERS[1]])
        resp = client.get("/api/drivers?is_sim_player=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["is_sim_player"] is True

    def test_get_driver_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([SAMPLE_DRIVERS[0]])
        resp = client.get("/api/drivers/driver-ver")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "VER"
        assert data["last_name"] == "Verstappen"
        assert data["is_sim_player"] is False

    def test_get_driver_not_found(self, client: TestClient, mock_pool: MockPool) -> None:
        mock_pool.set_rows([])
        resp = client.get("/api/drivers/nonexistent")
        assert resp.status_code == 404
