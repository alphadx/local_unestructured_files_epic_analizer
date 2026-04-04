"""
Tests for application settings parsing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import Settings


def test_vector_store_headers_accepts_empty_value(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_HEADERS", "")

    settings = Settings(_env_file=None)

    assert settings.vector_store_headers == {}


def test_vector_store_headers_accepts_key_value_pairs(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_HEADERS", "Authorization=Bearer abc, X-Trace = 123")

    settings = Settings(_env_file=None)

    assert settings.vector_store_headers == {
        "Authorization": "Bearer abc",
        "X-Trace": "123",
    }


def test_vector_store_headers_accepts_json(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_HEADERS", '{"Authorization": "Bearer abc"}')

    settings = Settings(_env_file=None)

    assert settings.vector_store_headers == {"Authorization": "Bearer abc"}
