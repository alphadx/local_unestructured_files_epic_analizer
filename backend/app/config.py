from __future__ import annotations

import json
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        enable_decoding=False,
        env_ignore_empty=True,
    )

    # Gemini
    gemini_api_key: str = ""
    gemini_flash_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/text-embedding-004"

    # ChromaDB
    vector_store_provider: str = "chroma"
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    vector_store_ssl: bool = False
    vector_store_headers: dict[str, str] = {}
    chroma_collection: str = "documents"
    vector_store_allow_reset: bool = True

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

    @field_validator("vector_store_headers", mode="before")
    @classmethod
    def _parse_vector_store_headers(cls, value: Any) -> dict[str, str]:
        if value in (None, "", {}):
            return {}
        if isinstance(value, dict):
            return {str(key): str(val) for key, val in value.items()}
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {}
                for item in raw.split(","):
                    if "=" not in item:
                        continue
                    key, val = item.split("=", 1)
                    parsed[key.strip()] = val.strip()
            if isinstance(parsed, dict):
                return {str(key): str(val) for key, val in parsed.items()}
        return {}


settings = Settings()
