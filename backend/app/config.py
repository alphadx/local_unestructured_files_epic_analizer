from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini
    gemini_api_key: str = ""
    gemini_flash_model: str = "gemini-1.5-flash"
    gemini_embedding_model: str = "models/text-embedding-004"

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_collection: str = "documents"

    # App
    max_file_size_mb: int = 10
    scan_concurrency: int = 4
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://frontend:3000"]


settings = Settings()
