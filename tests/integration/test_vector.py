import uuid

import numpy as np
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

    schema_sql = open("api/db/schema.sql").read()
    await p.execute_script(schema_sql)

    yield p
    await p.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seed_for_vector(pool: OraclePool):
    """Create a circuit, driver, and session so we can insert laps."""
    cid = f"vec-circuit-{uuid.uuid4().hex[:8]}"
    did = f"vec-driver-{uuid.uuid4().hex[:8]}"
    sid = f"vec-session-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "INSERT INTO circuits (circuit_id, circuit_name, country) VALUES (:1, :2, :3)",
            [cid, "Vector Test Circuit", "Testland"],
        )
        await cursor.execute(
            "INSERT INTO drivers (driver_id, code, first_name, last_name, is_sim_player) VALUES (:1, :2, :3, :4, :5)",
            [did, "VEC", "Vector", "Tester", 0],
        )
        await cursor.execute(
            "INSERT INTO sessions (session_id, circuit_id, session_type, source) VALUES (:1, :2, :3, :4)",
            [sid, cid, "race", "sim"],
        )
        await conn.commit()

    return {"circuit_id": cid, "driver_id": did, "session_id": sid}


def _random_vector(dim: int = 384, seed: int = 42) -> list[float]:
    """Generate a reproducible random unit vector."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    v = v / np.linalg.norm(v)
    return v.tolist()


def _similar_vector(base: list[float], noise: float = 0.05, seed: int = 99) -> list[float]:
    """Slightly perturb a vector to make it similar but not identical."""
    rng = np.random.default_rng(seed)
    arr = np.array(base, dtype=np.float32)
    arr += rng.standard_normal(len(base)).astype(np.float32) * noise
    arr = arr / np.linalg.norm(arr)
    return arr.tolist()


def _orthogonal_vector(base: list[float], seed: int = 7) -> list[float]:
    """Generate a vector roughly orthogonal to base."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(len(base)).astype(np.float32)
    b = np.array(base, dtype=np.float32)
    # Remove component along base
    v = v - (np.dot(v, b) / np.dot(b, b)) * b
    v = v / np.linalg.norm(v)
    return v.tolist()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_insert_lap_with_vector(pool: OraclePool, seed_for_vector: dict):
    """Insert a lap with a 384-dim embedding vector."""
    vector_sql = open("api/db/vector.sql").read()
    await pool.execute_script(vector_sql)

    lap_id = f"vec-lap-{uuid.uuid4().hex[:8]}"
    vec = _random_vector(384)
    vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """INSERT INTO laps (lap_id, session_id, driver_id, lap_number, lap_time_ms, lap_embedding)
               VALUES (:1, :2, :3, :4, :5, :6)""",
            [lap_id, seed_for_vector["session_id"], seed_for_vector["driver_id"], 1, 85000, vec_str],
        )
        await conn.commit()

        await cursor.execute(
            "SELECT lap_id FROM laps WHERE lap_id = :1 AND lap_embedding IS NOT NULL",
            [lap_id],
        )
        row = await cursor.fetchone()
        assert row is not None, "Lap with vector embedding not found"
        assert row[0] == lap_id


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_vector_similarity_search(pool: OraclePool, seed_for_vector: dict):
    """Insert 3 laps with different vectors, query for similar ones — nearest should rank first."""
    base_vec = _random_vector(384, seed=100)
    similar_vec = _similar_vector(base_vec, noise=0.05, seed=101)
    distant_vec = _orthogonal_vector(base_vec, seed=102)

    lap_base = f"vec-base-{uuid.uuid4().hex[:8]}"
    lap_similar = f"vec-similar-{uuid.uuid4().hex[:8]}"
    lap_distant = f"vec-distant-{uuid.uuid4().hex[:8]}"

    async with pool.connection() as conn:
        cursor = conn.cursor()

        for lap_id, vec, lap_num in [
            (lap_base, base_vec, 10),
            (lap_similar, similar_vec, 11),
            (lap_distant, distant_vec, 12),
        ]:
            vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
            await cursor.execute(
                """INSERT INTO laps (lap_id, session_id, driver_id, lap_number, lap_time_ms, lap_embedding)
                   VALUES (:1, :2, :3, :4, :5, :6)""",
                [lap_id, seed_for_vector["session_id"], seed_for_vector["driver_id"], lap_num, 86000, vec_str],
            )
        await conn.commit()

        # Search for laps similar to base_vec
        query_vec_str = "[" + ",".join(f"{v:.8f}" for v in base_vec) + "]"
        await cursor.execute(
            """
            SELECT lap_id, VECTOR_DISTANCE(lap_embedding, :1, COSINE) AS dist
            FROM laps
            WHERE lap_embedding IS NOT NULL
              AND session_id = :2
              AND lap_number >= 10
            ORDER BY dist ASC
            FETCH FIRST 3 ROWS ONLY
            """,
            [query_vec_str, seed_for_vector["session_id"]],
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 2, f"Expected >= 2 results, got {len(rows)}"

        # First result should be the base lap itself (distance ~0)
        assert rows[0][0] == lap_base
        assert float(rows[0][1]) < 0.01  # near-zero cosine distance

        # Second should be similar, not the distant one
        assert rows[1][0] == lap_similar

        # Distant should have much larger distance
        if len(rows) >= 3:
            assert float(rows[2][1]) > float(rows[1][1])
