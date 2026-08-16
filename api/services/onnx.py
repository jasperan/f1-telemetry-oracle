"""In-database ONNX scoring helpers.

Oracle 23ai/26ai runs ONNX models inside the database. These helpers
invoke them with the SQL prediction operators so that ML inference —
tire grip, remaining tire life, text embeddings — happens in the DB,
not in Python.

Models are imported with DBMS_DATA_MINING.IMPORT_ONNX_MODEL by
``scripts/load_onnx_models.py``. Each helper degrades gracefully:
if the model is not loaded (or scoring fails), the caller falls back
to its heuristic path.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Model names registered in Oracle (see scripts/load_onnx_models.py)
MODEL_TIRE_GRIP = "TIRE_GRIP_MODEL"
MODEL_TIRE_LAPS = "TIRE_LAPS_MODEL"
MODEL_EMBEDDING = "ALL_MINILM_L12_V2"

# Compound -> integer encoding used by the ONNX tire models
_COMPOUND_ENCODING: dict[str, int] = {
    "SOFT": 0,
    "MEDIUM": 1,
    "HARD": 2,
    "INTERMEDIATE": 3,
    "INTER": 3,
    "WET": 4,
}


def encode_compound(compound: str) -> int:
    """Map a tire compound string to the ONNX model's integer encoding.

    Args:
        compound: Tire compound name (case-insensitive).

    Returns:
        Integer encoding (0..4); unknown compounds map to SOFT (0).
    """
    return _COMPOUND_ENCODING.get(compound.strip().upper(), 0)


async def model_exists(pool, model_name: str) -> bool:
    """Check whether an ONNX model is loaded in the current schema.

    Args:
        pool: OraclePool instance.
        model_name: Model name (case-insensitive).

    Returns:
        True if the model exists, False otherwise.
    """
    try:
        async with pool.connection() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT COUNT(*) FROM user_mining_models WHERE UPPER(model_name) = UPPER(:name)",
                {"name": model_name},
            )
            row = await cursor.fetchone()
            return bool(row and row[0] > 0)
    except Exception as exc:  # pragma: no cover - DB unavailable
        logger.warning("model_exists(%s) failed: %s", model_name, exc)
        return False


async def score_regression(
    pool,
    model_name: str,
    inputs: dict[str, float | int],
) -> float | None:
    """Score a single-output regression ONNX model in the database.

    Args:
        pool: OraclePool instance.
        model_name: Registered ONNX model name.
        inputs: Mapping of input column name -> numeric value. The names
            must match the model's declared input columns.

    Returns:
        The predicted scalar, or None if the model is missing / scoring fails.
    """
    if not inputs:
        return None

    binds: dict[str, object] = {}
    using_parts: list[str] = []
    for i, (col, value) in enumerate(inputs.items()):
        bind = f"b{i}"
        using_parts.append(f":{bind} AS {col}")
        binds[bind] = value

    using_clause = ", ".join(using_parts)
    sql = f"SELECT PREDICTION({model_name} USING {using_clause}) FROM dual"

    try:
        async with pool.connection() as conn:
            cursor = conn.cursor()
            await cursor.execute(sql, binds)
            row = await cursor.fetchone()
            value = row[0] if row else None
            return float(value) if value is not None else None
    except Exception as exc:
        logger.warning("score_regression(%s) failed: %s", model_name, exc)
        return None


async def embed_text(pool, model_name: str, text: str) -> list[float] | None:
    """Generate a text embedding inside the database with VECTOR_EMBEDDING().

    Args:
        pool: OraclePool instance.
        model_name: Registered ONNX embedding model (e.g. ALL_MINILM_L12_V2).
        text: Input text to embed.

    Returns:
        Embedding vector as a list of floats, or None on failure.
    """
    try:
        async with pool.connection() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                f"SELECT VECTOR_EMBEDDING({model_name} USING :text AS DATA) FROM dual",
                {"text": text},
            )
            row = await cursor.fetchone()
            if row is None or row[0] is None:
                return None
            return list(row[0])
    except Exception as exc:
        logger.warning("embed_text(%s) failed: %s", model_name, exc)
        return None
