from __future__ import annotations

"""
Clustering service – groups documents by semantic similarity.

When real embeddings are available (from ChromaDB) we use HDBSCAN.
When embeddings are not available we fall back to a simple label-based grouping
using the *cluster_sugerido* field that Gemini returns.
"""

import logging
from collections import defaultdict

import numpy as np

from app.models.schemas import Cluster, ClusterItem, DocumentMetadata

logger = logging.getLogger(__name__)


def _try_hdbscan(
    embeddings: list[list[float]],
    ids: list[str],
    docs_by_id: dict[str, DocumentMetadata],
) -> list[Cluster] | None:
    """Attempt HDBSCAN clustering; return None if the library is missing."""
    try:
        import hdbscan  # type: ignore

        matrix = np.array(embeddings, dtype=np.float32)
        # Normalise for cosine distance
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        matrix = matrix / norms

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=max(2, len(embeddings) // 20),
            metric="euclidean",
        )
        labels = clusterer.fit_predict(matrix)

        clusters_map: dict[int, list[str]] = defaultdict(list)
        for doc_id, label in zip(ids, labels):
            clusters_map[int(label)].append(doc_id)

        results: list[Cluster] = []
        for label_id, cluster_ids in clusters_map.items():
            if label_id == -1:
                cluster_label = "Sin_Cluster"
            else:
                # Use the most common cluster_sugerido in the group as label
                labels_text = [
                    docs_by_id[i].analisis_semantico.cluster_sugerido or "Sin_Cluster"
                    for i in cluster_ids
                    if i in docs_by_id
                ]
                cluster_label = (
                    max(set(labels_text), key=labels_text.count)
                    if labels_text
                    else f"Cluster_{label_id}"
                )

            items = [
                ClusterItem(
                    documento_id=i,
                    path=docs_by_id[i].file_index.path if i in docs_by_id else "",
                    categoria=docs_by_id[i].categoria.value if i in docs_by_id else "",
                    resumen=docs_by_id[i].analisis_semantico.resumen if i in docs_by_id else None,
                )
                for i in cluster_ids
            ]
            results.append(
                Cluster(
                    cluster_id=f"cluster_{label_id}",
                    label=cluster_label,
                    document_count=len(items),
                    documents=items,
                )
            )
        return results
    except ImportError:
        logger.warning("hdbscan not installed – falling back to label-based clustering")
        return None


def _label_based_clustering(documents: list[DocumentMetadata]) -> list[Cluster]:
    """Group documents by the cluster_sugerido label Gemini assigned."""
    groups: dict[str, list[DocumentMetadata]] = defaultdict(list)
    for doc in documents:
        key = doc.analisis_semantico.cluster_sugerido or "Sin_Cluster"
        groups[key].append(doc)

    clusters = []
    for idx, (label, docs) in enumerate(groups.items()):
        items = [
            ClusterItem(
                documento_id=d.documento_id,
                path=d.file_index.path,
                categoria=d.categoria.value,
                resumen=d.analisis_semantico.resumen,
            )
            for d in docs
        ]
        clusters.append(
            Cluster(
                cluster_id=f"cluster_{idx}",
                label=label,
                document_count=len(items),
                documents=items,
            )
        )
    return clusters


def build_clusters(
    documents: list[DocumentMetadata],
    chroma_data: list[dict] | None = None,
) -> list[Cluster]:
    """
    Build semantic clusters from a list of processed documents.

    If ChromaDB embeddings are available, use HDBSCAN.
    Otherwise fall back to Gemini's *cluster_sugerido* label.
    """
    if not documents:
        return []

    if chroma_data:
        ids = [item["id"] for item in chroma_data]
        embeddings = [item["embedding"] for item in chroma_data]
        docs_by_id = {d.documento_id: d for d in documents}
        result = _try_hdbscan(embeddings, ids, docs_by_id)
        if result is not None:
            return result

    return _label_based_clustering(documents)


def detect_inconsistencies(clusters: list[Cluster], documents: list[DocumentMetadata]) -> list[Cluster]:
    """
    Add consistency warnings to clusters.

    Current rules:
    - Invoices (Factura_Proveedor) without a linked Work Order (id_ot_referencia)
    - Tender docs (Licitacion) without a tender ID (id_licitacion_vinculada)
    """
    docs_by_id = {d.documento_id: d for d in documents}

    for cluster in clusters:
        errors: list[str] = []
        for item in cluster.documents:
            doc = docs_by_id.get(item.documento_id)
            if doc is None:
                continue
            if (
                doc.categoria.value == "Factura_Proveedor"
                and not doc.relaciones.id_ot_referencia
            ):
                errors.append(
                    f"Factura sin OT vinculada: {doc.file_index.name}"
                )
            if (
                doc.categoria.value == "Licitacion"
                and not doc.relaciones.id_licitacion_vinculada
            ):
                errors.append(
                    f"Licitación sin ID de proyecto: {doc.file_index.name}"
                )
        cluster.inconsistencies = errors

    return clusters
