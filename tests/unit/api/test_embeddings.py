"""Tests for the lap embedding pipeline.

Verifies:
- Telemetry resampling to fixed 100-point grid
- Embedding shape is (384,)
- Determinism: same input always produces same embedding
- Similarity: similar laps produce closer vectors than dissimilar ones
"""

from __future__ import annotations

import numpy as np
import pytest

from api.services.embeddings import (
    LapEmbedder,
    resample_telemetry,
)


def _make_telemetry(
    n_points: int, speed_base: float = 280.0, seed: int = 42,
) -> dict[str, np.ndarray]:
    """Generate synthetic telemetry with n_points samples across 6 channels."""
    rng = np.random.RandomState(seed)
    distance = np.linspace(0.0, 5793.0, n_points)  # Monza track length
    return {
        "distance_m": distance,
        "speed_kph": speed_base + rng.randn(n_points) * 10,
        "throttle": np.clip(0.8 + rng.randn(n_points) * 0.1, 0.0, 1.0),
        "brake": np.clip(0.1 + rng.randn(n_points) * 0.05, 0.0, 1.0),
        "steering": rng.randn(n_points) * 0.3,
        "gear": np.clip(np.round(6 + rng.randn(n_points) * 0.5), 1, 8),
        "drs": (rng.rand(n_points) > 0.7).astype(float),
    }


class TestResampleTelemetry:
    """Test the resampling step that normalizes telemetry to 100 points."""

    def test_resample_to_100_points(self):
        telem = _make_telemetry(500)
        resampled = resample_telemetry(telem, n_points=100)
        assert resampled.shape == (100, 6), f"Expected (100, 6), got {resampled.shape}"

    def test_resample_fewer_points(self):
        telem = _make_telemetry(50)
        resampled = resample_telemetry(telem, n_points=100)
        assert resampled.shape == (100, 6)

    def test_resample_exact_points(self):
        telem = _make_telemetry(100)
        resampled = resample_telemetry(telem, n_points=100)
        assert resampled.shape == (100, 6)

    def test_resample_channels_order(self):
        """Channels must be: speed, throttle, brake, steering, gear, drs."""
        telem = _make_telemetry(200)
        resampled = resample_telemetry(telem, n_points=100)
        # Speed channel should be in the 200-300 range
        assert resampled[:, 0].mean() > 100.0, "Channel 0 should be speed"
        # Throttle should be 0-1
        assert 0.0 <= resampled[:, 1].mean() <= 1.0, "Channel 1 should be throttle"


class TestLapEmbedder:
    """Test the full embedding pipeline."""

    @pytest.fixture
    def embedder(self):
        return LapEmbedder(seed=42, output_dim=384)

    def test_embedding_shape(self, embedder):
        telem = _make_telemetry(500)
        embedding = embedder.embed(telem)
        assert embedding.shape == (384,), f"Expected (384,), got {embedding.shape}"

    def test_embedding_dtype(self, embedder):
        telem = _make_telemetry(500)
        embedding = embedder.embed(telem)
        assert embedding.dtype == np.float32

    def test_embedding_determinism(self, embedder):
        telem = _make_telemetry(500)
        e1 = embedder.embed(telem)
        e2 = embedder.embed(telem)
        np.testing.assert_array_equal(e1, e2, err_msg="Same input must produce identical embedding")

    def test_embedding_is_normalized(self, embedder):
        telem = _make_telemetry(500)
        embedding = embedder.embed(telem)
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5, f"Embedding should be L2-normalized, got norm={norm}"

    def test_similar_laps_closer_than_dissimilar(self, embedder):
        """Two laps with similar speed should be closer than a lap with very different speed.

        Uses the same seed (noise pattern) for all three so the ONLY difference
        is speed_base. Per-channel normalization maps speed to [0,1] within each
        lap, but throttle/brake/steering/gear/drs remain identical pre-
        normalization. The speed *range* (min-max) stays the same so the
        normalized speed curve is identical across all three. The real
        discriminator is that with same seed the non-speed channels are
        bit-identical, so two laps that share the same underlying telemetry
        are closer than one with dramatically different relative speed dynamics.

        We use cosine distance (1 - dot) on L2-normalized vectors to capture
        the shape difference that arises from the speed base affecting the
        raw 600-dim feature vector before normalization per-channel.
        """
        # Generate three telemetry traces: same noise, different speed
        # When per-channel normalization is applied, the speed channel
        # normalizes to [0,1] regardless. So we instead create genuinely
        # different trace SHAPES by varying multiple channels.
        rng_a = np.random.RandomState(42)
        rng_c = np.random.RandomState(99)
        n = 500
        distance = np.linspace(0.0, 5793.0, n)

        # Trace A: smooth high-speed lap
        telem_a = {
            "distance_m": distance,
            "speed_kph": 280.0 + rng_a.randn(n) * 10,
            "throttle": np.clip(0.85 + rng_a.randn(n) * 0.05, 0.0, 1.0),
            "brake": np.clip(0.05 + rng_a.randn(n) * 0.03, 0.0, 1.0),
            "steering": rng_a.randn(n) * 0.15,
            "gear": np.clip(np.round(7 + rng_a.randn(n) * 0.3), 1, 8),
            "drs": (rng_a.rand(n) > 0.6).astype(float),
        }

        # Trace B: very similar to A (same pattern, tiny perturbation)
        telem_b = {
            "distance_m": distance,
            "speed_kph": telem_a["speed_kph"] + np.random.RandomState(10).randn(n) * 2,
            "throttle": telem_a["throttle"] + np.random.RandomState(11).randn(n) * 0.01,
            "brake": telem_a["brake"] + np.random.RandomState(12).randn(n) * 0.005,
            "steering": telem_a["steering"] + np.random.RandomState(13).randn(n) * 0.02,
            "gear": telem_a["gear"],  # identical
            "drs": telem_a["drs"],    # identical
        }

        # Trace C: completely different driving style (heavy braking, low throttle)
        telem_c = {
            "distance_m": distance,
            "speed_kph": 180.0 + rng_c.randn(n) * 20,
            "throttle": np.clip(0.4 + rng_c.randn(n) * 0.2, 0.0, 1.0),
            "brake": np.clip(0.4 + rng_c.randn(n) * 0.15, 0.0, 1.0),
            "steering": rng_c.randn(n) * 0.5,
            "gear": np.clip(np.round(4 + rng_c.randn(n) * 1.5), 1, 8),
            "drs": (rng_c.rand(n) > 0.9).astype(float),
        }

        e_a = embedder.embed(telem_a)
        e_b = embedder.embed(telem_b)
        e_c = embedder.embed(telem_c)

        dist_ab = np.linalg.norm(e_a - e_b)
        dist_ac = np.linalg.norm(e_a - e_c)
        assert dist_ab < dist_ac, (
            f"Similar laps should be closer: dist(a,b)={dist_ab:.4f} >= dist(a,c)={dist_ac:.4f}"
        )

    def test_different_seeds_different_projections(self):
        telem = _make_telemetry(500)
        e1 = LapEmbedder(seed=42, output_dim=384).embed(telem)
        e2 = LapEmbedder(seed=99, output_dim=384).embed(telem)
        assert not np.allclose(e1, e2), "Different seeds should produce different projections"
