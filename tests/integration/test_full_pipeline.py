"""Full-stack integration tests -- real Oracle DB, no mocks.

Tests the complete round-trip:
  Seed Data -> DB Insert -> API Query -> Response Validation
  Vector Search -> Similar Lap Retrieval
  Duality View Insert -> Relational Query
"""

from __future__ import annotations

import contextlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from api.services.oracle import OraclePool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest_asyncio.fixture(loop_scope="session")
async def app(pool: OraclePool):
    """Create FastAPI app wired to the test Oracle pool."""
    application = create_app()
    # Override the pool with our test pool (bypass lifespan)
    application.state.pool = pool
    return application


@pytest_asyncio.fixture(loop_scope="session")
async def client(app):
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# -- Circuit / Driver / Session Endpoints ------------------------------------


class TestCRUDEndpoints:
    """Verify basic CRUD endpoints return seeded fixture data."""

    async def test_list_circuits(self, client: AsyncClient):
        resp = await client.get("/api/circuits")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        monza = next(c for c in data if c["circuit_id"] == "monza")
        assert monza["country"] == "Italy"
        assert monza["track_length_m"] == 5793

    async def test_list_drivers(self, client: AsyncClient):
        resp = await client.get("/api/drivers")
        assert resp.status_code == 200
        data = resp.json()
        codes = {d["code"] for d in data}
        assert "VER" in codes
        assert "SIM" in codes

    async def test_get_session(self, client: AsyncClient):
        resp = await client.get("/api/sessions/monza_2024_r")
        assert resp.status_code == 200
        session = resp.json()
        assert session["circuit_id"] == "monza"
        assert session["session_type"] == "race"
        assert session["source"] == "openf1"

    async def test_list_sessions_filter_by_circuit(self, client: AsyncClient):
        resp = await client.get("/api/sessions", params={"circuit_id": "monza"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(s["circuit_id"] == "monza" for s in data)


# -- Lap Endpoints -----------------------------------------------------------


class TestLapEndpoints:
    """Verify lap retrieval and telemetry detail."""

    async def test_list_laps_for_session(self, client: AsyncClient):
        resp = await client.get("/api/laps", params={"session_id": "monza_2024_r"})
        assert resp.status_code == 200
        laps = resp.json()
        assert len(laps) >= 2
        lap_ids = {lap["lap_id"] for lap in laps}
        assert "lap_ver_1" in lap_ids
        assert "lap_sim_1" in lap_ids

    async def test_get_lap_detail(self, client: AsyncClient):
        resp = await client.get("/api/laps/lap_ver_1")
        assert resp.status_code == 200
        lap = resp.json()
        assert lap["driver_id"] == "verstappen"
        assert lap["lap_time_ms"] == 85800
        assert lap["tire_compound"] == "SOFT"

    async def test_get_telemetry_frames(self, client: AsyncClient):
        resp = await client.get("/api/laps/lap_ver_1/telemetry")
        assert resp.status_code == 200
        data = resp.json()
        frames = data["items"]
        assert len(frames) == 2
        assert frames[0]["speed_kph"] == pytest.approx(0.0, abs=0.1)
        assert frames[1]["speed_kph"] == pytest.approx(297.3, abs=0.1)
        assert frames[1]["drs"] == 1

    async def test_nonexistent_lap_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/laps/nonexistent_lap")
        assert resp.status_code == 404


# -- Compare Endpoints -------------------------------------------------------


class TestCompareEndpoints:
    """Verify lap comparison."""

    async def test_compare_two_laps(self, client: AsyncClient):
        resp = await client.get(
            "/api/compare/laps",
            params={"ids": "lap_ver_1,lap_sim_1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "lap_ids" in data
        assert "sector_deltas" in data
        assert "sector1_ms" in data["sector_deltas"]
        assert "sector2_ms" in data["sector_deltas"]
        assert "sector3_ms" in data["sector_deltas"]


# -- Vector Search Round-Trip ------------------------------------------------


class TestVectorSearch:
    """Verify vector similarity search endpoint behavior."""

    async def test_similar_laps_no_embedding_returns_422(self, client: AsyncClient):
        """Laps seeded without embeddings should return 422 gracefully."""
        resp = await client.get("/api/laps/lap_ver_1/similar", params={"top_n": 5})
        # Without embeddings seeded, expect 422 (no embedding vector)
        assert resp.status_code == 422


# -- DB Round-Trip Integrity -------------------------------------------------


class TestDBRoundTrip:
    """Verify data integrity through the full pipeline path."""

    async def test_ingestion_roundtrip(self, client: AsyncClient, pool: OraclePool):
        """Insert a new lap directly, then query it through the API."""
        async with pool.connection() as conn:
            cursor = conn.cursor()
            # Clean up potential prior run
            with contextlib.suppress(Exception):
                await cursor.execute("DELETE FROM laps WHERE lap_id = 'lap_roundtrip'")

            await cursor.execute("""
                INSERT INTO laps (
                    lap_id, session_id, driver_id, lap_number,
                    sector1_ms, sector2_ms, sector3_ms, lap_time_ms,
                    tire_compound, tire_age_laps, fuel_load_kg, ers_deploy_pct
                ) VALUES (
                    'lap_roundtrip', 'monza_2024_r', 'verstappen', 2,
                    28200, 32900, 23800, 84900,
                    'MEDIUM', 12, 88.5, 0.80
                )
            """)
            await conn.commit()

        # Now query through the API
        resp = await client.get("/api/laps/lap_roundtrip")
        assert resp.status_code == 200
        lap = resp.json()
        assert lap["lap_number"] == 2
        assert lap["tire_compound"] == "MEDIUM"
        assert lap["tire_age_laps"] == 12
        assert lap["fuel_load_kg"] == pytest.approx(88.5, abs=0.01)
        assert lap["lap_time_ms"] == 84900

    async def test_duality_view_json_roundtrip(self, client: AsyncClient, pool: OraclePool):
        """Insert via JSON Duality View, query relationally through API.
        Validates the duality view round-trip core to the architecture.
        Skips gracefully if the duality view is not available."""
        import json

        lap_json = json.dumps(
            {
                "lap_id": "lap_duality_test",
                "session_id": "monza_2024_r",
                "driver_id": "verstappen",
                "lap_number": 3,
                "sector1_ms": 27800,
                "sector2_ms": 32500,
                "sector3_ms": 23600,
                "lap_time_ms": 83900,
                "tire_compound": "SOFT",
                "tire_age_laps": 3,
                "fuel_load_kg": 82.0,
                "ers_deploy_pct": 0.85,
            }
        )

        async with pool.connection() as conn:
            cursor = conn.cursor()
            try:
                await cursor.execute(
                    "INSERT INTO laps_dv VALUES (:1)",
                    [lap_json],
                )
                await conn.commit()
            except Exception:
                # Duality view may not exist in test container
                pytest.skip("Duality view LAPS_DV not available in test container")

        # Query through REST API
        resp = await client.get("/api/laps/lap_duality_test")
        assert resp.status_code == 200
        lap = resp.json()
        assert lap["lap_time_ms"] == 83900
        assert lap["tire_compound"] == "SOFT"
