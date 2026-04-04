from __future__ import annotations

import json
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini
    gemini_api_key: str = ""
    gemini_flash_model: str = "gemini-2.0-flash"
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
    cors_allow_credentials: bool = False

    @field_validator("cors_origins", mode="before")
    def _parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, bool):
            # Allow explicit false to mean wildcard origin when credentials are disabled.
            return ["*"]

        if isinstance(value, str):
            raw = value.strip()
            if raw.lower() == "false":
                return ["*"]
            if raw.lower() == "true":
                return ["*"]
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = []
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            if raw == "":
                return []
            return [item.strip() for item in raw.split(",") if item.strip()]

        return value


settings = Settings()
