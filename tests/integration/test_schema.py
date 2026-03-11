import pytest

from api.services.oracle import OraclePool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

EXPECTED_TABLES = [
    "CIRCUITS",
    "DRIVERS",
    "TEAMS",
    "SESSIONS",
    "LAPS",
    "TELEMETRY_FRAMES",
    "CAR_SETUPS",
    "RACE_EVENTS",
    "PIT_STOPS",
    "PREDICTIONS",
]


async def test_all_tables_exist(pool: OraclePool):
    """All 10 tables must exist (created by conftest apply_ddl)."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT table_name FROM user_tables ORDER BY table_name"
        )
        rows = await cursor.fetchall()
        existing = {row[0] for row in rows}

    for table in EXPECTED_TABLES:
        assert table in existing, f"Table {table} not found. Existing: {existing}"


async def test_laps_has_vector_column(pool: OraclePool):
    """LAPS table must have a lap_embedding column of type VECTOR."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("""
            SELECT data_type FROM user_tab_columns
            WHERE table_name = 'LAPS' AND column_name = 'LAP_EMBEDDING'
        """)
        row = await cursor.fetchone()
        assert row is not None, "LAPS.LAP_EMBEDDING column not found"
        assert "VECTOR" in row[0].upper(), f"Expected VECTOR type, got {row[0]}"


async def test_sessions_has_json_column(pool: OraclePool):
    """SESSIONS.weather_data must accept JSON."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("""
            SELECT data_type FROM user_tab_columns
            WHERE table_name = 'SESSIONS' AND column_name = 'WEATHER_DATA'
        """)
        row = await cursor.fetchone()
        assert row is not None, "SESSIONS.WEATHER_DATA column not found"
        assert row[0] in ("JSON", "CLOB", "BLOB"), f"Unexpected type: {row[0]}"


async def test_telemetry_frames_fk(pool: OraclePool):
    """TELEMETRY_FRAMES.lap_id must be a FK to LAPS."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("""
            SELECT c.constraint_name
            FROM user_constraints c
            JOIN user_cons_columns cc ON c.constraint_name = cc.constraint_name
            WHERE c.constraint_type = 'R'
              AND c.table_name = 'TELEMETRY_FRAMES'
              AND cc.column_name = 'LAP_ID'
        """)
        row = await cursor.fetchone()
        assert row is not None, "No FK from TELEMETRY_FRAMES.LAP_ID to LAPS"
