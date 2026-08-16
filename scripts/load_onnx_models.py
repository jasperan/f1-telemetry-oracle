"""Load ONNX models into Oracle Database for in-database inference.

Trains two single-output regression models (tire grip + remaining laps)
on synthetic tire data, exports them to ONNX, and loads them into Oracle
via DBMS_DATA_MINING.IMPORT_ONNX_MODEL. Also loads the Oracle-augmented
all-MiniLM-L12-v2 text embedding model so VECTOR_EMBEDDING() works in SQL.

Oracle 23ai regression ONNX models must expose a *single* output tensor,
so the two targets (grip_percent, laps_remaining) ship as two models:
  TIRE_GRIP_MODEL  -> grip_percent
  TIRE_LAPS_MODEL  -> laps_remaining

Usage:
    python -m scripts.load_onnx_models
    python -m scripts.load_onnx_models --export-only
    python -m scripts.load_onnx_models --no-embedding

The tire models predict, from [tire_age_laps, track_temp_c, fuel_load_kg,
compound_encoded (0=soft..4=wet)]:
  - grip_percent (0-100): current tire grip level
  - laps_remaining (0-N): estimated laps before performance cliff
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"

# Oracle-augmented MiniLM embedding model (bundles tokenization + pooling)
EMBEDDING_MODEL_NAME = "ALL_MINILM_L12_V2"
EMBEDDING_ZIP_URL = (
    "https://adwc4pm.objectstorage.us-ashburn-1.oci.customer-oci.com"
    "/p/TtH6hL2y25EypZ0-rrczRZ1aXp7v1ONbRBfCiT-BDBN8WLKQ3lgyW6RxCfIFLdA6"
    "/n/adwc4pm/b/OML-ai-models/o/all_MiniLM_L12_v2_augmented.zip"
)
EMBEDDING_ZIP = MODELS_DIR / "all_MiniLM_L12_v2_augmented.zip"
EMBEDDING_ONNX = MODELS_DIR / "all_MiniLM_L12_v2.onnx"

TIRE_FEATURES = ["TIRE_AGE_LAPS", "TRACK_TEMP_C", "FUEL_LOAD_KG", "COMPOUND_ENCODED"]


def _synthetic_tire_dataset(n_samples: int = 5000, random_state: int = 42) -> tuple:
    """Generate synthetic tire degradation data matching F1 physics.

    Returns:
        (X feature matrix, grip target, laps_remaining target).
    """
    rng = np.random.RandomState(random_state)

    tire_age = rng.randint(1, 45, size=n_samples).astype(float)
    track_temp = rng.uniform(15.0, 55.0, size=n_samples)
    fuel_load = rng.uniform(5.0, 110.0, size=n_samples)
    compound = rng.randint(0, 5, size=n_samples).astype(float)

    x = np.column_stack([tire_age, track_temp, fuel_load, compound])

    # Compound-specific base life (soft=25, medium=35, hard=45, inter=30, wet=28)
    base_life = np.array([25, 35, 45, 30, 28], dtype=float)
    compound_life = base_life[compound.astype(int)]

    # Temperature + fuel effects
    temp_factor = 1.0 + (track_temp - 30.0) * 0.005
    fuel_factor = 1.0 - (fuel_load - 50.0) * 0.001

    wear_fraction = (tire_age / compound_life) * temp_factor * fuel_factor
    wear_fraction = np.clip(wear_fraction, 0.0, 1.2)

    grip = np.clip((1.0 - wear_fraction) * 100.0, 0.0, 100.0)
    grip += rng.randn(n_samples) * 2.0  # noise
    grip = np.clip(grip, 0.0, 100.0)

    laps_remaining = np.clip(compound_life - tire_age, 0, 60)
    laps_remaining = (laps_remaining / (temp_factor * fuel_factor)).astype(float)
    laps_remaining += rng.randn(n_samples) * 1.5
    laps_remaining = np.clip(laps_remaining, 0, 60)

    return x, grip, laps_remaining


def build_tire_degradation_models(
    n_samples: int = 5000,
    random_state: int = 42,
) -> tuple:
    """Train two single-output RandomForest tire degradation models.

    Args:
        n_samples: Number of synthetic training samples.
        random_state: Seed for reproducibility.

    Returns:
        Tuple of ((grip_model, laps_model), feature_names).
    """
    from sklearn.ensemble import RandomForestRegressor

    x, grip, laps = _synthetic_tire_dataset(n_samples, random_state)

    grip_model = RandomForestRegressor(
        n_estimators=50, max_depth=10, random_state=random_state
    )
    grip_model.fit(x, grip)

    laps_model = RandomForestRegressor(
        n_estimators=50, max_depth=10, random_state=random_state
    )
    laps_model.fit(x, laps)

    logger.info(
        "Trained tire degradation models on %d synthetic samples", n_samples
    )
    return (grip_model, laps_model), TIRE_FEATURES


def export_to_onnx(model, feature_names: list[str], output_path: str) -> str:
    """Export a single sklearn model to ONNX format.

    Args:
        model: Trained sklearn regressor.
        feature_names: Input feature names.
        output_path: Path to write the .onnx file.

    Returns:
        The output_path.
    """
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    initial_type = [("X", FloatTensorType([None, len(feature_names)]))]

    onnx_model = convert_sklearn(
        model,
        initial_types=initial_type,
        target_opset=15,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(onnx_model.SerializeToString())

    file_size = Path(output_path).stat().st_size
    logger.info("Exported ONNX model to %s (%d bytes)", output_path, file_size)
    return output_path


def _regression_metadata(feature_names: list[str]) -> str:
    """Metadata JSON for a single-output regression ONNX model (23ai+).

    The ONNX input tensor is named 'X' (see export_to_onnx), so the
    metadata maps tensor name X -> feature columns explicitly.
    """
    return json.dumps(
        {
            "function": "regression",
            "input": {"X": feature_names},
        }
    )


async def load_model_into_oracle(pool, model_path: str, model_name: str, metadata: str) -> None:
    """Load an ONNX model into Oracle Database.

    Uses DBMS_DATA_MINING.IMPORT_ONNX_MODEL to store the model for
    in-database inference via SQL.

    Args:
        pool: OraclePool instance.
        model_path: Path to the .onnx file.
        model_name: Name to register the model under in Oracle.
        metadata: JSON metadata describing function/inputs/outputs.
    """
    with open(model_path, "rb") as f:
        onnx_bytes = f.read()

    async with pool.connection() as conn:
        cursor = conn.cursor()

        # Drop existing model if present
        try:
            await cursor.execute(
                "BEGIN DBMS_DATA_MINING.DROP_MODEL(:1); END;",
                [model_name],
            )
            logger.info("Dropped existing model %s", model_name)
        except Exception:
            pass  # Model doesn't exist yet

        # Load the ONNX model
        await cursor.execute(
            """
            DECLARE
                v_blob BLOB;
            BEGIN
                v_blob := :model_bytes;
                DBMS_DATA_MINING.IMPORT_ONNX_MODEL(
                    :model_name,
                    v_blob,
                    JSON(:metadata)
                );
            END;
            """,
            {
                "model_bytes": onnx_bytes,
                "model_name": model_name,
                "metadata": metadata,
            },
        )
        await conn.commit()

    logger.info("Loaded ONNX model %s into Oracle (%d bytes)", model_name, len(onnx_bytes))


async def ensure_embedding_onnx() -> Path:
    """Download + extract the Oracle-augmented MiniLM ONNX model if needed.

    Returns:
        Path to the extracted .onnx file.
    """
    if EMBEDDING_ONNX.exists():
        logger.info("Embedding ONNX already present: %s", EMBEDDING_ONNX)
        return EMBEDDING_ONNX

    EMBEDDING_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if not EMBEDDING_ZIP.exists():
        logger.info("Downloading augmented all-MiniLM-L12-v2 ONNX (~117 MB)...")
        urllib.request.urlretrieve(EMBEDDING_ZIP_URL, EMBEDDING_ZIP)
        logger.info("Download complete.")

    with zipfile.ZipFile(EMBEDDING_ZIP) as zf:
        zf.extractall(MODELS_DIR)

    if not EMBEDDING_ONNX.exists():
        raise FileNotFoundError(f"Extracted ONNX not found under {MODELS_DIR}")
    return EMBEDDING_ONNX


async def load_embedding_model(pool) -> None:
    """Load the text embedding model for in-database VECTOR_EMBEDDING()."""
    onnx_path = await ensure_embedding_onnx()
    metadata = json.dumps(
        {
            "function": "embedding",
            "embeddingOutput": "embedding",
            "input": {"input": ["DATA"]},
        }
    )
    await load_model_into_oracle(pool, str(onnx_path), EMBEDDING_MODEL_NAME, metadata)


async def main() -> None:
    """CLI entry point: train, export, and load all ONNX models."""
    parser = argparse.ArgumentParser(description="Train and load ONNX models into Oracle")
    parser.add_argument("--export-only", action="store_true", help="Export ONNX without loading into Oracle")
    parser.add_argument("--no-embedding", action="store_true", help="Skip the text embedding model")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from api.config import Settings
    from api.services.oracle import OraclePool

    settings = Settings()

    (grip_model, laps_model), features = build_tire_degradation_models()

    grip_path = str(MODELS_DIR / "tire_grip_v1.onnx")
    laps_path = str(MODELS_DIR / "tire_laps_v1.onnx")
    export_to_onnx(grip_model, features, grip_path)
    export_to_onnx(laps_model, features, laps_path)

    if args.export_only:
        logger.info("Export-only mode; skipping database load.")
        return

    pool = OraclePool(
        dsn=settings.oracle_dsn,
        user=settings.oracle_user,
        password=settings.oracle_password,
    )
    await pool.open()

    try:
        await load_model_into_oracle(pool, grip_path, "TIRE_GRIP_MODEL", _regression_metadata(features))
        await load_model_into_oracle(pool, laps_path, "TIRE_LAPS_MODEL", _regression_metadata(features))
        if not args.no_embedding:
            await load_embedding_model(pool)
    finally:
        await pool.close()

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
