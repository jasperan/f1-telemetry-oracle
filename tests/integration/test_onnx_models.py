"""Integration tests — in-database ONNX models.

Verifies the models loaded by scripts/load_onnx_models.py are registered
in Oracle and score correctly via the SQL prediction operators.
"""

from __future__ import annotations

import pytest

from api.services.onnx import (
    MODEL_EMBEDDING,
    MODEL_TIRE_GRIP,
    MODEL_TIRE_LAPS,
    embed_text,
    model_exists,
    score_regression,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_tire_models_registered(pool):
    """The two single-output tire regression models must be present."""
    assert await model_exists(pool, MODEL_TIRE_GRIP), "Run: python -m scripts.load_onnx_models"
    assert await model_exists(pool, MODEL_TIRE_LAPS)


async def test_tire_grip_scoring(pool):
    """PREDICTION(TIRE_GRIP_MODEL ...) returns a plausible 0-100 grip."""
    grip = await score_regression(
        pool,
        MODEL_TIRE_GRIP,
        {
            "TIRE_AGE_LAPS": 12,
            "TRACK_TEMP_C": 38.0,
            "FUEL_LOAD_KG": 55.0,
            "COMPOUND_ENCODED": 0,  # SOFT
        },
    )
    assert grip is not None
    assert 0.0 <= grip <= 100.0


async def test_tire_laps_scoring(pool):
    """PREDICTION(TIRE_LAPS_MODEL ...) returns a non-negative remaining life."""
    laps = await score_regression(
        pool,
        MODEL_TIRE_LAPS,
        {
            "TIRE_AGE_LAPS": 12,
            "TRACK_TEMP_C": 38.0,
            "FUEL_LOAD_KG": 55.0,
            "COMPOUND_ENCODED": 0,
        },
    )
    assert laps is not None
    assert laps >= 0.0
    # Old softs at high temperature must have less life than fresh ones
    fresh = await score_regression(
        pool,
        MODEL_TIRE_LAPS,
        {
            "TIRE_AGE_LAPS": 1,
            "TRACK_TEMP_C": 38.0,
            "FUEL_LOAD_KG": 55.0,
            "COMPOUND_ENCODED": 0,
        },
    )
    assert fresh is not None
    assert fresh > laps


async def test_embedding_model_registered(pool):
    """The MiniLM embedding model must be loadable for VECTOR_EMBEDDING()."""
    assert await model_exists(pool, MODEL_EMBEDDING), "Run: python -m scripts.load_onnx_models"


async def test_in_database_embedding(pool):
    """VECTOR_EMBEDDING() generates a 384-dim vector inside Oracle."""
    vec = await embed_text(pool, MODEL_EMBEDDING, "tire strategy pit window soft compound")
    assert vec is not None
    assert len(vec) == 384
    assert any(abs(v) > 0 for v in vec), "Embedding should not be all zeros"


async def test_semantic_similarity_in_db(pool):
    """Two related texts are closer than two unrelated texts."""
    embed_a = await embed_text(pool, MODEL_EMBEDDING, "how much tire life is left on softs")
    embed_b = await embed_text(pool, MODEL_EMBEDDING, "tire degradation and pit stops")
    embed_c = await embed_text(pool, MODEL_EMBEDDING, "the history of the roman empire")

    async with pool.connection() as conn:
        cursor = conn.cursor()
        for label, emb, other in [
            ("ab", embed_a, embed_b),
            ("ac", embed_a, embed_c),
        ]:
            vec_str = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
            other_str = "[" + ",".join(f"{v:.6f}" for v in other) + "]"
            await cursor.execute(
                "SELECT VECTOR_DISTANCE(:1, :2, COSINE) FROM dual",
                [vec_str, other_str],
            )
            dist = (await cursor.fetchone())[0]
            if label == "ab":
                dist_ab = dist
            else:
                dist_ac = dist

    assert dist_ab < dist_ac, "Related texts must be closer than unrelated texts"
