"""
Unit tests for remote source selection and scan preparation.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import ScanRequest, SourceProvider
from app.services.source_service import prepare_scan_source


def test_prepare_scan_source_local_returns_same_path(tmp_path):
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
