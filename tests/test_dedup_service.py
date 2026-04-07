"""
Tests for the advanced deduplication service (Phase 5B).

These tests do NOT require any external tools (czkawka, dupeguru, rmlint, jdupes).
All external-tool backends are tested via mocking.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import FileIndex
from app.services.dedup_service import DedupService, _is_image, _is_video, get_dedup_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fi(
    path: str,
    mime_type: str | None = None,
    extension: str = ".txt",
    sha256: str = "",
    is_duplicate: bool = False,
    duplicate_of: str | None = None,
) -> FileIndex:
    return FileIndex(
        path=path,
        name=Path(path).name,
        extension=extension,
        size_bytes=0,
        created_at="2026-01-01T00:00:00",
        modified_at="2026-01-01T00:00:00",
        sha256=sha256,
        mime_type=mime_type,
        is_duplicate=is_duplicate,
        duplicate_of=duplicate_of,
    )


# ---------------------------------------------------------------------------
# _is_image / _is_video helpers
# ---------------------------------------------------------------------------


class TestIsImage:
    def test_jpeg_mime(self):
        fi = _make_fi("/a.jpg", mime_type="image/jpeg", extension=".jpg")
        assert _is_image(fi) is True

    def test_png_mime(self):
        fi = _make_fi("/a.png", mime_type="image/png", extension=".png")
        assert _is_image(fi) is True

    def test_text_mime_not_image(self):
        fi = _make_fi("/a.txt", mime_type="text/plain", extension=".txt")
        assert _is_image(fi) is False

    def test_jpg_extension_no_mime(self):
        fi = _make_fi("/a.jpg", extension=".jpg")
        assert _is_image(fi) is True

    def test_webp_extension(self):
        fi = _make_fi("/a.webp", extension=".webp")
        assert _is_image(fi) is True

    def test_pdf_not_image(self):
        fi = _make_fi("/a.pdf", extension=".pdf")
        assert _is_image(fi) is False


class TestIsVideo:
    def test_mp4_mime(self):
        fi = _make_fi("/v.mp4", mime_type="video/mp4", extension=".mp4")
        assert _is_video(fi) is True

    def test_mkv_extension_no_mime(self):
        fi = _make_fi("/v.mkv", extension=".mkv")
        assert _is_video(fi) is True

    def test_image_not_video(self):
        fi = _make_fi("/a.jpg", mime_type="image/jpeg", extension=".jpg")
        assert _is_video(fi) is False


# ---------------------------------------------------------------------------
# DedupService — native backend
# ---------------------------------------------------------------------------


class TestDedupServiceNative:
    def test_native_backend_resolved(self):
        svc = DedupService(backend="native")
        assert svc.effective_backend == "native"

    def test_find_duplicates_native_returns_unchanged(self):
        fi1 = _make_fi("/a.txt", sha256="aaa")
        fi2 = _make_fi("/b.txt", sha256="bbb")
        svc = DedupService(backend="native")
        result = svc.find_duplicates([fi1, fi2])
        # Native does not recompute; returns as-is
        assert result == [fi1, fi2]

    def test_find_visual_duplicates_native_noop_for_images(self):
        fi1 = _make_fi("/img1.jpg", mime_type="image/jpeg", extension=".jpg")
        fi2 = _make_fi("/img2.jpg", mime_type="image/jpeg", extension=".jpg")
        svc = DedupService(backend="native")
        result = svc.find_visual_duplicates([fi1, fi2])
        # Native: no visual dedup — images returned unchanged
        assert all(not f.is_duplicate for f in result)

    def test_find_visual_duplicates_native_non_images_pass_through(self):
        fi1 = _make_fi("/doc.pdf", extension=".pdf")
        svc = DedupService(backend="native")
        result = svc.find_visual_duplicates([fi1])
        assert result == [fi1]


# ---------------------------------------------------------------------------
# DedupService — unknown backend falls back to native
# ---------------------------------------------------------------------------


class TestDedupServiceFallback:
    def test_unknown_backend_falls_back(self):
        svc = DedupService(backend="nonexistent_tool_xyz")
        assert svc.effective_backend == "native"

    def test_czkawka_not_on_path_falls_back(self):
        with patch("app.services.dedup_service._tool_available", return_value=False):
            svc = DedupService(backend="czkawka")
        assert svc.effective_backend == "native"

    def test_dupeguru_not_on_path_falls_back(self):
        with patch("app.services.dedup_service._tool_available", return_value=False):
            svc = DedupService(backend="dupeguru")
        assert svc.effective_backend == "native"

    def test_czkawka_on_path_resolves(self):
        with patch("app.services.dedup_service._tool_available", return_value=True):
            svc = DedupService(backend="czkawka")
        assert svc.effective_backend == "czkawka"

    def test_dupeguru_on_path_resolves(self):
        with patch("app.services.dedup_service._tool_available", return_value=True):
            svc = DedupService(backend="dupeguru")
        assert svc.effective_backend == "dupeguru"


# ---------------------------------------------------------------------------
# DedupService — similarity threshold → czkawka preset
# ---------------------------------------------------------------------------


class TestCzkawkaPreset:
    def _svc(self, threshold: float) -> DedupService:
        svc = DedupService.__new__(DedupService)
        svc.backend = "czkawka"
        svc.similarity_threshold = threshold
        svc._effective_backend = "czkawka"
        return svc

    def test_very_high(self):
        assert self._svc(0.99)._czkawka_similarity_preset() == "VeryHigh"

    def test_high(self):
        assert self._svc(0.95)._czkawka_similarity_preset() == "High"

    def test_medium(self):
        assert self._svc(0.85)._czkawka_similarity_preset() == "Medium"

    def test_low(self):
        assert self._svc(0.80)._czkawka_similarity_preset() == "Low"


# ---------------------------------------------------------------------------
# DedupService — _apply_similar_groups
# ---------------------------------------------------------------------------


class TestApplySimilarGroups:
    def test_marks_second_as_duplicate(self):
        fi1 = _make_fi("/a.jpg")
        fi2 = _make_fi("/b.jpg")
        paths_by_path = {"/a.jpg": fi1, "/b.jpg": fi2}
        result = DedupService._apply_similar_groups(paths_by_path, [["/a.jpg", "/b.jpg"]])
        by_path = {f.path: f for f in result}
        assert by_path["/a.jpg"].is_duplicate is False
        assert by_path["/b.jpg"].is_duplicate is True
        assert by_path["/b.jpg"].duplicate_of == "/a.jpg"

    def test_only_one_file_in_group_unchanged(self):
        fi1 = _make_fi("/a.jpg")
        paths_by_path = {"/a.jpg": fi1}
        result = DedupService._apply_similar_groups(paths_by_path, [["/a.jpg"]])
        assert result[0].is_duplicate is False

    def test_file_not_in_any_group_unchanged(self):
        fi1 = _make_fi("/a.jpg")
        fi2 = _make_fi("/b.jpg")
        paths_by_path = {"/a.jpg": fi1, "/b.jpg": fi2}
        # Group only covers /a.jpg and /c.jpg (not in dict)
        result = DedupService._apply_similar_groups(
            paths_by_path, [["/a.jpg", "/c.jpg"]]
        )
        by_path = {f.path: f for f in result}
        assert by_path["/b.jpg"].is_duplicate is False

    def test_multiple_groups(self):
        fi1 = _make_fi("/a.jpg")
        fi2 = _make_fi("/b.jpg")
        fi3 = _make_fi("/c.jpg")
        fi4 = _make_fi("/d.jpg")
        paths_by_path = {"/a.jpg": fi1, "/b.jpg": fi2, "/c.jpg": fi3, "/d.jpg": fi4}
        groups = [["/a.jpg", "/b.jpg"], ["/c.jpg", "/d.jpg"]]
        result = DedupService._apply_similar_groups(paths_by_path, groups)
        by_path = {f.path: f for f in result}
        assert by_path["/a.jpg"].is_duplicate is False
        assert by_path["/b.jpg"].is_duplicate is True
        assert by_path["/c.jpg"].is_duplicate is False
        assert by_path["/d.jpg"].is_duplicate is True


# ---------------------------------------------------------------------------
# DedupService — czkawka JSON parsing
# ---------------------------------------------------------------------------


class TestParseCzkawkaJson:
    def test_parses_similar_images(self, tmp_path):
        data = {
            "similar_images": [
                [{"path": "/a.jpg"}, {"path": "/b.jpg"}],
                [{"path": "/c.jpg"}, {"path": "/d.jpg"}],
            ]
        }
        f = tmp_path / "out.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        groups = DedupService._parse_czkawka_json(str(f))
        assert groups == [["/a.jpg", "/b.jpg"], ["/c.jpg", "/d.jpg"]]

    def test_parses_similar_videos(self, tmp_path):
        data = {
            "similar_videos": [
                [{"path": "/v1.mp4"}, {"path": "/v2.mp4"}],
            ]
        }
        f = tmp_path / "out.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        groups = DedupService._parse_czkawka_json(str(f))
        assert groups == [["/v1.mp4", "/v2.mp4"]]

    def test_single_file_group_not_included(self, tmp_path):
        data = {"similar_images": [[{"path": "/a.jpg"}]]}
        f = tmp_path / "out.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        groups = DedupService._parse_czkawka_json(str(f))
        assert groups == []

    def test_invalid_json_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not valid json", encoding="utf-8")
        groups = DedupService._parse_czkawka_json(str(f))
        assert groups == []

    def test_missing_file_returns_empty(self, tmp_path):
        groups = DedupService._parse_czkawka_json(str(tmp_path / "missing.json"))
        assert groups == []


# ---------------------------------------------------------------------------
# DedupService — czkawka subprocess integration (mocked)
# ---------------------------------------------------------------------------


class TestCzkawkaBackendMocked:
    def _make_svc(self) -> DedupService:
        with patch("app.services.dedup_service._tool_available", return_value=True):
            return DedupService(backend="czkawka", similarity_threshold=0.95)

    def test_find_visual_duplicates_czkawka_marks_duplicate(self, tmp_path):
        fi1 = _make_fi("/img/a.jpg", mime_type="image/jpeg", extension=".jpg")
        fi2 = _make_fi("/img/b.jpg", mime_type="image/jpeg", extension=".jpg")
        svc = self._make_svc()

        czkawka_output = {"similar_images": [[{"path": "/img/a.jpg"}, {"path": "/img/b.jpg"}]]}

        def fake_run(*args, **kwargs):
            mock = MagicMock()
            mock.returncode = 1
            # Write the JSON to the output file path extracted from cmd
            cmd = args[0]
            json_flag_idx = cmd.index("--json-file")
            output_path = cmd[json_flag_idx + 1]
            Path(output_path).write_text(json.dumps(czkawka_output), encoding="utf-8")
            return mock

        with patch("subprocess.run", side_effect=fake_run):
            result = svc.find_visual_duplicates([fi1, fi2])

        by_path = {f.path: f for f in result}
        assert by_path["/img/a.jpg"].is_duplicate is False
        assert by_path["/img/b.jpg"].is_duplicate is True
        assert by_path["/img/b.jpg"].duplicate_of == "/img/a.jpg"

    def test_find_visual_duplicates_czkawka_tool_not_found(self, tmp_path):
        fi1 = _make_fi("/img/a.jpg", mime_type="image/jpeg", extension=".jpg")
        svc = self._make_svc()

        with patch("subprocess.run", side_effect=FileNotFoundError("czkawka_cli not found")):
            result = svc.find_visual_duplicates([fi1])

        # Should return unchanged on error
        assert result == [fi1]

    def test_find_visual_duplicates_empty_list(self):
        svc = self._make_svc()
        assert svc.find_visual_duplicates([]) == []

    def test_non_image_files_not_sent_to_czkawka(self, tmp_path):
        fi_txt = _make_fi("/doc.pdf", extension=".pdf")
        fi_img = _make_fi("/img/a.jpg", mime_type="image/jpeg", extension=".jpg")
        svc = self._make_svc()

        czkawka_output: dict = {"similar_images": []}

        def fake_run(*args, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            cmd = args[0]
            json_flag_idx = cmd.index("--json-file")
            output_path = cmd[json_flag_idx + 1]
            Path(output_path).write_text(json.dumps(czkawka_output), encoding="utf-8")
            return mock

        with patch("subprocess.run", side_effect=fake_run):
            result = svc.find_duplicates([fi_txt, fi_img])

        # PDF should be returned unchanged; image also unchanged (no similar found)
        by_path = {f.path: f for f in result}
        assert by_path["/doc.pdf"].is_duplicate is False
        assert by_path["/img/a.jpg"].is_duplicate is False


# ---------------------------------------------------------------------------
# get_dedup_service factory
# ---------------------------------------------------------------------------


class TestGetDedupService:
    def test_returns_native_by_default(self):
        with patch("app.config.settings") as mock_settings:
            mock_settings.dedup_backend = "native"
            mock_settings.dedup_similarity_threshold = 0.95
            svc = get_dedup_service()
        assert svc.effective_backend == "native"

    def test_respects_settings_backend(self):
        with patch("app.config.settings") as mock_settings, \
             patch("app.services.dedup_service._tool_available", return_value=True):
            mock_settings.dedup_backend = "czkawka"
            mock_settings.dedup_similarity_threshold = 0.90
            svc = get_dedup_service()
        assert svc.effective_backend == "czkawka"
        assert svc.similarity_threshold == pytest.approx(0.90)
