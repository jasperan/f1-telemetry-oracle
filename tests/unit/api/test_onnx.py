"""Tests for the in-database ONNX scoring helpers (api/services/onnx.py)."""

from __future__ import annotations

import pytest

from api.services.onnx import (
    embed_text,
    encode_compound,
    model_exists,
    score_regression,
)
from tests.unit.api.mock_pool import FakeCursor, FakePool


class TestEncodeCompound:
    @pytest.mark.parametrize(
        ("compound", "expected"),
        [
            ("SOFT", 0),
            ("soft", 0),
            ("MEDIUM", 1),
            ("HARD", 2),
            ("INTER", 3),
            ("INTERMEDIATE", 3),
            ("WET", 4),
            ("UNKNOWN", 0),
        ],
    )
    def test_encoding(self, compound: str, expected: int):
        assert encode_compound(compound) == expected


class TestModelExists:
    @pytest.mark.asyncio
    async def test_present(self):
        pool = FakePool(cursor=FakeCursor(fetchone_result=(1,)))
        assert await model_exists(pool, "TIRE_GRIP_MODEL") is True

    @pytest.mark.asyncio
    async def test_absent(self):
        pool = FakePool(cursor=FakeCursor(fetchone_result=(0,)))
        assert await model_exists(pool, "NOPE") is False


class TestScoreRegression:
    @pytest.mark.asyncio
    async def test_returns_float(self):
        pool = FakePool(cursor=FakeCursor(fetchone_result=(62.5,)))
        value = await score_regression(
            pool, "TIRE_GRIP_MODEL", {"TIRE_AGE_LAPS": 10, "TRACK_TEMP_C": 30.0}
        )
        assert value == 62.5

    @pytest.mark.asyncio
    async def test_empty_inputs_returns_none(self):
        pool = FakePool()
        assert await score_regression(pool, "MODEL", {}) is None

    @pytest.mark.asyncio
    async def test_none_row_returns_none(self):
        pool = FakePool(cursor=FakeCursor(fetchone_result=(None,)))
        value = await score_regression(pool, "MODEL", {"A": 1})
        assert value is None

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        class BrokenCursor(FakeCursor):
            async def execute(self, sql, binds=None):
                raise RuntimeError("db down")

        pool = FakePool(cursor=BrokenCursor())
        assert await score_regression(pool, "MODEL", {"A": 1}) is None


class TestEmbedText:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        pool = FakePool(cursor=FakeCursor(fetchone_result=([0.1, 0.2, 0.3],)))
        vec = await embed_text(pool, "ALL_MINILM_L12_V2", "hello")
        assert vec == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        class BrokenCursor(FakeCursor):
            async def execute(self, sql, binds=None):
                raise RuntimeError("no model")

        pool = FakePool(cursor=BrokenCursor())
        assert await embed_text(pool, "ALL_MINILM_L12_V2", "hello") is None
