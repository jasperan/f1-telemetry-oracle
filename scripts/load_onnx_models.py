"""Load ONNX models into Oracle Database for in-database inference.

Trains a simple tire degradation model on synthetic data, exports it
to ONNX format, and loads it into Oracle via DBMS_DATA_MINING.IMPORT_ONNX_MODEL.

Usage:
    python -m scripts.load_onnx_models
    python -m scripts.load_onnx_models --export-only

The model predicts:
  - grip_percent (0-100): current tire grip level
  - laps_remaining (0-N): estimated laps before performance cliff

From inputs:
  - tire_age_laps: number of laps on current tires
  - track_temp_c: track surface temperature
  - fuel_load_kg: current fuel load
  - compound_encoded: 0=soft, 1=medium, 2=hard, 3=intermediate, 4=wet
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def build_tire_degradation_model(
    n_samples: int = 5000,
    random_state: int = 42,
) -> tuple:
    """Train a RandomForest on synthetic tire degradation data.

    Args:
        n_samples: Number of synthetic training samples.
        random_state: Seed for reproducibility.

    Returns:
        Tuple of (trained MultiOutputRegressor, feature_names list).
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor

    rng = np.random.RandomState(random_state)

    feature_names = [
        "tire_age_laps",
        "track_temp_c",
        "fuel_load_kg",
        "compound_encoded",
    ]

    # Generate synthetic features
    tire_age = rng.randint(1, 45, size=n_samples).astype(float)
    track_temp = rng.uniform(15.0, 55.0, size=n_samples)
    fuel_load = rng.uniform(5.0, 110.0, size=n_samples)
    compound = rng.randint(0, 5, size=n_samples).astype(float)

    X = np.column_stack([tire_age, track_temp, fuel_load, compound])

    # Compound-specific base life (soft=25, medium=35, hard=45, inter=30, wet=28)
    base_life = np.array([25, 35, 45, 30, 28], dtype=float)
    compound_life = base_life[compound.astype(int)]

    # Synthetic targets
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

    y = np.column_stack([grip, laps_remaining])

    model = MultiOutputRegressor(
        RandomForestRegressor(n_estimators=50, max_depth=10, random_state=random_state)
    )
    model.fit(X, y)

    logger.info("Trained tire degradation model on %d samples", n_samples)
    return model, feature_names


def export_to_onnx(
    model,
    feature_names: list[str],
    output_path: str,
) -> str:
    """Export a sklearn model to ONNX format.

    Args:
        model: Trained sklearn model.
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


async def load_model_into_oracle(
    pool,
    model_path: str,
    model_name: str = "TIRE_DEGRADATION_V1",
) -> None:
    """Load an ONNX model into Oracle Database.

    Uses DBMS_DATA_MINING.IMPORT_ONNX_MODEL to store the model
    in the database for in-database inference via SQL.

    Args:
        pool: OraclePool instance.
        model_path: Path to the .onnx file.
        model_name: Name to register the model under in Oracle.
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
        # DBMS_DATA_MINING.IMPORT_ONNX_MODEL expects a BLOB
        await cursor.execute(
            """
            DECLARE
                v_blob BLOB;
            BEGIN
                v_blob := :model_bytes;
                DBMS_DATA_MINING.IMPORT_ONNX_MODEL(
                    :model_name,
                    v_blob,
                    JSON('{"function": "regression",
                           "inputColumns": ["TIRE_AGE_LAPS", "TRACK_TEMP_C",
                                            "FUEL_LOAD_KG", "COMPOUND_ENCODED"],
                           "outputColumns": ["GRIP_PERCENT", "LAPS_REMAINING"]}')
                );
            END;
            """,
            {
                "model_bytes": onnx_bytes,
                "model_name": model_name,
            },
        )
        await conn.commit()

    logger.info("Loaded ONNX model %s into Oracle (%d bytes)", model_name, len(onnx_bytes))


async def main():
    """CLI entry point: train, export, and load the tire degradation model."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from api.config import Settings
    from api.services.oracle import OraclePool

    settings = Settings()

    model, feature_names = build_tire_degradation_model()

    onnx_path = str(Path(__file__).parent / "models" / "tire_degradation_v1.onnx")
    export_to_onnx(model, feature_names, onnx_path)

    pool = OraclePool(
        dsn=settings.oracle_dsn,
        user=settings.oracle_user,
        password=settings.oracle_password,
    )
    await pool.open()

    try:
        await load_model_into_oracle(pool, onnx_path)
        logger.info("Successfully loaded tire degradation model into Oracle")
    finally:
        await pool.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Train and load ONNX models into Oracle")
    parser.add_argument("--export-only", action="store_true", help="Export ONNX without loading into Oracle")
    args = parser.parse_args()

    if args.export_only:
        model, feature_names = build_tire_degradation_model()
        onnx_path = str(Path(__file__).parent / "models" / "tire_degradation_v1.onnx")
        export_to_onnx(model, feature_names, onnx_path)
    else:
        asyncio.run(main())
