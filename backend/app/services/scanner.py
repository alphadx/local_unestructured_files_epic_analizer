from __future__ import annotations

import hashlib
import logging
import os
import stat
from datetime import datetime
from pathlib import Path

# Optional: python-magic for MIME detection; fall back gracefully
try:
    import magic  # type: ignore

    _MAGIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MAGIC_AVAILABLE = False

from app.models.schemas import FileIndex

logger = logging.getLogger(__name__)

# Patterns that should be ignored (system noise, temp files, executables …)
_IGNORED_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib",
    ".tmp", ".temp", ".swp", ".DS_Store",
    ".lnk", ".ini", ".sys", ".bat", ".cmd",
    ".log", ".lock",
}

_IGNORED_NAMES = {
    "Thumbs.db", ".DS_Store", "desktop.ini",
    ".gitignore", ".gitkeep",
}

_IGNORED_PREFIXES = ("~$", "._")


def _is_noise(path: Path) -> bool:
    """Return True if the file should be skipped (temp, system, executable…)."""
    if path.name in _IGNORED_NAMES:
        return True
    if path.suffix.lower() in _IGNORED_EXTENSIONS:
        return True
    for prefix in _IGNORED_PREFIXES:
        if path.name.startswith(prefix):
            return True
    return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def _mime_type(path: Path) -> str | None:
    if not _MAGIC_AVAILABLE:
        return None
    try:
        return magic.from_file(str(path), mime=True)
    except Exception:
        return None


def scan_directory(root: str | Path) -> list[FileIndex]:
    """
    Walk *root* recursively and return a FileIndex for every non-noise file.

    Duplicates are flagged by SHA-256: if two files share the same hash the
    second (and further) ones get ``is_duplicate=True`` and ``duplicate_of``
    pointing at the first path encountered.
    """
    root = Path(root)
    logger.info("scan_directory: starting scan of '%s'", root)

    if not root.exists():
        logger.error("scan_directory: path does not exist: '%s'", root)
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        logger.error("scan_directory: path is not a directory: '%s'", root)
        raise NotADirectoryError(f"Path is not a directory: {root}")

    seen_hashes: dict[str, str] = {}  # sha256 -> first path
    results: list[FileIndex] = []
    skipped_noise = 0
    skipped_perm = 0
    skipped_non_regular = 0
    dirs_visited = 0

    for dirpath, _dirs, filenames in os.walk(root):
        # Skip hidden directories
        hidden = [d for d in _dirs if d.startswith(".")]
        _dirs[:] = [d for d in _dirs if not d.startswith(".")]
        dirs_visited += 1

        if hidden:
            logger.debug(
                "scan_directory: skipping %d hidden sub-dir(s) in '%s': %s",
                len(hidden), dirpath, hidden,
            )
        logger.debug(
            "scan_directory: entering '%s' (%d file(s), %d sub-dir(s))",
            dirpath, len(filenames), len(_dirs),
        )

        for filename in filenames:
            file_path = Path(dirpath) / filename
            if _is_noise(file_path):
                logger.debug("scan_directory: noise skip '%s'", file_path)
                skipped_noise += 1
                continue
            try:
                st = file_path.stat()
            except (OSError, PermissionError) as exc:
                logger.warning("scan_directory: cannot stat '%s': %s", file_path, exc)
                skipped_perm += 1
                continue
            if not stat.S_ISREG(st.st_mode):
                logger.debug("scan_directory: non-regular file skip '%s'", file_path)
                skipped_non_regular += 1
                continue

            sha = _sha256(file_path)
            is_dup = sha in seen_hashes and sha != ""
            dup_of = seen_hashes[sha] if is_dup else None
            if not is_dup and sha:
                seen_hashes[sha] = str(file_path)

            if is_dup:
                logger.debug(
                    "scan_directory: duplicate '%s' (same hash as '%s')",
                    file_path, dup_of,
                )

            results.append(
                FileIndex(
                    path=str(file_path),
                    name=filename,
                    extension=file_path.suffix.lower(),
                    size_bytes=st.st_size,
                    created_at=datetime.fromtimestamp(st.st_ctime).isoformat(),
                    modified_at=datetime.fromtimestamp(st.st_mtime).isoformat(),
                    sha256=sha,
                    mime_type=_mime_type(file_path),
                    is_duplicate=is_dup,
                    duplicate_of=dup_of,
                )
            )

    logger.info(
        "scan_directory: finished '%s' — dirs=%d files_indexed=%d "
        "duplicates=%d skipped_noise=%d skipped_perm=%d skipped_non_regular=%d",
        root,
        dirs_visited,
        len(results),
        sum(1 for f in results if f.is_duplicate),
        skipped_noise,
        skipped_perm,
        skipped_non_regular,
    )
    return results
