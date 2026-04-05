from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from app.models.schemas import (
    ClusterSummary,
    CorpusExplorationReport,
    CorpusFacetItem,
    DataHealthReport,
    DirectoryHotspot,
    DocumentMetadata,
    JobStatistics,
    RelationEdge,
    RelationGraph,
    RelationNode,
    TemporalBucket,
    TopicSummary,
)

_SIZE_BUCKETS: list[tuple[int, str]] = [
    (1 * 1024 * 1024, "<1MB"),
    (10 * 1024 * 1024, "1-10MB"),
    (100 * 1024 * 1024, "10-100MB"),
]


def normalize_extension(extension: str | None) -> str:
    if not extension:
        return "(sin extensión)"

    value = extension.strip().lower()
    if not value or value == ".":
        return "(sin extensión)"
    if not value.startswith("."):
        value = f".{value}"
    return value


def normalize_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return "(desconocido)"
    return mime_type.strip().lower() or "(desconocido)"


def bucket_file_size(size_bytes: int) -> str:
    for threshold, label in _SIZE_BUCKETS:
        if size_bytes < threshold:
            return label
    return ">100MB"


def normalize_directory(path: str) -> str:
    parent = Path(path).parent
    return parent.as_posix() or "."


def _bucket_month(date_value: str | None) -> str:
    if not date_value:
        return "(desconocido)"
    try:
        parsed = datetime.fromisoformat(date_value)
        return f"{parsed.year}-{parsed.month:02d}"
    except ValueError:
        return "(desconocido)"


def _document_month_bucket(doc: DocumentMetadata) -> str:
    month = _bucket_month(doc.fecha_emision)
    if month == "(desconocido)":
        return _bucket_month(doc.file_index.modified_at)
    return month


def _build_relation_graph(documents: list[DocumentMetadata]) -> RelationGraph:
    nodes: dict[str, RelationNode] = {}
    edges: dict[tuple[str, str, str], int] = {}

    def add_node(node_id: str, label: str, kind: str, group: str | None = None) -> None:
        if node_id not in nodes:
            nodes[node_id] = RelationNode(
                id=node_id,
                label=label,
                kind=kind,
                group=group,
            )

    def add_edge(source: str, target: str, relation_type: str) -> None:
        key = (source, target, relation_type)
        edges[key] = edges.get(key, 0) + 1

    for doc in documents:
        doc_node_id = f"doc::{doc.documento_id}"
        add_node(
            doc_node_id,
            Path(doc.file_index.path).name or doc.documento_id,
            "document",
            doc.categoria.value,
        )

        if doc.relaciones.id_ot_referencia:
            ot_node_id = f"ot::{doc.relaciones.id_ot_referencia}"
            add_node(
                ot_node_id,
                doc.relaciones.id_ot_referencia,
                "work_order",
                "Orden_Trabajo",
            )
            add_edge(doc_node_id, ot_node_id, "referencia_OT")

        if doc.relaciones.id_licitacion_vinculada:
            tender_node_id = f"tender::{doc.relaciones.id_licitacion_vinculada}"
            add_node(
                tender_node_id,
                doc.relaciones.id_licitacion_vinculada,
                "tender",
                "Licitacion",
            )
            add_edge(doc_node_id, tender_node_id, "referencia_Licitacion")

    return RelationGraph(
        nodes=list(nodes.values()),
        edges=[
            RelationEdge(
                source=src,
                target=tgt,
                relation_type=rel,
                count=count,
            )
            for (src, tgt, rel), count in edges.items()
        ],
        node_count=len(nodes),
        edge_count=len(edges),
    )


def build_job_statistics(
    job_id: str,
    report: DataHealthReport,
    documents: list[DocumentMetadata],
) -> JobStatistics:
    extension_breakdown = Counter(
        normalize_extension(doc.file_index.extension) for doc in documents
    )
    category_distribution = Counter(doc.categoria.value for doc in documents)
    mime_breakdown = Counter(
        normalize_mime_type(doc.file_index.mime_type) for doc in documents
    )
    size_bucket_distribution = Counter(
        bucket_file_size(doc.file_index.size_bytes) for doc in documents
    )
    directory_breakdown = Counter(
        normalize_directory(doc.file_index.path) for doc in documents
    )
    temporal_distribution = Counter(_document_month_bucket(doc) for doc in documents)
    pii_risk_distribution = Counter(doc.pii_info.risk_level.value for doc in documents)
    keyword_distribution = Counter(
        keyword.lower().strip()
        for doc in documents
        for keyword in doc.analisis_semantico.palabras_clave
        if keyword and keyword.strip()
    )

    cluster_summary = [
        ClusterSummary(
            cluster_id=c.cluster_id,
            label=c.label,
            document_count=c.document_count,
            inconsistency_count=len(c.inconsistencies),
        )
        for c in report.clusters
    ]

    classified_documents = sum(
        1 for doc in documents if doc.categoria.value != "Desconocido"
    )
    semantic_coverage = (
        classified_documents / len(documents) if documents else 0.0
    )

    return JobStatistics(
        job_id=job_id,
        total_files=report.total_files,
        unique_files=report.total_files - report.duplicates,
        duplicate_files=report.duplicates,
        extension_breakdown=dict(extension_breakdown),
        category_distribution=dict(category_distribution),
        mime_breakdown=dict(mime_breakdown),
        size_bucket_distribution=dict(size_bucket_distribution),
        directory_breakdown=dict(directory_breakdown),
        temporal_distribution=dict(temporal_distribution),
        pii_risk_distribution=dict(pii_risk_distribution),
        keyword_distribution=dict(keyword_distribution),
        semantic_coverage=semantic_coverage,
        cluster_summary=cluster_summary,
    )


def _share(count: int, total: int) -> float:
    return count / total if total else 0.0


def build_corpus_exploration(
    job_id: str,
    report: DataHealthReport,
    documents: list[DocumentMetadata],
) -> CorpusExplorationReport:
    total = len(documents)
    if total == 0:
        return CorpusExplorationReport(
            job_id=job_id,
            total_files=report.total_files,
            unique_files=report.total_files - report.duplicates,
            duplicate_files=report.duplicates,
        )

    extension_counts = Counter(
        normalize_extension(doc.file_index.extension) for doc in documents
    )
    directory_counts = Counter(
        normalize_directory(doc.file_index.path) for doc in documents
    )
    category_counts = Counter(doc.categoria.value for doc in documents)
    docs_by_directory: dict[str, list[DocumentMetadata]] = {}
    for doc in documents:
        docs_by_directory.setdefault(normalize_directory(doc.file_index.path), []).append(doc)

    top_extensions = [
        CorpusFacetItem(
            label=label,
            count=count,
            share=_share(count, total),
        )
        for label, count in extension_counts.most_common(5)
    ]
    top_directories = [
        CorpusFacetItem(
            label=label,
            count=count,
            share=_share(count, total),
        )
        for label, count in directory_counts.most_common(5)
    ]
    dominant_categories = [
        CorpusFacetItem(
            label=label,
            count=count,
            share=_share(count, total),
        )
        for label, count in category_counts.most_common(5)
    ]

    cluster_docs = {
        cluster.label: cluster.document_count for cluster in report.clusters
    }
    cluster_inconsistencies = {
        cluster.label: len(cluster.inconsistencies) for cluster in report.clusters
    }
    dominant_clusters = [
        TopicSummary(
            label=label,
            document_count=count,
            inconsistency_count=cluster_inconsistencies.get(label, 0),
            share=_share(count, total),
        )
        for label, count in sorted(
            cluster_docs.items(), key=lambda item: item[1], reverse=True
        )[:5]
    ]

    temporal_counts = Counter(_document_month_bucket(doc) for doc in documents)
    temporal_heatmap = [
        TemporalBucket(label=label, count=count, share=_share(count, total))
        for label, count in sorted(
            temporal_counts.items(), key=lambda item: item[0]
        )
    ]

    relation_graph = _build_relation_graph(documents)

    noisy_directories: list[DirectoryHotspot] = []
    for path, docs in sorted(
        docs_by_directory.items(), key=lambda item: len(item[1]), reverse=True
    )[:5]:
        duplicate_count = sum(1 for doc in docs if doc.file_index.is_duplicate)
        unknown_count = sum(
            1 for doc in docs if doc.categoria.value == "Desconocido"
        )
        noisy_directories.append(
            DirectoryHotspot(
                path=path,
                count=len(docs),
                duplicate_count=duplicate_count,
                unknown_count=unknown_count,
                share=_share(len(docs), total),
            )
        )

    uncategorised = sum(
        1 for doc in documents if doc.categoria.value == "Desconocido"
    )
    pii_count = sum(1 for doc in documents if doc.pii_info.detected)
    concentration_index = max(
        [*(count for count in extension_counts.values()), *(count for count in directory_counts.values()), 0]
    ) / total

    return CorpusExplorationReport(
        job_id=job_id,
        total_files=report.total_files,
        unique_files=report.total_files - report.duplicates,
        duplicate_files=report.duplicates,
        top_extensions=top_extensions,
        top_directories=top_directories,
        dominant_categories=dominant_categories,
        dominant_clusters=dominant_clusters,
        noisy_directories=noisy_directories,
        temporal_heatmap=temporal_heatmap,
        relation_graph=relation_graph,
        uncategorised_share=_share(uncategorised, total),
        pii_share=_share(pii_count, total),
        concentration_index=concentration_index,
    )
