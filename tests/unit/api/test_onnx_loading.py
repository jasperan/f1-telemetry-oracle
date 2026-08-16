"""Tests for in-database ONNX model loading.

Verifies:
- Synthetic tire degradation models train and export to ONNX
- ONNX model files are valid and produce correct output shape
- Load script inserts models into Oracle (mocked)
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from scripts.load_onnx_models import (
    build_tire_degradation_models,
    export_to_onnx,
    load_model_into_oracle,
)


class TestBuildTireDegradationModels:
    """Test synthetic model training."""

    def test_models_train_successfully(self):
        (grip_model, laps_model), feature_names = build_tire_degradation_models(
            n_samples=500, random_state=42
        )
        assert grip_model is not None
        assert laps_model is not None
        assert len(feature_names) == 4

    def test_feature_names(self):
        _, feature_names = build_tire_degradation_models(n_samples=100, random_state=42)
        assert feature_names == [
            "TIRE_AGE_LAPS",
            "TRACK_TEMP_C",
            "FUEL_LOAD_KG",
            "COMPOUND_ENCODED",
        ]

    def test_models_predict(self):
        (grip_model, laps_model), _ = build_tire_degradation_models(
            n_samples=500, random_state=42
        )
        # Single sample: 10 laps old, 35C, 80kg fuel, soft compound (0)
        x = np.array([[10, 35.0, 80.0, 0]])
        grip = grip_model.predict(x)
        laps = laps_model.predict(x)
        assert grip.shape == (1,), f"Expected (1,) got {grip.shape}"
        assert 0.0 <= grip[0] <= 100.0, f"Grip should be 0-100, got {grip[0]}"
        assert laps[0] >= 0, f"Laps remaining should be >= 0, got {laps[0]}"


class TestExportToOnnx:
    """Test ONNX export."""

    def test_export_creates_file(self):
        (grip_model, _), feature_names = build_tire_degradation_models(
            n_samples=500, random_state=42
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tire_grip.onnx")
            export_to_onnx(grip_model, feature_names, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_onnx_model_produces_single_output(self):
        (grip_model, _), feature_names = build_tire_degradation_models(
            n_samples=500, random_state=42
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tire_grip.onnx")
            export_to_onnx(grip_model, feature_names, path)

            import onnxruntime as ort

            session = ort.InferenceSession(path)
            x = np.array([[15, 40.0, 60.0, 1]], dtype=np.float32)
            inputs = {session.get_inputs()[0].name: x}
            outputs = session.run(None, inputs)
            # Single-output regression -> one output tensor of shape (1, 1)
            assert len(outputs) == 1
            assert outputs[0].shape == (1, 1)


class TestLoadModelIntoOracle:
    """Test Oracle loading (mocked DB)."""

    @pytest.mark.asyncio
    async def test_load_model_calls_dbms_data_mining(self):
        mock_cursor = AsyncMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = AsyncMock()

        mock_pool = MagicMock()

        @contextlib.asynccontextmanager
        async def _fake_connection():
            yield mock_conn

        mock_pool.connection = _fake_connection

        with tempfile.TemporaryDirectory() as tmpdir:
            (grip_model, _), feature_names = build_tire_degradation_models(
                n_samples=100, random_state=42
            )
            path = os.path.join(tmpdir, "tire_grip.onnx")
            export_to_onnx(grip_model, feature_names, path)

            await load_model_into_oracle(
                pool=mock_pool,
                model_path=path,
                model_name="TIRE_GRIP_MODEL",
                metadata='{"function": "regression", "input": {"X": []}}',
            )

            # Verify cursor.execute was called (model loading SQL)
            assert mock_cursor.execute.called
            # The metadata must map the ONNX input tensor name explicitly
            metadata_arg = mock_cursor.execute.call_args[0][1]["metadata"]
            assert "regression" in metadata_arg
