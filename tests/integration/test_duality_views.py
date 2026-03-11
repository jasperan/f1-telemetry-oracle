import json
import uuid

import pytest
import pytest_asyncio

from api.services.oracle import OraclePool


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = OraclePool(
        dsn="localhost:1525/FREEPDB1",
        user="f1app",
        password="f1app",
        min_connections=1,
        max_connections=4,
    )
    await p.open()

    # Ensure base tables exist
    schema_sql = open("api/db/schema.sql").read()
    await p.execute_script(schema_sql)

    yield p
    await p.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seed_data(pool: OraclePool):
    """Insert prerequisite rows so FKs are satisfied for duality view inserts."""
    circuit_id = f"test-circuit-{uuid.uuid4().hex[:8]}"
    driver_id = f"test-driver-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """INSERT INTO circuits (circuit_id, circuit_name, country)
               VALUES (:1, :2, :3)""",
            [circuit_id, "Monza", "Italy"],
        )
        await cursor.execute(
            """INSERT INTO drivers (driver_id, code, first_name, last_name, nationality, is_sim_player)
               VALUES (:1, :2, :3, :4, :5, :6)""",
            [driver_id, "TST", "Test", "Driver", "Testland", 0],
        )
        await conn.commit()

    return {"circuit_id": circuit_id, "driver_id": driver_id}


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_lap_duality_view_insert_and_read(pool: OraclePool, seed_data: dict):
    """Insert JSON through lap_dv, read back relationally from laps table."""
    duality_sql = open("api/db/duality_views.sql").read()
    await pool.execute_script(duality_sql)

    session_id = f"test-sess-{uuid.uuid4().hex[:8]}"
    lap_id = f"test-lap-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()

        # Insert prerequisite session
        await cursor.execute(
            """INSERT INTO sessions (session_id, circuit_id, session_type, source, season)
               VALUES (:1, :2, :3, :4, :5)""",
            [session_id, seed_data["circuit_id"], "race", "sim", 2025],
        )
        await conn.commit()

        # Insert via duality view — _id maps to lap_id (PK)
        lap_json = json.dumps(
            {
                "_id": lap_id,
                "session_id": session_id,
                "driver_id": seed_data["driver_id"],
                "lap_number": 7,
                "sector1_ms": 28500,
                "sector2_ms": 33200,
                "sector3_ms": 24100,
                "lap_time_ms": 85800,
                "tire_compound": "SOFT",
                "tire_age_laps": 3,
                "is_valid": 1,
            }
        )

        await cursor.execute(
            "INSERT INTO lap_dv VALUES (:1)",
            [lap_json],
        )
        await conn.commit()

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


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_session_duality_view_read_json(pool: OraclePool, seed_data: dict):
    """Read a session through session_dv and get nested JSON with circuit info."""
    session_id = f"test-sess-dv-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()

        await cursor.execute(
            """INSERT INTO sessions (session_id, circuit_id, session_type, source, season)
               VALUES (:1, :2, :3, :4, :5)""",
            [session_id, seed_data["circuit_id"], "qualifying", "openf1", 2024],
        )
        await conn.commit()

        # Read through duality view — oracledb returns dict for JSON duality view data column
        await cursor.execute(
            'SELECT data FROM session_dv s WHERE s.data."_id" = :1',
            [session_id],
        )
        row = await cursor.fetchone()
        assert row is not None, "Session not found in duality view"

        # oracledb auto-parses duality view data as dict
        doc = row[0] if isinstance(row[0], dict) else json.loads(str(row[0]))
        assert doc["_id"] == session_id
        assert doc["session_type"] == "qualifying"
        assert doc["circuit"]["circuit_name"] == "Monza"
