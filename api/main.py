"""FastAPI application factory for F1 Telemetry Oracle."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from api.config import settings
from api.services.oracle import OraclePool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and tear down the Oracle connection pool."""
    pool = OraclePool(
        dsn=settings.oracle_dsn,
        user=settings.oracle_user,
        password=settings.oracle_password,
    )
    await pool.open()
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


def create_app() -> FastAPI:
    """Build the FastAPI application with all routers mounted."""
    app = FastAPI(
        title="F1 Telemetry Oracle",
        description="AI-powered F1 race engineer — sim telemetry vs real F1 data, backed by Oracle 26ai Free",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Import and include routers
    from api.routers.circuits import router as circuits_router
    from api.routers.drivers import router as drivers_router
    from api.routers.laps import router as laps_router
    from api.routers.sessions import router as sessions_router

    app.include_router(circuits_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(drivers_router, prefix="/api")
    app.include_router(laps_router, prefix="/api")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
