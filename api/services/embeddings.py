"""Lap embedding pipeline — telemetry trace to 384-dim vector.

Converts raw telemetry (variable-length, 6 channels) into a fixed-size
embedding suitable for Oracle AI Vector Search similarity queries.

Pipeline:
  1. Resample telemetry to 100 equally-spaced points by track distance
  2. Concatenate 6 channels -> 600-dim feature vector
  3. Project via seeded random matrix to 384 dims
  4. L2-normalize

For v1, we use a deterministic random projection (no ONNX autoencoder).
The projection matrix is generated from a fixed seed so embeddings are
reproducible without storing the matrix on disk.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# The 6 telemetry channels used for embedding, in order
CHANNELS = ["speed_kph", "throttle", "brake", "steering", "gear", "drs"]


def resample_telemetry(
    telemetry: dict[str, np.ndarray],
    n_points: int = 100,
) -> np.ndarray:
    """Resample telemetry to a fixed number of equally-spaced points by distance.

    Args:
        telemetry: Dict with 'distance_m' key and 6 channel arrays.
        n_points: Number of output points (default 100).

    Returns:
        Array of shape (n_points, 6) with channels in CHANNELS order.
    """
    distance = telemetry["distance_m"]
    n_input = len(distance)

    if n_input < 2:
        raise ValueError(f"Need at least 2 telemetry points, got {n_input}")

    # Target distances: equally spaced from start to end
    target_dist = np.linspace(distance[0], distance[-1], n_points)

    resampled = np.zeros((n_points, len(CHANNELS)), dtype=np.float64)

    for ch_idx, channel_name in enumerate(CHANNELS):
        values = telemetry[channel_name]
        # Linear interpolation to target distances
        resampled[:, ch_idx] = np.interp(target_dist, distance, values)

    return resampled


class LapEmbedder:
    """Produces fixed-size embeddings from telemetry using random projection.

    The projection matrix is generated deterministically from a seed,
    so the same seed always produces the same embeddings -- no need to
    persist the matrix.

    Args:
        seed: Random seed for the projection matrix.
        output_dim: Embedding dimensionality (default 384 for Oracle Vector Search).
        n_points: Number of resampled telemetry points (default 100).
    """

    def __init__(
        self,
        seed: int = 42,
        output_dim: int = 384,
        n_points: int = 100,
    ) -> None:
        self._n_points = n_points
        self._output_dim = output_dim
        self._input_dim = n_points * len(CHANNELS)  # 100 * 6 = 600

        # Deterministic random projection matrix (600 -> 384)
        # Using Gaussian random projection (Johnson-Lindenstrauss)
        rng = np.random.RandomState(seed)
        self._projection = rng.randn(self._input_dim, output_dim).astype(np.float32)
        # Scale by 1/sqrt(output_dim) for variance preservation
        self._projection /= np.sqrt(output_dim)

        logger.info(
            "LapEmbedder initialized: %d -> %d dims (seed=%d)",
            self._input_dim, output_dim, seed,
        )

    def embed(self, telemetry: dict[str, np.ndarray]) -> np.ndarray:
        """Convert a telemetry trace to a 384-dim embedding vector.

        Args:
            telemetry: Dict with 'distance_m' and 6 channel arrays.

        Returns:
            L2-normalized float32 array of shape (output_dim,).
        """
        # Step 1: Resample to fixed grid
        resampled = resample_telemetry(telemetry, n_points=self._n_points)

        # Step 2: Normalize each channel to [0, 1] for stable projection
        col_min = resampled.min(axis=0, keepdims=True)
        col_max = resampled.max(axis=0, keepdims=True)
        col_range = col_max - col_min
        col_range[col_range == 0] = 1.0  # avoid division by zero for constant channels
        normalized = (resampled - col_min) / col_range

        # Step 3: Flatten to 600-dim vector
        flat = normalized.flatten().astype(np.float32)

        # Step 4: Project to output_dim
        embedding = flat @ self._projection

        # Step 5: L2-normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding /= norm

        return embedding

    def embed_batch(self, telemetry_list: list[dict[str, np.ndarray]]) -> np.ndarray:
        """Embed multiple telemetry traces.

        Args:
            telemetry_list: List of telemetry dicts.

        Returns:
            Array of shape (n, output_dim) with L2-normalized embeddings.
        """
        embeddings = np.stack([self.embed(t) for t in telemetry_list])
        return embeddings
