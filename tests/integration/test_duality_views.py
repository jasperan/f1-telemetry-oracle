"""Integration tests for JSON Relational Duality Views.

Uses the session-scoped pool and DDL from conftest.py.
"""

import json
import uuid

import pytest

from api.services.oracle import OraclePool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_lap_duality_view_insert_and_read(pool: OraclePool):
    """Insert JSON through lap_dv, read back relationally from laps table."""
    circuit_id = f"dv-circuit-{uuid.uuid4().hex[:8]}"
    driver_id = f"dv-driver-{uuid.uuid4().hex[:8]}"
    session_id = f"dv-sess-{uuid.uuid4().hex[:8]}"
    lap_id = f"dv-lap-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()

        # Insert prerequisite rows
        await cursor.execute(
            "INSERT INTO circuits (circuit_id, circuit_name, country) VALUES (:1, :2, :3)",
            [circuit_id, "Monza", "Italy"],
        )
        await cursor.execute(
            "INSERT INTO drivers (driver_id, code, first_name, last_name, nationality, is_sim_player) VALUES (:1, :2, :3, :4, :5, :6)",
            [driver_id, "TST", "Test", "Driver", "Testland", 0],
        )
        await cursor.execute(
            "INSERT INTO sessions (session_id, circuit_id, session_type, source, season) VALUES (:1, :2, :3, :4, :5)",
            [session_id, circuit_id, "race", "sim", 2025],
        )
        await conn.commit()

        # Insert via duality view
        lap_json = json.dumps({
            "_id": lap_id,
            "session_id": session_id,
            "driver_id": driver_id,
            "lap_number": 7,
            "sector1_ms": 28500,
            "sector2_ms": 33200,
            "sector3_ms": 24100,
            "lap_time_ms": 85800,
            "tire_compound": "SOFT",
            "tire_age_laps": 3,
            "is_valid": 1,
        })

        try:
            await cursor.execute("INSERT INTO lap_dv VALUES (:1)", [lap_json])
            await conn.commit()
        except Exception:
            pytest.skip("Duality view LAP_DV not available in test container")

        # Read back relationally
        await cursor.execute(
            "SELECT lap_id, lap_number, lap_time_ms, tire_compound FROM laps WHERE lap_id = :1",
            [lap_id],
        )
        row = await cursor.fetchone()
        assert row is not None, "Lap not found in relational table after duality view insert"
        assert row[0] == lap_id
        assert row[1] == 7
        assert row[2] == 85800
        assert row[3] == "SOFT"


async def test_session_duality_view_read_json(pool: OraclePool):
    """Read a session through session_dv and get nested JSON with circuit info."""
    circuit_id = f"dv2-circuit-{uuid.uuid4().hex[:8]}"
    session_id = f"dv2-sess-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()

        await cursor.execute(
            "INSERT INTO circuits (circuit_id, circuit_name, country) VALUES (:1, :2, :3)",
            [circuit_id, "Monza DV", "Italy"],
        )
        await cursor.execute(
            "INSERT INTO sessions (session_id, circuit_id, session_type, source, season) VALUES (:1, :2, :3, :4, :5)",
            [session_id, circuit_id, "qualifying", "openf1", 2024],
        )
        await conn.commit()

        try:
            await cursor.execute(
                'SELECT data FROM session_dv s WHERE s.data."_id" = :1',
                [session_id],
            )
        except Exception:
            pytest.skip("Duality view SESSION_DV not available in test container")

        row = await cursor.fetchone()
        assert row is not None, "Session not found in duality view"

        doc = row[0] if isinstance(row[0], dict) else json.loads(str(row[0]))
        assert doc["_id"] == session_id
        assert doc["session_type"] == "qualifying"
        assert doc["circuit"]["circuit_name"] == "Monza DV"
