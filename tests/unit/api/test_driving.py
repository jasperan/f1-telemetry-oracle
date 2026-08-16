"""Tests for the driving-style twin service (api/services/driving.py)."""

from __future__ import annotations

import pytest

from api.services import driving
from tests.unit.api.mock_pool import FakeCursor, FakePool


def _make_frames(lap_id: str, n: int = 60, speed_base: float = 200.0) -> list[tuple]:
    """Build synthetic frame rows across the full lap distance."""
    frames = []
    for i in range(n):
        progress = i / n
        frames.append(
            (
                f"{lap_id}_f{i}",
                lap_id,
                i * 500,
                round(progress * 5000, 2),
                round(speed_base + 100 * (1 - abs(progress - 0.5) * 2), 1),
                round(100 - 80 * abs(progress - 0.3), 2),
                (100 if 0.25 < progress < 0.35 else 0),
                round(0.4 * progress, 4),
                min(8, max(1, int(speed_base / 50))),
                9000 + i,
                1 if i > n * 0.7 else 0,
            )
        )
    return frames


class TestSplitIntoSectors:
    def test_three_sectors(self):
        frames = _make_frames("lap_1", n=90)
        sectors = driving.split_into_sectors(frames)
        assert len(sectors) == 3
        for sector in sectors:
            assert set(sector.keys()) == {
                "distance_m",
                "speed_kph",
                "throttle",
                "brake",
                "steering",
                "gear",
                "drs",
            }
            assert len(sector["speed_kph"]) > 0

    def test_empty_returns_empty(self):
        assert driving.split_into_sectors([]) == []

    def test_single_point_handled(self):
        frames = [("f1", "lap", 0, 0.0, 200.0, 50.0, 0.0, 0.0, 4, 9000, 0)]
        sectors = driving.split_into_sectors(frames)
        assert len(sectors) == 3


class TestEmbedLapSectors:
    @pytest.mark.asyncio
    async def test_too_few_frames_returns_none(self):
        pool = FakePool(rows=_make_frames("lap_x", n=4))
        assert await driving.embed_lap_sectors(pool, "lap_x") is None

    @pytest.mark.asyncio
    async def test_embeds_and_stores_three_vectors(self):
        frames = _make_frames("lap_y", n=90)
        cursor = FakeCursor(rows=frames)
        pool = FakePool(cursor=cursor)
        embeddings = await driving.embed_lap_sectors(pool, "lap_y")
        assert embeddings is not None
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 384

        # Insert statements executed: DELETE + 3 INSERTs
        executed = cursor.executed
        assert any("DELETE FROM lap_sector_embeddings" in sql for sql, _ in executed)
        inserts = [sql for sql, _ in executed if "INSERT INTO lap_sector_embeddings" in sql]
        assert len(inserts) == 3


class TestDrivingTwin:
    @pytest.mark.asyncio
    async def test_sparse_lap_returns_error(self):
        pool = FakePool(rows=_make_frames("sparse", n=3))
        result = await driving.driving_twin(pool, "sparse", top_k=2)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_full_flow_with_mock_candidates(self, monkeypatch):
        """Embed the sim lap; other laps come back with similarities."""
        frames = _make_frames("sim_lap", n=90)

        class Cursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self._state = {"phase": "frames", "deleted": False}

            async def execute(self, sql, binds=None):
                self.executed.append((sql, binds))
                if "FROM telemetry_frames WHERE lap_id" in sql:
                    self._state["phase"] = "frames"
                    self.rows = frames
                elif "DELETE FROM lap_sector_embeddings" in sql or "INSERT INTO lap_sector_embeddings" in sql:
                    self.rows = []
                elif "GROUP BY lap_id HAVING COUNT(*) >= " in sql:
                    self._state["phase"] = "missing"
                    self.rows = [("real_lap",)]  # candidate missing embeddings
                elif "sector_embedding IS NOT NULL" in sql:
                    self._state["phase"] = "similarity"
                    self.description = [
                        ("lap_id",),
                        ("code",),
                        ("driver",),
                        ("lap_time_ms",),
                        ("similarity",),
                    ]
                    self.rows = [
                        ("real_lap", "HAM", "Lewis Hamilton", 85200, 0.01),
                        ("real_lap2", "ALO", "Fernando Alonso", 86000, 0.02),
                    ]
                elif "FROM laps l" in sql and "lap_id = " in sql:
                    self.rows = []
                return self

            async def fetchall(self):
                return self.rows

        cursor = Cursor()
        pool = FakePool(cursor=cursor)

        result = await driving.driving_twin(pool, "sim_lap", top_k=2)
        assert "error" not in result
        assert len(result["sectors"]) == 3
        # Every sector has the top match HAM with similarity 0.01
        for sector in result["sectors"]:
            assert sector["matches"][0]["code"] == "HAM"
        assert result["overall_twin"]["driver_code"] == "HAM"
        assert result["overall_twin"]["mean_similarity"] == pytest.approx(0.01, abs=0.001)
