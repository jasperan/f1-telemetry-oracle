"""Tests for in-database ONNX model loading.

Verifies:
- Synthetic tire degradation model trains and exports to ONNX
- ONNX model file is valid and produces correct output shape
- Load script inserts model into Oracle (integration test, mocked)
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from scripts.load_onnx_models import (
    build_tire_degradation_model,
    export_to_onnx,
    load_model_into_oracle,
)


class TestBuildTireDegradationModel:
    """Test synthetic model training."""

    def test_model_trains_successfully(self):
        model, feature_names = build_tire_degradation_model(n_samples=500, random_state=42)
        assert model is not None
        assert len(feature_names) == 4

    def test_feature_names(self):
        _, feature_names = build_tire_degradation_model(n_samples=100, random_state=42)
        assert feature_names == [
            "tire_age_laps",
            "track_temp_c",
            "fuel_load_kg",
            "compound_encoded",
        ]

    def test_model_predicts(self):
        model, _ = build_tire_degradation_model(n_samples=500, random_state=42)
        # Single sample: 10 laps old, 35C, 80kg fuel, soft compound (0)
        X = np.array([[10, 35.0, 80.0, 0]])
        predictions = model.predict(X)
        assert predictions.shape == (1, 2), f"Expected (1, 2) got {predictions.shape}"
        grip, laps_remaining = predictions[0]
        assert 0.0 <= grip <= 100.0, f"Grip should be 0-100, got {grip}"
        assert laps_remaining >= 0, f"Laps remaining should be >= 0, got {laps_remaining}"


class TestExportToOnnx:
    """Test ONNX export."""

    def test_export_creates_file(self):
        model, feature_names = build_tire_degradation_model(n_samples=500, random_state=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tire_deg.onnx")
            export_to_onnx(model, feature_names, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_onnx_model_produces_correct_output(self):
        model, feature_names = build_tire_degradation_model(n_samples=500, random_state=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tire_deg.onnx")
            export_to_onnx(model, feature_names, path)

            import onnxruntime as ort

            session = ort.InferenceSession(path)
            X = np.array([[15, 40.0, 60.0, 1]], dtype=np.float32)
            inputs = {session.get_inputs()[0].name: X}
            outputs = session.run(None, inputs)
            assert outputs[0].shape == (1, 2)


class TestLoadModelIntoOracle:
    """Test Oracle loading (mocked DB)."""

    @pytest.mark.asyncio
    async def test_load_model_calls_dbms_data_mining(self):
        import contextlib

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
            model, feature_names = build_tire_degradation_model(n_samples=100, random_state=42)
            path = os.path.join(tmpdir, "tire_deg.onnx")
            export_to_onnx(model, feature_names, path)

            await load_model_into_oracle(
                pool=mock_pool,
                model_path=path,
                model_name="TIRE_DEGRADATION_V1",
            )

            # Verify cursor.execute was called (model loading SQL)
            assert mock_cursor.execute.called
