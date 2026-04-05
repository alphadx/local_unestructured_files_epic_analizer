from __future__ import annotations

import json
from typing import Any
from pydantic import Field, field_validator
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
    gemini_flash_model: str = "gemini-2.5-flash-lite"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    # ChromaDB
    vector_store_provider: str = "chroma"
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    vector_store_ssl: bool = False
    vector_store_headers: str | dict[str, str] = Field(default_factory=dict)
    chroma_collection: str = "documents"
    vector_store_allow_reset: bool = True

    # App
    max_file_size_mb: int = 10
    scan_concurrency: int = 4
    log_level: str = "INFO"

    # Content filtering — mime types and extensions
    # Ingestion mode: "whitelist" (only allow listed extensions/mimetypes) or "blacklist" (allow all except denied)
    ingestion_mode: str = "blacklist"
    # Allowed extensions (whitelist mode): e.g., ".txt,.pdf,.docx,.json,.csv"
    allowed_extensions: str = ""
    # Denied extensions (blacklist mode): e.g., ".exe,.dll,.so,.bin"
    denied_extensions: str = ".exe,.dll,.so,.dylib,.bin,.app,.msi,.jar,.com,.bat,.cmd,.pyc,.pyo"
    # Allowed MIME type prefixes: e.g., "text/,application/pdf,image/"
    allowed_mime_types: str = ""
    # Denied MIME type prefixes: e.g., "application/x-executable,application/x-sharedlib"
    denied_mime_types: str = "application/x-executable,application/x-sharedlib,application/x-dvi,application/x-java-applet"

    # Security — API key auth (leave empty to disable)
    api_key: str = ""

    # Retention — automatic job pruning
    max_jobs_retained: int = 0  # 0 = unlimited
    job_max_age_hours: int = 0  # 0 = unlimited

    # Remote source integrations
    google_drive_service_account_json: dict[str, Any] = Field(default_factory=dict)
    google_drive_folder_id: str = ""
    sharepoint_tenant_id: str = ""
    sharepoint_client_id: str = ""
    sharepoint_client_secret: str = ""
    sharepoint_site_id: str = ""
    sharepoint_drive_id: str = ""

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

    @field_validator("google_drive_service_account_json", mode="before")
    @classmethod
    def _parse_google_drive_service_account_json(cls, value: Any) -> dict[str, Any]:
        if value in (None, "", {}):
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}


settings = Settings()

