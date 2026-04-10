"""
Unit tests for remote source selection and scan preparation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import settings
from app.models.schemas import ScanRequest, SourceProvider
from app.services.source_service import prepare_scan_source


def test_prepare_scan_source_local_returns_same_path(tmp_path):
    settings.local_scan_root = ""

    request = ScanRequest(
        path=str(tmp_path),
        source_provider=SourceProvider.LOCAL,
        source_options={},
        enable_pii_detection=False,
        enable_embeddings=False,
        enable_clustering=False,
    )

    path, cleanup = prepare_scan_source(request)

    assert path == str(tmp_path)
    assert cleanup is False


def test_scan_request_local_path_is_resolved_inside_local_scan_root(monkeypatch):
    monkeypatch.setattr(settings, "local_scan_root", "/data/scan")

    request = ScanRequest(
        path="OficinaEstructurada",
        source_provider=SourceProvider.LOCAL,
        source_options={},
        enable_pii_detection=False,
        enable_embeddings=False,
        enable_clustering=False,
    )

    assert request.path == "/data/scan/OficinaEstructurada"


def test_scan_request_local_path_cannot_escape_local_scan_root(monkeypatch):
    monkeypatch.setattr(settings, "local_scan_root", "/data/scan")

    with pytest.raises(ValueError, match="LOCAL_SCAN_ROOT"):
        ScanRequest(
            path="../app",
            source_provider=SourceProvider.LOCAL,
            source_options={},
            enable_pii_detection=False,
            enable_embeddings=False,
            enable_clustering=False,
        )
