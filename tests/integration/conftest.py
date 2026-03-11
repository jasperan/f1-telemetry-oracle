"""Integration test fixtures -- real Oracle DB on localhost:1525/FREEPDB1.

Connects to the already-running Oracle container (from docker compose),
applies DDL, seeds fixture data, and provides an async OraclePool to tests.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest_asyncio

from api.services.oracle import OraclePool

# Path to DDL scripts (same ones used by the real app)
DDL_DIR = Path(__file__).resolve().parent.parent.parent / "api" / "db"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Oracle container running via docker compose on port 1525
ORACLE_DSN = "localhost:1525/FREEPDB1"
ORACLE_USER = "f1app"
ORACLE_PASSWORD = "f1app"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def pool():
    """Create an async OraclePool pointing at the local Oracle container."""
    p = OraclePool(
        dsn=ORACLE_DSN,
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        min_connections=1,
        max_connections=4,
    )
    await p.open()
    yield p
    await p.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def apply_ddl(pool: OraclePool):
    """Apply schema DDL and seed fixture data into the test container."""
    # Apply the main schema
    schema_file = DDL_DIR / "schema.sql"
    if schema_file.exists():
        await pool.execute_script(schema_file.read_text())

    # Seed fixture data
    fixture_sql = FIXTURES_DIR / "seed_integration.sql"
    if fixture_sql.exists():
        sql_text = fixture_sql.read_text()
        async with pool.connection() as conn:
            cursor = conn.cursor()
            for stmt in sql_text.split(";"):
                stmt = stmt.strip()
                if stmt and not stmt.startswith("--"):
                    with contextlib.suppress(Exception):
                        await cursor.execute(stmt)
            await conn.commit()
