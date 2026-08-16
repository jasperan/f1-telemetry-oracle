"""FastAPI application factory for F1 Telemetry Oracle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.services.agent import RaceEngineerAgent
from api.services.ollama import OllamaClient
from api.services.oracle import OraclePool
from api.services.rag import ContextAssembler, QueryUnderstanding, ResponseGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and tear down the Oracle connection pool and AI services."""
    pool = OraclePool(
        dsn=settings.oracle_dsn,
        user=settings.oracle_user,
        password=settings.oracle_password,
    )
    await pool.open()
    app.state.pool = pool

    # Initialize Ollama + RAG services
    ollama_client = OllamaClient(base_url=settings.ollama_base_url)
    app.state.ollama_client = ollama_client
    app.state.query_understanding = QueryUnderstanding(ollama_client=ollama_client)
    app.state.context_assembler = ContextAssembler(oracle_pool=pool)
    app.state.response_generator = ResponseGenerator(ollama_client=ollama_client)
    app.state.agent = RaceEngineerAgent(
        pool=pool, ollama_client=ollama_client, model=settings.ollama_model
    )

    try:
        yield
    finally:
        await ollama_client.close()
        await pool.close()


def create_app() -> FastAPI:
    """Build the FastAPI application with all routers mounted."""
    app = FastAPI(
        title="F1 Telemetry Oracle",
        description="AI-powered F1 race engineer — sim telemetry vs real F1 data, backed by Oracle 23ai Free",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow frontend dev server
    allowed_origins = ["http://localhost:3100", "http://127.0.0.1:3100"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if settings.app_env != "development" else ["*"],
        allow_credentials=settings.app_env != "development",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    from api.routers.chat import router as chat_router
    from api.routers.circuits import router as circuits_router
    from api.routers.compare import router as compare_router
    from api.routers.drivers import router as drivers_router
    from api.routers.laps import router as laps_router
    from api.routers.predict import router as predict_router
    from api.routers.sessions import router as sessions_router
    from api.routers.ws import router as ws_router

    app.include_router(circuits_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(drivers_router, prefix="/api")
    app.include_router(laps_router, prefix="/api")
    app.include_router(compare_router, prefix="/api")
    app.include_router(predict_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
