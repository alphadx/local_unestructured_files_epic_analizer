from __future__ import annotations

from app.models.schemas import (
    DocumentMetadata,
    ScanChangeType,
    ScanComparisonResponse,
    ScanComparisonSummary,
    ScanDeltaItem,
)


def _index_by_path(documents: list[DocumentMetadata]) -> dict[str, DocumentMetadata]:
    return {doc.file_index.path: doc for doc in documents}


def _apply_limit(items: list[ScanDeltaItem], limit: int) -> list[ScanDeltaItem]:
    if limit <= 0:
        return []
    return items[:limit]


def compare_scans(
    base_job_id: str,
    target_job_id: str,
    base_documents: list[DocumentMetadata],
    target_documents: list[DocumentMetadata],
    *,
    include_unchanged: bool = False,
    limit: int = 200,
) -> ScanComparisonResponse:
    """Compare two scan outputs and classify files as new/modified/deleted/unchanged."""
    base_by_path = _index_by_path(base_documents)
    target_by_path = _index_by_path(target_documents)

    all_paths = sorted(set(base_by_path.keys()) | set(target_by_path.keys()))

    new_items: list[ScanDeltaItem] = []
    modified_items: list[ScanDeltaItem] = []
    deleted_items: list[ScanDeltaItem] = []
    unchanged_items: list[ScanDeltaItem] = []

    for path in all_paths:
        base_doc = base_by_path.get(path)
        target_doc = target_by_path.get(path)

        if base_doc is None and target_doc is not None:
            new_items.append(
                ScanDeltaItem(
                    path=path,
                    change_type=ScanChangeType.NEW,
                    target_sha256=target_doc.file_index.sha256,
                    target_documento_id=target_doc.documento_id,
                )
            )
            continue

        if base_doc is not None and target_doc is None:
            deleted_items.append(
                ScanDeltaItem(
                    path=path,
                    change_type=ScanChangeType.DELETED,
                    base_sha256=base_doc.file_index.sha256,
                    base_documento_id=base_doc.documento_id,
                )
            )
            continue

        if base_doc is None or target_doc is None:
            continue

        if base_doc.file_index.sha256 != target_doc.file_index.sha256:
            modified_items.append(
                ScanDeltaItem(
                    path=path,
                    change_type=ScanChangeType.MODIFIED,
                    base_sha256=base_doc.file_index.sha256,
                    target_sha256=target_doc.file_index.sha256,
                    base_documento_id=base_doc.documento_id,
                    target_documento_id=target_doc.documento_id,
                )
            )
        elif include_unchanged:
            unchanged_items.append(
                ScanDeltaItem(
                    path=path,
                    change_type=ScanChangeType.UNCHANGED,
                    base_sha256=base_doc.file_index.sha256,
                    target_sha256=target_doc.file_index.sha256,
                    base_documento_id=base_doc.documento_id,
                    target_documento_id=target_doc.documento_id,
                )
            )

    summary = ScanComparisonSummary(
        new_files=len(new_items),
        modified_files=len(modified_items),
        deleted_files=len(deleted_items),
        unchanged_files=len(unchanged_items),
    )

    return ScanComparisonResponse(
        base_job_id=base_job_id,
        target_job_id=target_job_id,
        base_total_documents=len(base_documents),
        target_total_documents=len(target_documents),
        summary=summary,
        new_files=_apply_limit(new_items, limit),
        modified_files=_apply_limit(modified_items, limit),
        deleted_files=_apply_limit(deleted_items, limit),
        unchanged_files=_apply_limit(unchanged_items, limit),
    )
