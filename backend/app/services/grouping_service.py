"""
Grouping service: directory group analysis and similarity computation.

Implements directory group profiling with:
1. Construction of groups in strict/extended modes
2. Aggregation of features (categories, extensions, PII, embeddings)
3. Hybrid similarity metric for group comparison
4. Health scoring and anomaly detection
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np

from app.models.schemas import (
    DocumentMetadata,
    GroupAnalysisResult,
    GroupFeatures,
    GroupMode,
    GroupProfile,
    GroupSimilarity,
    RiskLevel,
)

logger = logging.getLogger(__name__)


def _normalize_path(path: str) -> str:
    """Normalize directory path for grouping."""
    return path.rstrip("/").rstrip("\\")


def _extract_directory_parts(file_path: str) -> list[str]:
    """Extract directory hierarchy from a file path."""
    cleaned = _normalize_path(file_path).replace("\\", "/")
    parts = cleaned.split("/")
    # Remove empty parts and the filename
    return [p for p in parts[:-1] if p]


def _get_parent_directory(file_path: str) -> str:
    """Get parent directory of a file."""
    parts = _extract_directory_parts(file_path)
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def build_groups(
    documents: list[DocumentMetadata],
    mode: GroupMode = GroupMode.STRICT,
) -> dict[str, list[DocumentMetadata]]:
    """
    Build directory groups from documents.

    Args:
        documents: List of classified documents
        mode: GroupMode.STRICT (single directory) or EXTENDED (directory + subtree)

    Returns:
        Dictionary mapping group_path -> list of DocumentMetadata in that group
    """
    groups: dict[str, list[DocumentMetadata]] = defaultdict(list)

    for doc in documents:
        file_path = doc.file_index.path

        if mode == GroupMode.STRICT:
            # Strict: group = immediate parent directory
            group_path = _get_parent_directory(file_path)
            groups[group_path].append(doc)

        elif mode == GroupMode.EXTENDED:
            # Extended: group = deepest common directory with other files
            # For MVP, treat as strict; can be enhanced to group subdir hierarchies
            group_path = _get_parent_directory(file_path)
            groups[group_path].append(doc)

    return groups


def _compute_centroid(embeddings: list[list[float]]) -> list[float] | None:
    """Compute mean embedding from list of embeddings."""
    if not embeddings:
        return None
    try:
        arr = np.array(embeddings)
        centroid = np.mean(arr, axis=0)
        return centroid.tolist()
    except Exception as e:
        logger.warning(f"Failed to compute centroid: {e}")
        return None


def _compute_dispersion(embeddings: list[list[float]]) -> float:
    """Compute standard deviation of embeddings from mean."""
    if len(embeddings) < 2:
        return 0.0

    try:
        arr = np.array(embeddings)
        std = np.std(arr, axis=0)
        # Return mean of stds across dimensions
        return float(np.mean(std))
    except Exception as e:
        logger.warning(f"Failed to compute dispersion: {e}")
        return 0.0


def extract_features(
    documents: list[DocumentMetadata], group_path: str
) -> GroupFeatures:
    """
    Extract aggregated features from a group of documents.

    Args:
        documents: List of documents in the group
        group_path: Path of the group

    Returns:
        GroupFeatures with aggregated data
    """
    if not documents:
        return GroupFeatures(
            group_path=group_path,
            depth=0,
            file_count=0,
            unique_file_count=0,
            duplicate_count=0,
        )

    # Basic counts
    file_count = len(documents)
    unique_count = sum(1 for d in documents if not d.file_index.is_duplicate)
    duplicate_count = file_count - unique_count

    # Depth: number of directory levels
    depth_values = []
    for doc in documents:
        parts = _extract_directory_parts(doc.file_index.path)
        depth_values.append(len(parts))
    mean_depth = int(np.mean(depth_values)) if depth_values else 0

    # Category distribution
    category_dist: dict[str, int] = defaultdict(int)
    for doc in documents:
        category_dist[doc.categoria.value] += 1

    # Extension distribution
    extension_dist: dict[str, int] = defaultdict(int)
    for doc in documents:
        ext = doc.file_index.extension.lower()
        extension_dist[ext] += 1

    # MIME distribution
    mime_dist: dict[str, int] = defaultdict(int)
    for doc in documents:
        if doc.file_index.mime_type:
            mime_dist[doc.file_index.mime_type] += 1

    # Semantic features
    embeddings_list = [
        doc.embedding for doc in documents if doc.embedding is not None
    ]
    semantic_centroid = _compute_centroid(embeddings_list)
    semantic_dispersion = _compute_dispersion(embeddings_list)

    # Dominant category
    if category_dist:
        dominant_cat = max(category_dist.items(), key=lambda x: x[1])
        dominant_category = dominant_cat[0]
        dominant_share = dominant_cat[1] / file_count
    else:
        dominant_category = None
        dominant_share = 0.0

    # PII signals
    pii_count = sum(1 for d in documents if d.pii_info.detected)
    pii_share = pii_count / file_count if file_count > 0 else 0.0

    pii_risk_dist: dict[str, int] = defaultdict(int)
    for doc in documents:
        if doc.pii_info.detected:
            risk_key = doc.pii_info.risk_level.value
            pii_risk_dist[risk_key] += 1

    # Uncategorised
    uncategorised_count = sum(
        1
        for d in documents
        if d.categoria.value == "Desconocido"
    )
    uncategorised_share = (
        uncategorised_count / file_count if file_count > 0 else 0.0
    )

    duplicate_share = duplicate_count / file_count if file_count > 0 else 0.0

    # Temporal signals
    fiscal_dist: dict[str, int] = defaultdict(int)
    date_values = []

    for doc in documents:
        if doc.periodo_fiscal:
            fiscal_dist[doc.periodo_fiscal] += 1
        if doc.fecha_emision:
            date_values.append(doc.fecha_emision)

    date_range_start = min(date_values) if date_values else None
    date_range_end = max(date_values) if date_values else None

    return GroupFeatures(
        group_path=group_path,
        depth=mean_depth,
        file_count=file_count,
        unique_file_count=unique_count,
        duplicate_count=duplicate_count,
        category_distribution=dict(category_dist),
        extension_distribution=dict(extension_dist),
        mime_distribution=dict(mime_dist),
        semantic_centroid=semantic_centroid,
        semantic_dispersion=semantic_dispersion,
        dominant_category=dominant_category,
        dominant_category_share=dominant_share,
        pii_detection_count=pii_count,
        pii_share=pii_share,
        pii_risk_distribution=dict(pii_risk_dist),
        uncategorised_count=uncategorised_count,
        uncategorised_share=uncategorised_share,
        duplicate_share=duplicate_share,
        fiscal_period_distribution=dict(fiscal_dist),
        date_range_start=date_range_start,
        date_range_end=date_range_end,
    )


def _compute_category_overlap(
    dist_a: dict[str, int], dist_b: dict[str, int]
) -> float:
    """Compute Jaccard-like overlap between category distributions."""
    if not dist_a or not dist_b:
        return 0.0

    categories_a = set(dist_a.keys())
    categories_b = set(dist_b.keys())

    if not categories_a or not categories_b:
        return 0.0

    intersection = len(categories_a & categories_b)
    union = len(categories_a | categories_b)

    return intersection / union if union > 0 else 0.0


def _compute_semantic_similarity(
    centroid_a: list[float] | None, centroid_b: list[float] | None
) -> float:
    """Compute cosine similarity between two centroids."""
    if centroid_a is None or centroid_b is None:
        return 0.0

    try:
        a = np.array(centroid_a)
        b = np.array(centroid_b)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = np.dot(a, b) / (norm_a * norm_b)
        return float(max(0.0, min(1.0, similarity)))  # Clamp to [0, 1]
    except Exception as e:
        logger.warning(f"Failed to compute semantic similarity: {e}")
        return 0.0


def _compute_operational_similarity(
    features_a: GroupFeatures, features_b: GroupFeatures
) -> float:
    """
    Compute similarity of PII and duplicate profiles.

    Returns a score normalized to [0, 1].
    """
    # Difference in PII share
    pii_diff = abs(features_a.pii_share - features_b.pii_share)

    # Difference in duplicate share
    dup_diff = abs(features_a.duplicate_share - features_b.duplicate_share)

    # Normalize: max diff is 1.0, so similarity = 1 - avg_diff
    avg_diff = (pii_diff + dup_diff) / 2.0
    return 1.0 - avg_diff


def compute_group_similarity(
    group_a: GroupProfile,
    group_b: GroupProfile,
    weights: dict[str, float] | None = None,
) -> GroupSimilarity:
    """
    Compute hybrid similarity between two groups.

    Uses weighted combination of:
    - Semantic similarity (centroid cosine)
    - Category overlap (Jaccard-like)
    - Operational similarity (PII/duplicate profiles)

    Args:
        group_a: First group profile
        group_b: Second group profile
        weights: Optional weights {semantic, category, operational}

    Returns:
        GroupSimilarity with components and composite score
    """
    if weights is None:
        weights = {
            "semantic": 0.4,
            "category": 0.35,
            "operational": 0.25,
        }

    semantic_sim = _compute_semantic_similarity(
        group_a.features.semantic_centroid, group_b.features.semantic_centroid
    )
    category_sim = _compute_category_overlap(
        group_a.features.category_distribution,
        group_b.features.category_distribution,
    )
    operational_sim = _compute_operational_similarity(
        group_a.features, group_b.features
    )

    # Composite score
    composite = (
        weights["semantic"] * semantic_sim
        + weights["category"] * category_sim
        + weights["operational"] * operational_sim
    )
    composite = float(max(0.0, min(1.0, composite)))

    # Interpret similarity level
    if composite < 0.3:
        similarity_level = "dissimilar"
    elif composite < 0.65:
        similarity_level = "similar"
    else:
        similarity_level = "equivalent"

    return GroupSimilarity(
        group_a_id=group_a.group_id,
        group_b_id=group_b.group_id,
        group_a_path=group_a.group_path,
        group_b_path=group_b.group_path,
        semantic_similarity=semantic_sim,
        category_overlap=category_sim,
        operational_similarity=operational_sim,
        composite_score=composite,
        similarity_level=similarity_level,
        interpretation=f"Groups have {similarity_level} patterns: "
        f"semantic={semantic_sim:.2f}, category={category_sim:.2f}, "
        f"operational={operational_sim:.2f}",
    )


def _compute_health_score(
    features: GroupFeatures, profile_data: dict[str, Any]
) -> tuple[float, dict[str, float], list[str], list[str]]:
    """
    Compute composite health score for a group (0-100).

    Returns:
        (health_score, factor_breakdown, alerts, recommendations)
    """
    factors: dict[str, float] = {}
    alerts: list[str] = []
    recommendations: list[str] = []

    # 1. Coherence: based on semantic dispersion
    # Lower dispersion = higher coherence
    coherence = max(0.0, 1.0 - (features.semantic_dispersion / 2.0))
    factors["coherence"] = coherence

    if features.semantic_dispersion > 0.5:
        alerts.append(
            f"High semantic dispersion ({features.semantic_dispersion:.2f}): "
            "group contains diverse document types"
        )

    # 2. Coverage: based on categorization rate
    if features.file_count > 0:
        coverage = 1.0 - features.uncategorised_share
    else:
        coverage = 0.0
    factors["coverage"] = coverage

    if features.uncategorised_share > 0.2:
        alerts.append(
            f"Low categorization ({features.uncategorised_share:.1%}): "
            "many documents could not be classified"
        )
        recommendations.append(
            "Review uncategorized documents; may indicate "
            "incorrect schema or edge cases"
        )

    # 3. Quality: based on PII/duplicate risk
    # Both high PII share and high duplicate share reduce quality
    quality = 1.0 - (
        0.5 * min(features.pii_share, 1.0) + 0.5 * features.duplicate_share
    )
    factors["quality"] = quality

    if features.pii_share > 0.15:
        alerts.append(
            f"PII detected in {features.pii_share:.1%} of documents: "
            "sensitive data exposure risk"
        )
        recommendations.append("Review and redact PII before sharing documents")

    if features.duplicate_share > 0.2:
        alerts.append(
            f"High duplication ({features.duplicate_share:.1%}): "
            "many identical files present"
        )
        recommendations.append("Consider consolidation or cleanup of duplicates")

    # 4. Risk profile
    if (
        features.pii_risk_distribution.get("rojo", 0) > 0
        or features.pii_risk_distribution.get("amarillo", 0) > 0
    ):
        risk_factor = 0.4  # Significant risk
        alerts.append(
            "High-risk PII detected: credit cards, SSNs, or other sensitive identifiers"
        )
        recommendations.append("Immediate review and remediation recommended")
    else:
        risk_factor = 0.8

    factors["risk_profile"] = risk_factor

    # Composite health score
    weight_coherence = 0.25
    weight_coverage = 0.25
    weight_quality = 0.3
    weight_risk = 0.2

    health = (
        weight_coherence * coherence
        + weight_coverage * coverage
        + weight_quality * quality
        + weight_risk * risk_factor
    )
    health_score = health * 100.0  # Convert to 0-100 scale

    return health_score, factors, alerts, recommendations


def _infer_group_purpose(
    features: GroupFeatures, documents: list[DocumentMetadata]
) -> str:
    """
    Infer the purpose/function of a group based on its characteristics.

    Returns a descriptive string.
    """
    if not documents:
        return "Empty directory"

    # Use dominant category and distribution to infer purpose
    if not features.dominant_category:
        return "Mixed or uncategorized content"

    # Build inference
    parts = []

    if features.dominant_category_share > 0.7:
        parts.append(
            f"Primarily {features.dominant_category}"
            f" ({features.dominant_category_share:.0%})"
        )
    else:
        top_cats = sorted(
            features.category_distribution.items(), key=lambda x: x[1], reverse=True
        )[:3]
        cat_str = ", ".join(f"{c[0]}" for c in top_cats)
        parts.append(f"Mixed: {cat_str}")

    # Add temporal context if available
    if features.fiscal_period_distribution:
        periods = sorted(features.fiscal_period_distribution.keys())
        if len(periods) == 1:
            parts.append(f"(FY {periods[0]})")
        else:
            parts.append(f"(FY {periods[0]} to {periods[-1]})")

    # Add risk context
    if features.pii_share > 0.1:
        parts.append("[Contains PII]")

    return " ".join(parts) if parts else "Mixed content"


def create_group_profile(
    job_id: str,
    group_id: str,
    group_path: str,
    documents: list[DocumentMetadata],
    mode: GroupMode = GroupMode.STRICT,
) -> GroupProfile:
    """
    Create a complete group profile from documents.

    Args:
        job_id: Parent job ID
        group_id: Unique group identifier
        group_path: Directory path of the group
        documents: List of documents in the group
        mode: Grouping mode used

    Returns:
        Complete GroupProfile with analysis results
    """
    # Extract features
    features = extract_features(documents, group_path)

    # Compute health score and derived insights
    health_score, health_factors, alerts, recommendations = (
        _compute_health_score(features, {})
    )

    # Infer purpose
    inferred_purpose = _infer_group_purpose(features, documents)

    # Select representative documents (closest to centroid if embeddings present)
    representative_docs = []
    if features.semantic_centroid is not None and documents:
        centroid = np.array(features.semantic_centroid)

        # Compute distance to centroid for each doc with embedding
        doc_distances = []
        for doc in documents:
            if doc.embedding is not None:
                embedding = np.array(doc.embedding)
                distance = np.linalg.norm(embedding - centroid)
                doc_distances.append((doc.documento_id, distance))

        # Sort by distance and take top 3
        doc_distances.sort(key=lambda x: x[1])
        representative_docs = [doc_id for doc_id, _ in doc_distances[:3]]

    return GroupProfile(
        group_id=group_id,
        job_id=job_id,
        group_path=group_path,
        group_mode=mode,
        created_at=datetime.utcnow().isoformat(),
        features=features,
        inferred_purpose=inferred_purpose,
        health_score=health_score,
        health_factors={k: float(v) for k, v in health_factors.items()},
        alerts=alerts,
        recommendations=recommendations,
        representative_docs=representative_docs,
    )


def analyze_all_groups(
    job_id: str,
    documents: list[DocumentMetadata],
    mode: GroupMode = GroupMode.STRICT,
    top_k_similarities: int = 10,
) -> GroupAnalysisResult:
    """
    Perform complete group analysis on a job's documents.

    Args:
        job_id: Job identifier
        documents: All documents from the job
        mode: Grouping mode (strict/extended)
        top_k_similarities: Number of top similarities to keep

    Returns:
        Complete GroupAnalysisResult with all groups and similarities
    """
    # Build groups
    dir_groups = build_groups(documents, mode)

    # Create profiles for each group
    profiles = []
    for i, (group_path, group_docs) in enumerate(dir_groups.items()):
        group_id = f"group_{i:04d}"
        profile = create_group_profile(
            job_id=job_id,
            group_id=group_id,
            group_path=group_path,
            documents=group_docs,
            mode=mode,
        )
        profiles.append(profile)

    logger.info(f"Created {len(profiles)} group profiles for job {job_id}")

    # Compute pairwise similarities
    all_similarities = []
    for i, group_a in enumerate(profiles):
        for group_b in profiles[i + 1 :]:
            similarity = compute_group_similarity(group_a, group_b)
            all_similarities.append(similarity)

    # Keep top k by composite score
    all_similarities.sort(key=lambda x: x.composite_score, reverse=True)
    top_similarities = all_similarities[:top_k_similarities]

    return GroupAnalysisResult(
        job_id=job_id,
        group_count=len(profiles),
        total_groups_analyzed=len(profiles),
        groups=profiles,
        group_similarities=top_similarities,
        analysis_timestamp=datetime.utcnow().isoformat(),
    )
