"""Integration tests for vector similarity search.

Uses the session-scoped pool and DDL from conftest.py.
"""

import uuid

import numpy as np
import pytest

from api.services.oracle import OraclePool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


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
    v = v - (np.dot(v, b) / np.dot(b, b)) * b
    v = v / np.linalg.norm(v)
    return v.tolist()


async def _create_seed_data(pool: OraclePool) -> dict:
    """Create prerequisite circuit, driver, session for vector tests."""
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


async def test_insert_lap_with_vector(pool: OraclePool):
    """Insert a lap with a 384-dim embedding vector."""
    seed = await _create_seed_data(pool)

    lap_id = f"vec-lap-{uuid.uuid4().hex[:8]}"
    vec = _random_vector(384)
    vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """INSERT INTO laps (lap_id, session_id, driver_id, lap_number, lap_time_ms, lap_embedding)
               VALUES (:1, :2, :3, :4, :5, :6)""",
            [lap_id, seed["session_id"], seed["driver_id"], 1, 85000, vec_str],
        )
        await conn.commit()

        await cursor.execute(
            "SELECT lap_id FROM laps WHERE lap_id = :1 AND lap_embedding IS NOT NULL",
            [lap_id],
        )
        row = await cursor.fetchone()
        assert row is not None, "Lap with vector embedding not found"
        assert row[0] == lap_id


async def test_vector_similarity_search(pool: OraclePool):
    """Insert 3 laps with different vectors, query for similar ones -- nearest should rank first."""
    seed = await _create_seed_data(pool)

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
                [lap_id, seed["session_id"], seed["driver_id"], lap_num, 86000, vec_str],
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
            [query_vec_str, seed["session_id"]],
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 2, f"Expected >= 2 results, got {len(rows)}"

        # First result should be the base lap itself (distance ~0)
        assert rows[0][0] == lap_base
        assert float(rows[0][1]) < 0.01

        # Second should be similar, not the distant one
        assert rows[1][0] == lap_similar

        # Distant should have much larger distance
        if len(rows) >= 3:
            assert float(rows[2][1]) > float(rows[1][1])
