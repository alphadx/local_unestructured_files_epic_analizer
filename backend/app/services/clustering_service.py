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


def _simplify_cluster_label(label: str) -> str:
    if not label:
        return "Mixto"
    normalized = label.replace("-", "_").strip("_")
    parts = [part for part in normalized.split("_") if part]
    if len(parts) > 1 and parts[-1].isdigit():
        parts = parts[:-1]
    if len(parts) > 1 and parts[-1].lower() in {"final", "draft", "borrador", "v1", "v2"}:
        parts = parts[:-1]
    return "_".join(parts) or label


def _cluster_namer(documents: list[DocumentMetadata]) -> str:
    if not documents:
        return "Sin_Cluster"

    label_counts: dict[str, int] = {}
    for doc in documents:
        label = doc.analisis_semantico.cluster_sugerido or ""
        if label:
            label_counts[label] = label_counts.get(label, 0) + 1

    if label_counts:
        most_common_label, count = max(label_counts.items(), key=lambda item: item[1])
        if count / len(documents) >= 0.6:
            return _simplify_cluster_label(most_common_label)

        base_counts: dict[str, int] = {}
        for label, label_count in label_counts.items():
            base = _simplify_cluster_label(label)
            base_counts[base] = base_counts.get(base, 0) + label_count
        top_base, top_base_count = max(base_counts.items(), key=lambda item: item[1])
        if top_base_count / len(documents) >= 0.4:
            return top_base

    category_counts: dict[str, int] = {}
    for doc in documents:
        category_counts[doc.categoria.value] = category_counts.get(doc.categoria.value, 0) + 1

    if category_counts:
        top_category, top_count = max(category_counts.items(), key=lambda item: item[1])
        if top_count / len(documents) >= 0.5:
            return top_category
        sorted_categories = sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
        return "Mixto: " + ", ".join(cat for cat, _ in sorted_categories[:2])

    return "Sin_Cluster"


def _build_cluster_items(item_ids: list[str], docs_by_id: dict[str, DocumentMetadata]) -> list[ClusterItem]:
    return [
        ClusterItem(
            documento_id=item_id,
            path=docs_by_id[item_id].file_index.path if item_id in docs_by_id else "",
            categoria=docs_by_id[item_id].categoria.value if item_id in docs_by_id else "",
            resumen=docs_by_id[item_id].analisis_semantico.resumen if item_id in docs_by_id else None,
        )
        for item_id in item_ids
        if item_id in docs_by_id
    ]


def _build_clusters_from_labels(
    labels: list[int],
    ids: list[str],
    docs_by_id: dict[str, DocumentMetadata],
    method: str = "dbscan",
) -> list[Cluster]:
    clusters_map: dict[int, list[str]] = defaultdict(list)
    for item_id, label in zip(ids, labels):
        clusters_map[int(label)].append(item_id)

    results: list[Cluster] = []
    for label_id, item_ids in clusters_map.items():
        if label_id == -1:
            cluster_label = "Sin_Cluster"
        else:
            docs = [docs_by_id[item_id] for item_id in item_ids if item_id in docs_by_id]
            cluster_label = _cluster_namer(docs)

        results.append(
            Cluster(
                cluster_id=f"{method}_cluster_{label_id}",
                label=cluster_label,
                document_count=len(item_ids),
                documents=_build_cluster_items(item_ids, docs_by_id),
            )
        )
    return results


def _cluster_centroid(cluster: Cluster, docs_by_id: dict[str, DocumentMetadata]) -> np.ndarray | None:
    embeddings: list[list[float]] = []
    for item in cluster.documents:
        doc = docs_by_id.get(item.documento_id)
        if doc is None or doc.embedding is None:
            continue
        embeddings.append(doc.embedding)
    if not embeddings:
        return None
    arr = np.array(embeddings, dtype=np.float32)
    centroid = np.mean(arr, axis=0)
    norm = np.linalg.norm(centroid)
    if norm == 0:
        return None
    return centroid / norm


def _family_namer(clusters: list[Cluster]) -> str:
    if not clusters:
        return "Familia"
    label_counts: dict[str, int] = {}
    for cluster in clusters:
        label = _simplify_cluster_label(cluster.label)
        label_counts[label] = label_counts.get(label, 0) + cluster.document_count
    top_label, count = max(label_counts.items(), key=lambda item: item[1])
    if count / sum(label_counts.values()) >= 0.5:
        return top_label
    if len(label_counts) == 1:
        return top_label
    sorted_labels = sorted(label_counts.items(), key=lambda item: item[1], reverse=True)
    return "Familia: " + ", ".join(label for label, _ in sorted_labels[:2])


def _assign_cluster_families(clusters: list[Cluster], docs_by_id: dict[str, DocumentMetadata]) -> None:
    centroids: list[np.ndarray] = []
    valid_clusters: list[Cluster] = []

    for cluster in clusters:
        centroid = _cluster_centroid(cluster, docs_by_id)
        if centroid is not None:
            centroids.append(centroid)
            valid_clusters.append(cluster)

    if len(valid_clusters) < 2:
        for cluster in clusters:
            cluster.family_label = _simplify_cluster_label(cluster.label)
        return

    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError:
        for cluster in clusters:
            cluster.family_label = _simplify_cluster_label(cluster.label)
        return

    try:
        matrix = np.vstack(centroids)
        try:
            family_clustering = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=0.35,
                linkage="average",
                metric="cosine",
            ).fit(matrix)
        except TypeError:
            family_clustering = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=0.35,
                linkage="average",
                affinity="cosine",
            ).fit(matrix)

        family_labels = family_clustering.labels_.tolist()
        family_groups: dict[int, list[Cluster]] = defaultdict(list)
        for cluster, family_id in zip(valid_clusters, family_labels):
            family_groups[family_id].append(cluster)

        family_name_by_id: dict[int, str] = {
            fid: _family_namer(group) for fid, group in family_groups.items()
        }
        for cluster, family_id in zip(valid_clusters, family_labels):
            cluster.family_label = family_name_by_id[family_id]

        for cluster in clusters:
            if cluster.family_label is None:
                cluster.family_label = _simplify_cluster_label(cluster.label)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Family clustering failed: %s", exc)
        for cluster in clusters:
            cluster.family_label = _simplify_cluster_label(cluster.label)


def _try_dbscan(
    embeddings: list[list[float]],
    ids: list[str],
    docs_by_id: dict[str, DocumentMetadata],
) -> list[Cluster] | None:
    """Attempt DBSCAN clustering; return None if sklearn is unavailable."""
    try:
        from sklearn.cluster import DBSCAN
    except ImportError:
        logger.warning("sklearn not installed – DBSCAN unavailable")
        return None

    try:
        matrix = _normalize_embeddings(embeddings)
        clusterer = DBSCAN(
            eps=0.5,
            min_samples=max(2, len(embeddings) // 20),
            metric="cosine",
        )
        labels = clusterer.fit_predict(matrix).tolist()
        if all(label == -1 for label in labels):
            return None
        return _build_clusters_from_labels(labels, ids, docs_by_id, method="dbscan")
    except Exception as exc:  # noqa: BLE001
        logger.warning("DBSCAN clustering failed: %s", exc)
        return None


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

    docs_by_id = {d.documento_id: d for d in documents}

    if chroma_data:
        chunk_result = _try_hdbscan_on_chunks(chroma_data, docs_by_id)
        if chunk_result is not None:
            _assign_cluster_families(chunk_result, docs_by_id)
            return chunk_result

        doc_records = [
            item for item in chroma_data if str(item.get("id", "")).startswith("doc::")
        ]
        if doc_records:
            ids = [str(item["id"]).removeprefix("doc::") for item in doc_records]
            embeddings = [item["embedding"] for item in doc_records]
            dbscan_result = _try_dbscan(embeddings, ids, docs_by_id)
            if dbscan_result is not None:
                _assign_cluster_families(dbscan_result, docs_by_id)
                return dbscan_result
            hdbscan_result = _try_hdbscan(embeddings, ids, docs_by_id)
            if hdbscan_result is not None:
                _assign_cluster_families(hdbscan_result, docs_by_id)
                return hdbscan_result

    label_result = _label_based_clustering(documents)
    _assign_cluster_families(label_result, docs_by_id)
    return label_result


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
