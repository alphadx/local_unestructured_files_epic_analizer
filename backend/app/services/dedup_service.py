from __future__ import annotations

"""
Advanced deduplication service — Phase 5B.

Provides a pluggable abstraction over duplicate-detection strategies:

- **native**   — Uses SHA-256 hashes already computed by the scanner.
                 No external dependencies. Default.
- **czkawka**  — Delegates to the ``czkawka_cli`` binary for detecting
                 similar (not only identical) images and videos.
                 Requires ``czkawka_cli`` on PATH.
- **dupeguru** — Delegates to the ``dupeguru`` CLI in Picture mode to
                 find visually similar images before sending them to Gemini.
                 Requires ``dupeguru`` on PATH.

Configuration (via .env / environment variables):
    DEDUP_BACKEND=native            # native | czkawka | dupeguru
    DEDUP_SIMILARITY_THRESHOLD=0.95 # 0.0-1.0, used by fuzzy backends

All public methods return the same ``FileIndex`` schema already used by the
rest of the pipeline — callers do not need to know which backend is active.

External backends degrade gracefully: if the required binary is not found,
the service logs a warning and falls back to the native backend automatically.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.models.schemas import FileIndex

logger = logging.getLogger(__name__)

# MIME type prefixes that represent image files
_IMAGE_MIME_PREFIXES = ("image/",)

# MIME type prefixes that represent video files
_VIDEO_MIME_PREFIXES = ("video/",)


def _is_image(fi: FileIndex) -> bool:
    if fi.mime_type:
        return any(fi.mime_type.startswith(p) for p in _IMAGE_MIME_PREFIXES)
    return fi.extension.lower() in {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
        ".tif", ".webp", ".heic", ".heif", ".svg", ".ico",
    }


def _is_video(fi: FileIndex) -> bool:
    if fi.mime_type:
        return any(fi.mime_type.startswith(p) for p in _VIDEO_MIME_PREFIXES)
    return fi.extension.lower() in {
        ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv",
        ".webm", ".m4v", ".3gp", ".ts",
    }


def _tool_available(name: str) -> bool:
    """Return True if *name* is an executable on PATH."""
    return shutil.which(name) is not None


class DedupService:
    """
    Pluggable duplicate-detection service.

    Usage::

        from app.services.dedup_service import DedupService
        service = DedupService(backend="native", similarity_threshold=0.95)

        # Update is_duplicate / duplicate_of flags on all FileIndex objects
        updated = service.find_duplicates(file_indices)

        # For image files only: pre-filter visually identical images
        updated = service.find_visual_duplicates(image_file_indices)
    """

    def __init__(self, backend: str = "native", similarity_threshold: float = 0.95) -> None:
        self.backend = backend.lower()
        self.similarity_threshold = max(0.0, min(1.0, similarity_threshold))
        self._effective_backend = self._resolve_backend()

    # ------------------------------------------------------------------
    # Backend resolution
    # ------------------------------------------------------------------

    def _resolve_backend(self) -> str:
        """Validate the requested backend is usable; fall back to native if not."""
        if self.backend == "native":
            return "native"

        if self.backend == "czkawka":
            if _tool_available("czkawka_cli"):
                logger.info("DedupService: using 'czkawka' backend (czkawka_cli found on PATH)")
                return "czkawka"
            logger.warning(
                "DedupService: 'czkawka' backend requested but 'czkawka_cli' not found on PATH. "
                "Falling back to 'native'. Install czkawka_cli to enable advanced deduplication."
            )
            return "native"

        if self.backend == "dupeguru":
            if _tool_available("dupeguru"):
                logger.info("DedupService: using 'dupeguru' backend (dupeguru found on PATH)")
                return "dupeguru"
            logger.warning(
                "DedupService: 'dupeguru' backend requested but 'dupeguru' not found on PATH. "
                "Falling back to 'native'. Install dupeguru to enable visual deduplication."
            )
            return "native"

        logger.warning(
            "DedupService: unknown backend '%s'. Falling back to 'native'.", self.backend
        )
        return "native"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_duplicates(self, file_indices: list[FileIndex]) -> list[FileIndex]:
        """
        Return *file_indices* with ``is_duplicate`` / ``duplicate_of`` updated.

        - ``native``: relies on the SHA-256 already computed by the scanner.
        - ``czkawka``: also marks similar (non-identical) images and videos.
        - ``dupeguru``: same as native for non-visual files; for images delegates
          to ``find_visual_duplicates``.
        """
        if self._effective_backend == "czkawka":
            return self._find_duplicates_czkawka(file_indices)
        if self._effective_backend == "dupeguru":
            images = [fi for fi in file_indices if _is_image(fi)]
            non_images = [fi for fi in file_indices if not _is_image(fi)]
            visual_deduped = self._find_visual_duplicates_dupeguru(images)
            return non_images + visual_deduped
        # native — SHA-256 already filled by scanner; nothing to recompute
        return file_indices

    def find_visual_duplicates(self, file_indices: list[FileIndex]) -> list[FileIndex]:
        """
        Mark visually similar images as duplicates without calling Gemini.

        Only processes files with an image MIME type or image extension.
        Non-image files are returned unchanged.

        Returns the updated list (same objects, mutated in-place).
        """
        images = [fi for fi in file_indices if _is_image(fi)]
        non_images = [fi for fi in file_indices if not _is_image(fi)]

        if not images:
            return file_indices

        if self._effective_backend == "czkawka":
            deduped_images = self._find_visual_duplicates_czkawka(images)
        elif self._effective_backend == "dupeguru":
            deduped_images = self._find_visual_duplicates_dupeguru(images)
        else:
            # native — no visual dedup; return unchanged
            deduped_images = images

        return non_images + deduped_images

    @property
    def effective_backend(self) -> str:
        """The backend actually in use (may differ from requested due to fallback)."""
        return self._effective_backend

    # ------------------------------------------------------------------
    # Native backend (no-op — scanner already computed SHA-256)
    # ------------------------------------------------------------------

    # (No additional logic needed; find_duplicates returns the list as-is)

    # ------------------------------------------------------------------
    # Czkawka backend
    # ------------------------------------------------------------------

    def _find_duplicates_czkawka(self, file_indices: list[FileIndex]) -> list[FileIndex]:
        """
        Run ``czkawka_cli`` for both exact and similar image/video detection.

        Files not covered by czkawka (non-image, non-video) are still detected
        via their existing SHA-256 flags from the scanner.
        """
        images = [fi for fi in file_indices if _is_image(fi)]
        videos = [fi for fi in file_indices if _is_video(fi)]
        others = [fi for fi in file_indices if not _is_image(fi) and not _is_video(fi)]

        updated_images = self._find_visual_duplicates_czkawka(images) if images else []
        updated_videos = self._find_similar_videos_czkawka(videos) if videos else []

        return others + updated_images + updated_videos

    def _find_visual_duplicates_czkawka(self, images: list[FileIndex]) -> list[FileIndex]:
        """Detect similar images using czkawka_cli similar-images mode."""
        if not images:
            return []

        unique_dirs = {str(Path(fi.path).parent) for fi in images}
        paths_by_path = {fi.path: fi for fi in images}

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            output_file = tf.name

        try:
            cmd = [
                "czkawka_cli",
                "image",
                "--directories", ",".join(sorted(unique_dirs)),
                "--similarity-preset",
                self._czkawka_similarity_preset(),
                "--json-file", output_file,
            ]
            logger.debug("DedupService[czkawka]: running %s", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode not in (0, 1):  # czkawka returns 1 when duplicates found
                logger.warning(
                    "DedupService[czkawka]: czkawka_cli exited with %d — stderr: %s",
                    result.returncode, result.stderr[:500],
                )
                return images

            similar_groups = self._parse_czkawka_json(output_file)
            return self._apply_similar_groups(paths_by_path, similar_groups)

        except FileNotFoundError:
            logger.warning("DedupService[czkawka]: czkawka_cli not found, skipping visual dedup")
            return images
        except subprocess.TimeoutExpired:
            logger.warning("DedupService[czkawka]: czkawka_cli timed out after 300s")
            return images
        except Exception as exc:  # noqa: BLE001
            logger.warning("DedupService[czkawka]: unexpected error: %s", exc)
            return images
        finally:
            Path(output_file).unlink(missing_ok=True)

    def _find_similar_videos_czkawka(self, videos: list[FileIndex]) -> list[FileIndex]:
        """Detect similar videos using czkawka_cli video mode."""
        if not videos:
            return []

        unique_dirs = {str(Path(fi.path).parent) for fi in videos}
        paths_by_path = {fi.path: fi for fi in videos}

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            output_file = tf.name

        try:
            cmd = [
                "czkawka_cli",
                "video",
                "--directories", ",".join(sorted(unique_dirs)),
                "--json-file", output_file,
            ]
            logger.debug("DedupService[czkawka]: running %s", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode not in (0, 1):
                logger.warning(
                    "DedupService[czkawka video]: czkawka_cli exited with %d — stderr: %s",
                    result.returncode, result.stderr[:500],
                )
                return videos

            similar_groups = self._parse_czkawka_json(output_file)
            return self._apply_similar_groups(paths_by_path, similar_groups)

        except FileNotFoundError:
            logger.warning("DedupService[czkawka]: czkawka_cli not found for video dedup")
            return videos
        except subprocess.TimeoutExpired:
            logger.warning("DedupService[czkawka video]: czkawka_cli timed out after 600s")
            return videos
        except Exception as exc:  # noqa: BLE001
            logger.warning("DedupService[czkawka video]: unexpected error: %s", exc)
            return videos
        finally:
            Path(output_file).unlink(missing_ok=True)

    def _czkawka_similarity_preset(self) -> str:
        """Map similarity_threshold to a czkawka preset name."""
        if self.similarity_threshold >= 0.99:
            return "VeryHigh"
        if self.similarity_threshold >= 0.95:
            return "High"
        if self.similarity_threshold >= 0.85:
            return "Medium"
        return "Low"

    @staticmethod
    def _parse_czkawka_json(json_file: str) -> list[list[str]]:
        """
        Parse czkawka JSON output and return a list of groups.
        Each group is a list of file paths that are similar to each other.
        """
        try:
            with open(json_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("DedupService[czkawka]: failed to parse JSON output: %s", exc)
            return []

        groups: list[list[str]] = []

        # czkawka JSON structure: {"similar_images": [[{"path": "...", ...}, ...], ...]}
        # or {"similar_videos": [[{"path": "...", ...}, ...], ...]}
        for key in ("similar_images", "similar_videos", "duplicate_files"):
            raw_groups = data.get(key, [])
            for raw_group in raw_groups:
                paths: list[str] = []
                if isinstance(raw_group, list):
                    for item in raw_group:
                        if isinstance(item, dict):
                            p = item.get("path") or item.get("file_path")
                        elif isinstance(item, str):
                            p = item
                        else:
                            continue
                        if p:
                            paths.append(p)
                if len(paths) > 1:
                    groups.append(paths)

        return groups

    # ------------------------------------------------------------------
    # dupeGuru backend
    # ------------------------------------------------------------------

    def _find_visual_duplicates_dupeguru(self, images: list[FileIndex]) -> list[FileIndex]:
        """
        Run dupeguru in Picture mode to detect visually similar images.

        dupeGuru does not have a stable headless JSON CLI, so we use a workaround:
        write a temp scan list, run dupeguru --result-path, parse the XML result.
        If dupeguru is not available, falls back gracefully.
        """
        if not images:
            return []

        paths_by_path = {fi.path: fi for fi in images}

        with tempfile.TemporaryDirectory() as tmpdir:
            result_file = Path(tmpdir) / "results.xml"
            # Write source paths to a file for dupeguru to scan
            sources_file = Path(tmpdir) / "sources.txt"
            unique_dirs = sorted({str(Path(fi.path).parent) for fi in images})
            sources_file.write_text("\n".join(unique_dirs), encoding="utf-8")

            try:
                cmd = [
                    "dupeguru",
                    "--appmode", "2",  # Picture mode
                    "--result-path", str(result_file),
                    "--se", str(int(self.similarity_threshold * 100)),  # similarity 0-100
                    *unique_dirs,
                ]
                logger.debug("DedupService[dupeguru]: running %s", " ".join(cmd))
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode not in (0, 1):
                    logger.warning(
                        "DedupService[dupeguru]: dupeguru exited with %d — stderr: %s",
                        result.returncode, result.stderr[:500],
                    )
                    return images

                if result_file.exists():
                    similar_groups = self._parse_dupeguru_xml(str(result_file))
                    return self._apply_similar_groups(paths_by_path, similar_groups)

                return images

            except FileNotFoundError:
                logger.warning("DedupService[dupeguru]: dupeguru not found, skipping visual dedup")
                return images
            except subprocess.TimeoutExpired:
                logger.warning("DedupService[dupeguru]: dupeguru timed out after 300s")
                return images
            except Exception as exc:  # noqa: BLE001
                logger.warning("DedupService[dupeguru]: unexpected error: %s", exc)
                return images

    @staticmethod
    def _parse_dupeguru_xml(xml_file: str) -> list[list[str]]:
        """Parse dupeGuru XML result file and return groups of similar file paths."""
        import xml.etree.ElementTree as ET  # noqa: PLC0415

        groups: list[list[str]] = []
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for group_elem in root.findall(".//group"):
                paths: list[str] = []
                for file_elem in group_elem.findall("file"):
                    path = file_elem.get("path") or file_elem.get("filename")
                    if path:
                        paths.append(path)
                if len(paths) > 1:
                    groups.append(paths)
        except ET.ParseError as exc:
            logger.warning("DedupService[dupeguru]: failed to parse XML: %s", exc)
        return groups

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_similar_groups(
        paths_by_path: dict[str, FileIndex],
        similar_groups: list[list[str]],
    ) -> list[FileIndex]:
        """
        Given a list of similar-file groups, mark all but the first file in each
        group as ``is_duplicate=True`` with ``duplicate_of`` pointing to the first.

        Files not present in any group are returned unchanged (is_duplicate as-is).
        """
        # Build a mapping: path -> (is_duplicate, duplicate_of)
        duplicate_flags: dict[str, tuple[bool, str | None]] = {}
        for group in similar_groups:
            if not group:
                continue
            original = group[0]
            for path in group[1:]:
                duplicate_flags[path] = (True, original)

        result: list[FileIndex] = []
        for path, fi in paths_by_path.items():
            if path in duplicate_flags:
                is_dup, dup_of = duplicate_flags[path]
                # Return a new instance with updated flags to avoid mutating the original
                result.append(fi.model_copy(update={"is_duplicate": is_dup, "duplicate_of": dup_of}))
            else:
                result.append(fi)

        return result


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------


def get_dedup_service() -> DedupService:
    """Return a DedupService configured from application settings."""
    from app.config import settings  # noqa: PLC0415 — avoid circular import at module load

    return DedupService(
        backend=settings.dedup_backend,
        similarity_threshold=settings.dedup_similarity_threshold,
    )
