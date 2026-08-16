"""Shared fake Oracle pool for unit tests (no database required)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any


class FakeCursor:
    """Minimal async cursor faking execute/fetchone/fetchall."""

    def __init__(
        self,
        rows: list | None = None,
        fetchone_result: Any = None,
        description: list | None = None,
    ) -> None:
        self.rows = rows or []
        self.fetchone_result = fetchone_result
        self.description = description
        self.executed: list[tuple[str, Any]] = []

    async def execute(self, sql: str, binds: Any = None) -> FakeCursor:
        self.executed.append((sql, binds))
        return self

    async def fetchone(self):
        if self.fetchone_result is not None:
            return self.fetchone_result
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class FakeConnection:
    """Minimal async connection wrapping a FakeCursor."""

    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.commit_called = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    async def commit(self) -> None:
        self.commit_called = True


class FakePool:
    """Fake OraclePool returning a configured FakeCursor per connection."""

    def __init__(self, cursor: FakeCursor | None = None, rows: list | None = None) -> None:
        self.cursor = cursor or FakeCursor(rows=rows or [])

    @contextlib.asynccontextmanager
    async def connection(self) -> AsyncIterator[FakeConnection]:
        yield FakeConnection(self.cursor)
