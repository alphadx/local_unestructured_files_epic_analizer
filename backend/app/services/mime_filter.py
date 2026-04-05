"""Utilities for filtering files by MIME type and extension based on configuration."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_list(value: str, prefix: str = ".") -> set[str]:
    """Parse a comma-separated string into a set of normalized values."""
    if not value or not value.strip():
        return set()
    items = value.split(",")
    normalized = set()
    for item in items:
        item = item.strip()
        if item:
            # Normalize extensions to lowercase with leading dot
            if prefix == ".":
                if not item.startswith("."):
                    item = "." + item
                item = item.lower()
            normalized.add(item)
    return normalized


def should_process_file(
    file_path: Path | str,
    mime_type: str | None,
    *,
    ingestion_mode: str = "blacklist",
    allowed_extensions: str = "",
    denied_extensions: str = "",
    allowed_mime_types: str = "",
    denied_mime_types: str = "",
) -> tuple[bool, str]:
    """
    Determine if a file should be processed based on extension and MIME type.

    Returns:
        (should_process, reason_if_skipped)
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    ingestion_mode = (ingestion_mode or "blacklist").strip().lower()
    extension = file_path.suffix.lower()
    mime_type = mime_type or ""

    allowed_exts = _parse_list(allowed_extensions, prefix=".")
    denied_exts = _parse_list(denied_extensions, prefix=".")
    allowed_mimes = _parse_list(allowed_mime_types, prefix="")
    denied_mimes = _parse_list(denied_mime_types, prefix="")

    # Check extension-based filtering
    if ingestion_mode == "whitelist":
        # Whitelist mode: at least one allow rule must match.
        if not allowed_exts and not allowed_mimes:
            return False, "no whitelist rules configured"
        if allowed_exts and extension not in allowed_exts:
            return False, f"extension not in whitelist: {extension}"
    else:
        # Blacklist mode (default): extension must not be in denied list
        if extension in denied_exts:
            return False, f"extension in blacklist: {extension}"

    # Check MIME type-based filtering
    if mime_type:
        if ingestion_mode == "whitelist":
            # Whitelist mode: MIME type must match one of the allowed prefixes
            if allowed_mimes:
                matched = any(
                    mime_type.startswith(prefix) for prefix in allowed_mimes
                )
                if not matched:
                    return False, f"MIME type not whitelisted: {mime_type}"
        else:
            # Blacklist mode: MIME type must not match any denied prefix
            if any(mime_type.startswith(prefix) for prefix in denied_mimes):
                return False, f"MIME type blacklisted: {mime_type}"

    return True, ""


def filter_file_index_list(
    file_indices: list,  # list of FileIndex objects
    *,
    ingestion_mode: str = "blacklist",
    allowed_extensions: str = "",
    denied_extensions: str = "",
    allowed_mime_types: str = "",
    denied_mime_types: str = "",
) -> tuple[list, list[dict]]:
    """
    Filter a list of FileIndex objects based on MIME type and extension rules.

    Returns:
        (filtered_list, skipped_info_list)

    Each item in skipped_info_list is a dict with:
        - path: file path
        - reason: reason for skipping
    """
    filtered = []
    skipped = []

    for file_index in file_indices:
        should_process, reason = should_process_file(
            file_index.path,
            mime_type=file_index.mime_type,
            ingestion_mode=ingestion_mode,
            allowed_extensions=allowed_extensions,
            denied_extensions=denied_extensions,
            allowed_mime_types=allowed_mime_types,
            denied_mime_types=denied_mime_types,
        )

        if should_process:
            filtered.append(file_index)
        else:
            skipped.append({"path": file_index.path, "reason": reason})
            logger.debug(f"Skipping file: {file_index.path} — {reason}")

    return filtered, skipped
