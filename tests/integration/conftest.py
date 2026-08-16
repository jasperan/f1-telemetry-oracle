"""Integration test fixtures -- real Oracle DB on localhost:1525/FREEPDB1.

Connects to the already-running Oracle container (from docker compose),
applies DDL, seeds fixture data, and provides an async OraclePool to tests.

The connection settings can be overridden via the ORACLE_TEST_DSN /
ORACLE_TEST_USER / ORACLE_TEST_PASSWORD environment variables (e.g. to
point at a dedicated CI container on another port).
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest_asyncio

from api.services.oracle import OraclePool

# Path to DDL scripts (same ones used by the real app)
DDL_DIR = Path(__file__).resolve().parent.parent.parent / "api" / "db"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Oracle container running via docker compose on port 1525
ORACLE_DSN = os.environ.get("ORACLE_TEST_DSN", "localhost:1525/FREEPDB1")
ORACLE_USER = os.environ.get("ORACLE_TEST_USER", "f1app")
ORACLE_PASSWORD = os.environ.get("ORACLE_TEST_PASSWORD", "f1app")


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
    """Apply schema DDL, optional DDL extensions, and seed fixture data."""
    # Apply the main schema
    schema_file = DDL_DIR / "schema.sql"
    if schema_file.exists():
        await pool.execute_script(schema_file.read_text())

    # Apply optional DDL extensions (duality views, spatial, vector)
    # These may fail in some Oracle configurations — don't block seeding
    for extra in ("duality_views.sql", "spatial.sql", "vector.sql"):
        extra_file = DDL_DIR / extra
        if extra_file.exists():
            with contextlib.suppress(Exception):
                await pool.execute_script(extra_file.read_text())

    # Seed fixture data
    fixture_sql = FIXTURES_DIR / "seed_integration.sql"
    if fixture_sql.exists():
        sql_text = fixture_sql.read_text()
        async with pool.connection() as conn:
            cursor = conn.cursor()
            for raw_stmt in sql_text.split(";"):
                # Strip leading comment lines from each segment
                lines = [
                    line
                    for line in raw_stmt.strip().splitlines()
                    if line.strip() and not line.strip().startswith("--")
                ]
                stmt = "\n".join(lines).strip()
                if stmt:
                    try:
                        await cursor.execute(stmt)
                    except Exception as exc:
                        # ORA-00001 = unique constraint (duplicate row) — skip
                        err = getattr(exc, "args", [None])[0]
                        if hasattr(err, "code") and err.code == 1:
                            continue
                        raise
            await conn.commit()
