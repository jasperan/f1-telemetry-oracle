import oracledb
import pytest
import pytest_asyncio

from api.services.oracle import OraclePool


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    """Create a pool pointing at the local Oracle 23ai container."""
    p = OraclePool(
        dsn="localhost:1525/FREEPDB1",
        user="f1app",
        password="f1app",
        min_connections=1,
        max_connections=4,
    )
    await p.open()
    yield p
    await p.close()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_connect_and_check_version(pool: OraclePool):
    """Verify we can connect and the database identifies as Oracle."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("SELECT banner_full FROM v$version WHERE ROWNUM = 1")
        row = await cursor.fetchone()
        assert row is not None
        banner = row[0]
        assert "Oracle" in banner


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_pool_returns_multiple_connections(pool: OraclePool):
    """Pool hands out independent connections."""
    async with pool.connection() as conn1:
        async with pool.connection() as conn2:
            cur1 = conn1.cursor()
            cur2 = conn2.cursor()
            await cur1.execute("SELECT 1 FROM dual")
            await cur2.execute("SELECT 2 FROM dual")
            r1 = await cur1.fetchone()
            r2 = await cur2.fetchone()
            assert r1[0] == 1
            assert r2[0] == 2
