from __future__ import annotations

import contextlib
from typing import AsyncIterator

import oracledb


class OraclePool:
    """Thin-mode async connection pool for Oracle 23ai Free."""

    def __init__(
        self,
        dsn: str,
        user: str,
        password: str,
        min_connections: int = 2,
        max_connections: int = 10,
    ) -> None:
        self._dsn = dsn
        self._user = user
        self._password = password
        self._min = min_connections
        self._max = max_connections
        self._pool: oracledb.AsyncConnectionPool | None = None

    async def open(self) -> None:
        """Create the underlying async connection pool (thin mode, no client libs)."""
        if self._pool is not None:
            return
        self._pool = oracledb.create_pool_async(
            user=self._user,
            password=self._password,
            dsn=self._dsn,
            min=self._min,
            max=self._max,
        )

    async def close(self) -> None:
        """Drain and close every connection in the pool."""
        if self._pool is not None:
            await self._pool.close(force=True)
            self._pool = None

    @contextlib.asynccontextmanager
    async def connection(self) -> AsyncIterator[oracledb.AsyncConnection]:
        """Borrow a connection from the pool. Auto-returns on exit."""
        if self._pool is None:
            raise RuntimeError("Pool is not open. Call await pool.open() first.")
        conn = await self._pool.acquire()
        try:
            yield conn
        finally:
            await self._pool.release(conn)

    async def execute_script(self, sql_text: str) -> None:
        """Run a multi-statement SQL script (split on ';' and '/' delimiters)."""
        async with self.connection() as conn:
            statements: list[str] = []
            current: list[str] = []
            in_plsql = False

            for raw_line in sql_text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("--"):
                    continue

                upper = line.upper()
                if upper.startswith("BEGIN") or upper.startswith("DECLARE") or upper.startswith("CREATE OR REPLACE"):
                    in_plsql = True

                if in_plsql:
                    if line == "/":
                        stmt = "\n".join(current).strip()
                        if stmt:
                            statements.append(stmt)
                        current = []
                        in_plsql = False
                    else:
                        current.append(raw_line)
                else:
                    if line.endswith(";"):
                        current.append(raw_line.rstrip().rstrip(";"))
                        stmt = "\n".join(current).strip()
                        if stmt:
                            statements.append(stmt)
                        current = []
                    else:
                        current.append(raw_line)

            leftover = "\n".join(current).strip().rstrip(";").rstrip("/").strip()
            if leftover:
                statements.append(leftover)

            cursor = conn.cursor()
            for stmt in statements:
                try:
                    await cursor.execute(stmt)
                except oracledb.DatabaseError as exc:
                    error_obj = exc.args[0]
                    if hasattr(error_obj, "code") and error_obj.code in (942, 1418, 955, 1408):
                        pass
                    else:
                        raise
            await conn.commit()
