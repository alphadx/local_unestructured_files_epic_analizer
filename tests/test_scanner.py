"""
Tests for the file scanner service.

These tests do NOT require Gemini API keys or ChromaDB – they only exercise
the local file-system traversal and hashing logic.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

# Make sure the backend app package is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.scanner import scan_directory, _is_noise, _sha256


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: bytes = b"hello world") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# _is_noise
# ---------------------------------------------------------------------------


class TestIsNoise:
    def test_tmp_extension_is_noise(self, tmp_path):
        f = tmp_path / "file.tmp"
        assert _is_noise(f) is True

    def test_exe_is_noise(self, tmp_path):
        assert _is_noise(tmp_path / "app.exe") is True

    def test_tilde_prefix_is_noise(self, tmp_path):
        assert _is_noise(tmp_path / "~$budget.docx") is True

    def test_pdf_is_not_noise(self, tmp_path):
        assert _is_noise(tmp_path / "factura.pdf") is False

    def test_txt_is_not_noise(self, tmp_path):
        assert _is_noise(tmp_path / "readme.txt") is False


# ---------------------------------------------------------------------------
# _sha256
# ---------------------------------------------------------------------------


class TestSha256:
    def test_known_hash(self, tmp_path):
        content = b"hello world"
        f = _write(tmp_path / "test.txt", content)
        expected = hashlib.sha256(content).hexdigest()
        assert _sha256(f) == expected

    def test_nonexistent_returns_empty(self, tmp_path):
        assert _sha256(tmp_path / "missing.txt") == ""


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------


class TestScanDirectory:
    def test_raises_for_missing_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scan_directory(tmp_path / "does_not_exist")

    def test_raises_for_file_not_dir(self, tmp_path):
        f = _write(tmp_path / "file.txt")
        with pytest.raises(NotADirectoryError):
            scan_directory(f)

    def test_basic_scan(self, tmp_path):
        _write(tmp_path / "a.pdf", b"pdf content")
        _write(tmp_path / "b.txt", b"text content")
        results = scan_directory(tmp_path)
        names = {r.name for r in results}
        assert "a.pdf" in names
        assert "b.txt" in names

    def test_noise_files_excluded(self, tmp_path):
        _write(tmp_path / "real.pdf", b"real")
        _write(tmp_path / "junk.tmp", b"temp")
        _write(tmp_path / "~$locked.docx", b"locked")
        results = scan_directory(tmp_path)
        names = {r.name for r in results}
        assert "real.pdf" in names
        assert "junk.tmp" not in names
        assert "~$locked.docx" not in names

    def test_duplicate_detection(self, tmp_path):
        content = b"identical content"
        _write(tmp_path / "original.pdf", content)
        _write(tmp_path / "copy.pdf", content)
        results = scan_directory(tmp_path)
        # One should be marked duplicate
        originals = [r for r in results if not r.is_duplicate]
        duplicates = [r for r in results if r.is_duplicate]
        assert len(originals) == 1
        assert len(duplicates) == 1
        assert duplicates[0].duplicate_of == originals[0].path

    def test_recursive_scan(self, tmp_path):
        _write(tmp_path / "sub" / "deep.txt", b"deep")
        results = scan_directory(tmp_path)
        names = {r.name for r in results}
        assert "deep.txt" in names

    def test_hidden_dirs_skipped(self, tmp_path):
        hidden_dir = tmp_path / ".hidden"
        _write(hidden_dir / "secret.txt", b"secret")
        _write(tmp_path / "visible.txt", b"visible")
        results = scan_directory(tmp_path)
        names = {r.name for r in results}
        assert "visible.txt" in names
        assert "secret.txt" not in names

    def test_file_index_fields(self, tmp_path):
        content = b"document content"
        _write(tmp_path / "invoice.pdf", content)
        results = scan_directory(tmp_path)
        assert len(results) == 1
        fi = results[0]
        assert fi.name == "invoice.pdf"
        assert fi.extension == ".pdf"
        assert fi.size_bytes == len(content)
        assert fi.sha256 == hashlib.sha256(content).hexdigest()
        assert fi.is_duplicate is False

    def test_empty_directory(self, tmp_path):
        results = scan_directory(tmp_path)
        assert results == []
