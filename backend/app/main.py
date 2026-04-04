from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import jobs, reports, reorganize

logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Analizador de Archivos No Estructurados",
    description=(
        "Motor de Ingesta Inteligente para Gobernanza de Datos. "
        "Escanea directorios locales, clasifica documentos con Gemini, "
        "genera embeddings y construye clusters semánticos."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(reorganize.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}
