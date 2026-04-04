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


def _normalize_embeddings(embeddings: list[list[float]]) -> np.ndarray:
    matrix = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return matrix / norms


def _try_hdbscan(
    embeddings: list[list[float]],
    ids: list[str],
    docs_by_id: dict[str, DocumentMetadata],
    is_chunk: bool = False,
    chunk_to_document: dict[str, str] | None = None,
) -> list[Cluster] | None:
    """Attempt HDBSCAN clustering; return None if the library is missing."""
    try:
        import hdbscan  # type: ignore

        matrix = _normalize_embeddings(embeddings)

        clusterer = hdbscan.HDBSCAN(
            # A minimum cluster size of ~5 % of the corpus avoids overfitting
            # on small datasets while still forming meaningful groups for
            # larger collections. The floor of 2 ensures HDBSCAN can always
            # form at least one cluster regardless of corpus size.
            min_cluster_size=max(2, len(embeddings) // 20),
            metric="euclidean",
        )
        labels = clusterer.fit_predict(matrix)

        clusters_map: dict[int, list[str]] = defaultdict(list)
        for item_id, label in zip(ids, labels):
            clusters_map[int(label)].append(item_id)

        results: list[Cluster] = []
        for label_id, item_ids in clusters_map.items():
            if label_id == -1:
                cluster_label = "Sin_Cluster"
            else:
                labels_text: list[str] = []
                if is_chunk and chunk_to_document is not None:
                    for chunk_id in item_ids:
                        doc_id = chunk_to_document.get(chunk_id)
                        if doc_id and doc_id in docs_by_id:
                            labels_text.append(
                                docs_by_id[doc_id].analisis_semantico.cluster_sugerido
                                or "Sin_Cluster"
                            )
                else:
                    labels_text = [
                        docs_by_id[item_id].analisis_semantico.cluster_sugerido or "Sin_Cluster"
                        for item_id in item_ids
                        if item_id in docs_by_id
                    ]
                cluster_label = (
                    max(set(labels_text), key=labels_text.count)
                    if labels_text
                    else f"Cluster_{label_id}"
                )

            if is_chunk and chunk_to_document is not None:
                seen: set[str] = set()
                documents_in_cluster: list[str] = []
                for chunk_id in item_ids:
                    doc_id = chunk_to_document.get(chunk_id)
                    if doc_id and doc_id not in seen:
                        seen.add(doc_id)
                        documents_in_cluster.append(doc_id)
                items = [
                    ClusterItem(
                        documento_id=doc_id,
                        path=docs_by_id[doc_id].file_index.path,
                        categoria=docs_by_id[doc_id].categoria.value,
                        resumen=docs_by_id[doc_id].analisis_semantico.resumen,
                    )
                    for doc_id in documents_in_cluster
                    if doc_id in docs_by_id
                ]
            else:
                items = [
                    ClusterItem(
                        documento_id=item_id,
                        path=docs_by_id[item_id].file_index.path if item_id in docs_by_id else "",
                        categoria=docs_by_id[item_id].categoria.value if item_id in docs_by_id else "",
                        resumen=docs_by_id[item_id].analisis_semantico.resumen if item_id in docs_by_id else None,
                    )
                    for item_id in item_ids
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
    except Exception as exc:  # noqa: BLE001
        logger.error("HDBSCAN clustering failed: %s", exc)
        return None


def _try_hdbscan_on_chunks(
    chroma_data: list[dict],
    docs_by_id: dict[str, DocumentMetadata],
) -> list[Cluster] | None:
    chunk_records = [
        item for item in chroma_data if str(item.get("id", "")).startswith("chunk::")
    ]
    if not chunk_records:
        return None

    ids: list[str] = []
    embeddings: list[list[float]] = []
    chunk_to_document: dict[str, str] = {}

    for item in chunk_records:
        record_id = str(item.get("id", ""))
        chunk_id = record_id.removeprefix("chunk::")
        metadata = item.get("metadata") or {}
        document_id = metadata.get("document_id")
        if not document_id:
            continue
        embedding = item.get("embedding")
        if not embedding:
            continue
        ids.append(chunk_id)
        embeddings.append(embedding)
        chunk_to_document[chunk_id] = document_id

    if not ids or not embeddings:
        return None

    return _try_hdbscan(
        embeddings=embeddings,
        ids=ids,
        docs_by_id=docs_by_id,
        is_chunk=True,
        chunk_to_document=chunk_to_document,
    )


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

    Prefer HDBSCAN over chunk-level embeddings when available.
    If chunk embeddings are missing, fall back to document embeddings.
    If no embeddings are present, use Gemini's *cluster_sugerido* label.
    """
    if not documents:
        return []

    if chroma_data:
        docs_by_id = {d.documento_id: d for d in documents}

        chunk_result = _try_hdbscan_on_chunks(chroma_data, docs_by_id)
        if chunk_result is not None:
            return chunk_result

        doc_records = [
            item for item in chroma_data if str(item.get("id", "")).startswith("doc::")
        ]
        if doc_records:
            ids = [str(item["id"]).removeprefix("doc::") for item in doc_records]
            embeddings = [item["embedding"] for item in doc_records]
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
