from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, audit, jobs, rag, reports, reorganize, search

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (idempotent; Alembic handles production migrations)."""
    from app.db.session import create_tables

    try:
        await create_tables()
        _logger.info("Database tables verified/created.")
    except Exception as exc:
        _logger.warning("Could not initialise database: %s", exc)

    yield

    # Graceful shutdown: close the async engine connection pool.
    from app.db.session import engine

    await engine.dispose()
    _logger.info("Database connection pool closed.")


app = FastAPI(
    title="Analizador de Archivos No Estructurados",
    description=(
        "Motor de Ingesta Inteligente para Gobernanza de Datos. "
        "Escanea directorios locales, clasifica documentos con Gemini, "
        "genera embeddings y construye clusters semánticos."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API key authentication middleware
# ---------------------------------------------------------------------------

_UNAUTHENTICATED_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next) -> Response:
    """Validate X-Api-Key header when API_KEY is configured."""
    if settings.api_key:
        # Skip auth for health check and docs
        if request.url.path not in _UNAUTHENTICATED_PATHS:
            provided = request.headers.get("X-Api-Key", "")
            if not secrets.compare_digest(provided, settings.api_key):
                return Response(
                    content='{"detail":"Invalid or missing API key"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "ApiKey"},
                )
    return await call_next(request)


app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(rag.router)
app.include_router(search.router)
app.include_router(reorganize.router)
app.include_router(audit.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}

