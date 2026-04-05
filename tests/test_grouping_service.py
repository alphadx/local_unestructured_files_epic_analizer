"""
Tests for grouping service – directory group analysis and similarity.

Tests cover:
- Group construction (strict/extended modes)
- Feature extraction (categories, embeddings, PII, temporal)
- Health scoring
- Similarity computation
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import (
    DocumentCategory,
    DocumentMetadata,
    DocumentRelations,
    FileIndex,
    GroupMode,
    PiiInfo,
    RiskLevel,
    SemanticAnalysis,
)
from app.services.grouping_service import (
    build_groups,
    extract_features,
    create_group_profile,
    compute_group_similarity,
    analyze_all_groups,
    _compute_category_overlap,
    _compute_operational_similarity,
)


def _make_doc(
    doc_id: str,
    path: str,
    categoria: DocumentCategory = DocumentCategory.INVOICE,
    cluster_label: str = "test_cluster",
    embedding: list[float] | None = None,
    pii_detected: bool = False,
    pii_level: RiskLevel = RiskLevel.GREEN,
    fecha_emision: str | None = None,
    periodo_fiscal: str | None = None,
) -> DocumentMetadata:
    """Helper to create test documents."""
    fi = FileIndex(
        path=path,
        name=Path(path).name,
        extension=Path(path).suffix,
        size_bytes=100,
        created_at="2026-01-01T00:00:00",
        modified_at="2026-01-01T00:00:00",
        sha256=doc_id,
    )
    return DocumentMetadata(
        documento_id=doc_id,
        file_index=fi,
        categoria=categoria,
        analisis_semantico=SemanticAnalysis(
            resumen="Resumen de prueba",
            cluster_sugerido=cluster_label,
            confianza_clasificacion=0.9,
            palabras_clave=["test"],
        ),
        pii_info=PiiInfo(detected=pii_detected, risk_level=pii_level),
        fecha_emision=fecha_emision,
        periodo_fiscal=periodo_fiscal,
        embedding=embedding,
    )


class TestGroupConstruction:
    def test_strict_mode_groups_by_parent_dir(self):
        """In strict mode, files are grouped by immediate parent directory."""
        docs = [
            _make_doc("doc1", "/path/group_a/file1.pdf"),
            _make_doc("doc2", "/path/group_a/file2.pdf"),
            _make_doc("doc3", "/path/group_b/file3.pdf"),
        ]
        groups = build_groups(docs, GroupMode.STRICT)

        # Should have two groups
        assert len(groups) == 2
        assert "/path/group_a" in groups
        assert "/path/group_b" in groups
        assert len(groups["/path/group_a"]) == 2
        assert len(groups["/path/group_b"]) == 1

    def test_empty_docs_returns_empty(self):
        """Empty document list returns empty groups."""
        groups = build_groups([], GroupMode.STRICT)
        assert groups == {}

    def test_single_doc_single_group(self):
        """Single document creates single group."""
        docs = [_make_doc("doc1", "/path/file1.pdf")]
        groups = build_groups(docs, GroupMode.STRICT)
        assert len(groups) == 1
        assert len(list(groups.values())[0]) == 1

    def test_extended_mode_groups_by_ancestor_dirs(self):
        """Extended mode groups files into each parent directory ancestor."""
        docs = [
            _make_doc("doc1", "/path/a/file1.pdf"),
            _make_doc("doc2", "/path/a/b/file2.pdf"),
        ]
        groups_extended = build_groups(docs, GroupMode.EXTENDED)

        assert "/path" in groups_extended
        assert "/path/a" in groups_extended
        assert "/path/a/b" in groups_extended
        assert len(groups_extended["/path"]) == 2
        assert len(groups_extended["/path/a"]) == 2
        assert len(groups_extended["/path/a/b"]) == 1


class TestFeatureExtraction:
    def test_basic_features(self):
        """Extract basic feature counts."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", DocumentCategory.INVOICE),
            _make_doc("doc2", "/path/file2.pdf", DocumentCategory.INVOICE),
            _make_doc("doc3", "/path/file3.xlsx", DocumentCategory.UNKNOWN),
        ]
        features = extract_features(docs, "/path")

        assert features.group_path == "/path"
        assert features.file_count == 3
        assert features.unique_file_count == 3
        assert features.duplicate_count == 0

    def test_category_distribution(self):
        """Extract category distribution."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", DocumentCategory.INVOICE),
            _make_doc("doc2", "/path/file2.pdf", DocumentCategory.INVOICE),
            _make_doc("doc3", "/path/file3.pdf", DocumentCategory.CONTRACT),
        ]
        features = extract_features(docs, "/path")

        assert features.category_distribution["Factura_Proveedor"] == 2
        assert features.category_distribution["Contrato"] == 1
        assert features.dominant_category == "Factura_Proveedor"
        assert features.dominant_category_share == pytest.approx(2 / 3, rel=0.01)

    def test_pii_detection(self):
        """Extract PII signals."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", pii_detected=True, pii_level=RiskLevel.RED),
            _make_doc("doc2", "/path/file2.pdf", pii_detected=False),
            _make_doc("doc3", "/path/file3.pdf", pii_detected=True, pii_level=RiskLevel.YELLOW),
        ]
        features = extract_features(docs, "/path")

        assert features.pii_detection_count == 2
        assert features.pii_share == pytest.approx(2 / 3, rel=0.01)
        assert features.pii_risk_distribution["rojo"] == 1
        assert features.pii_risk_distribution["amarillo"] == 1

    def test_temporal_features(self):
        """Extract temporal signals."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", fecha_emision="2026-01-10", periodo_fiscal="2026-01"),
            _make_doc("doc2", "/path/file2.pdf", fecha_emision="2026-01-15", periodo_fiscal="2026-01"),
            _make_doc("doc3", "/path/file3.pdf", fecha_emision="2026-02-10", periodo_fiscal="2026-02"),
        ]
        features = extract_features(docs, "/path")

        assert features.fiscal_period_distribution["2026-01"] == 2
        assert features.fiscal_period_distribution["2026-02"] == 1
        assert features.date_range_start == "2026-01-10"
        assert features.date_range_end == "2026-02-10"

    def test_uncategorised_count(self):
        """Extract uncategorized document count."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", DocumentCategory.INVOICE),
            _make_doc("doc2", "/path/file2.pdf", DocumentCategory.UNKNOWN),
            _make_doc("doc3", "/path/file3.pdf", DocumentCategory.UNKNOWN),
        ]
        features = extract_features(docs, "/path")

        assert features.uncategorised_count == 2
        assert features.uncategorised_share == pytest.approx(2 / 3, rel=0.01)

    def test_semantic_features_with_embeddings(self):
        """Extract semantic features when embeddings present."""
        # Simple 2D embeddings for testing
        emb1 = [1.0, 0.0]
        emb2 = [0.8, 0.2]
        emb3 = [0.6, 0.4]

        docs = [
            _make_doc("doc1", "/path/file1.pdf", embedding=emb1),
            _make_doc("doc2", "/path/file2.pdf", embedding=emb2),
            _make_doc("doc3", "/path/file3.pdf", embedding=emb3),
        ]
        features = extract_features(docs, "/path")

        assert features.semantic_centroid is not None
        assert len(features.semantic_centroid) == 2
        # Centroid should be ~[0.8, 0.2]
        assert features.semantic_dispersion >= 0.0


class TestGroupProfile:
    def test_create_profile_basic(self):
        """Create a basic group profile."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", DocumentCategory.INVOICE),
            _make_doc("doc2", "/path/file2.pdf", DocumentCategory.INVOICE),
        ]
        profile = create_group_profile(
            job_id="job123",
            group_id="group_001",
            group_path="/path",
            documents=docs,
            mode=GroupMode.STRICT,
        )

        assert profile.group_id == "group_001"
        assert profile.job_id == "job123"
        assert profile.group_path == "/path"
        assert profile.group_mode == GroupMode.STRICT
        assert 0 <= profile.health_score <= 100

    def test_health_score_computed(self):
        """Health score should be computed."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", DocumentCategory.INVOICE),
            _make_doc("doc2", "/path/file2.pdf", DocumentCategory.INVOICE),
        ]
        profile = create_group_profile(
            job_id="job123",
            group_id="group_001",
            group_path="/path",
            documents=docs,
        )

        assert profile.health_score > 0  # Should have positive health
        assert "coherence" in profile.health_factors
        assert "coverage" in profile.health_factors

    def test_alerts_for_high_pii(self):
        """Alerts should be generated for high PII."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", pii_detected=True, pii_level=RiskLevel.RED),
            _make_doc("doc2", "/path/file2.pdf", pii_detected=True, pii_level=RiskLevel.RED),
        ]
        profile = create_group_profile(
            job_id="job123",
            group_id="group_001",
            group_path="/path",
            documents=docs,
        )

        assert len(profile.alerts) > 0
        assert any("PII" in alert for alert in profile.alerts)

    def test_inferred_purpose(self):
        """Inferred purpose should describe group."""
        docs = [
            _make_doc("doc1", "/path/file1.pdf", DocumentCategory.INVOICE),
            _make_doc("doc2", "/path/file2.pdf", DocumentCategory.INVOICE),
        ]
        profile = create_group_profile(
            job_id="job123",
            group_id="group_001",
            group_path="/path",
            documents=docs,
        )

        assert profile.inferred_purpose is not None
        assert len(profile.inferred_purpose) > 0


class TestGroupSimilarity:
    def test_category_overlap_identical(self):
        """Identical category distributions should have high overlap."""
        dist_a = {"Factura_Proveedor": 5, "Contrato": 3}
        dist_b = {"Factura_Proveedor": 5, "Contrato": 3}
        overlap = _compute_category_overlap(dist_a, dist_b)

        assert overlap == pytest.approx(1.0, rel=0.01)

    def test_category_overlap_disjoint(self):
        """Disjoint categories should have zero overlap."""
        dist_a = {"Factura_Proveedor": 5}
        dist_b = {"Contrato": 3}
        overlap = _compute_category_overlap(dist_a, dist_b)

        assert overlap == pytest.approx(0.0, rel=0.01)

    def test_category_overlap_partial(self):
        """Partial overlap should be between 0 and 1."""
        dist_a = {"Factura_Proveedor": 5, "Contrato": 3}
        dist_b = {"Factura_Proveedor": 5, "Licitacion": 2}
        overlap = _compute_category_overlap(dist_a, dist_b)

        assert 0.0 < overlap < 1.0

    def test_operational_similarity_identical(self):
        """Identical operational profiles should have high similarity."""
        docs_a = [
            _make_doc("d1", "/a/f1.pdf", pii_detected=False),
            _make_doc("d2", "/a/f2.pdf", pii_detected=False),
        ]
        docs_b = [
            _make_doc("d3", "/b/f3.pdf", pii_detected=False),
            _make_doc("d4", "/b/f4.pdf", pii_detected=False),
        ]
        features_a = extract_features(docs_a, "/a")
        features_b = extract_features(docs_b, "/b")
        sim = _compute_operational_similarity(features_a, features_b)

        assert sim == pytest.approx(1.0, rel=0.01)

    def test_compute_group_similarity_basic(self):
        """Compute basic group similarity."""
        docs_a = [
            _make_doc("d1", "/a/f1.pdf", DocumentCategory.INVOICE),
            _make_doc("d2", "/a/f2.pdf", DocumentCategory.INVOICE),
        ]
        docs_b = [
            _make_doc("d3", "/b/f3.pdf", DocumentCategory.INVOICE),
            _make_doc("d4", "/b/f4.pdf", DocumentCategory.INVOICE),
        ]

        profile_a = create_group_profile("job1", "grp_a", "/a", docs_a)
        profile_b = create_group_profile("job1", "grp_b", "/b", docs_b)

        sim = compute_group_similarity(profile_a, profile_b)

        assert 0.0 <= sim.composite_score <= 1.0
        assert 0.0 <= sim.semantic_similarity <= 1.0
        assert 0.0 <= sim.category_overlap <= 1.0
        assert 0.0 <= sim.operational_similarity <= 1.0

    def test_similarity_level_classification(self):
        """Similarity level should be classified correctly."""
        docs_a = [
            _make_doc("d1", "/a/f1.pdf", DocumentCategory.INVOICE),
        ]
        docs_b = [
            _make_doc("d2", "/b/f2.pdf", DocumentCategory.CONTRACT),
        ]

        profile_a = create_group_profile("job1", "grp_a", "/a", docs_a)
        profile_b = create_group_profile("job1", "grp_b", "/b", docs_b)

        sim = compute_group_similarity(profile_a, profile_b)

        # Should be either dissimilar, similar, or equivalent
        assert sim.similarity_level in ["dissimilar", "similar", "equivalent"]


class TestCompleteAnalysis:
    def test_analyze_all_groups(self):
        """Complete group analysis on a job."""
        docs = [
            _make_doc("d1", "/path/a/f1.pdf", DocumentCategory.INVOICE),
            _make_doc("d2", "/path/a/f2.pdf", DocumentCategory.INVOICE),
            _make_doc("d3", "/path/b/f3.pdf", DocumentCategory.CONTRACT),
            _make_doc("d4", "/path/b/f4.pdf", DocumentCategory.CONTRACT),
        ]

        result = analyze_all_groups("job123", docs, GroupMode.STRICT, top_k_similarities=5)

        assert result.job_id == "job123"
        assert result.group_count == 2
        assert len(result.groups) == 2
        assert len(result.group_similarities) <= 5

    def test_analyze_with_no_documents(self):
        """Analyze with empty document list."""
        result = analyze_all_groups("job123", [], GroupMode.STRICT)

        assert result.job_id == "job123"
        assert result.group_count == 0
        assert len(result.groups) == 0
        assert len(result.group_similarities) == 0

    def test_analyze_preserves_metadata(self):
        """Analysis preserves timestamp and mode."""
        docs = [
            _make_doc("d1", "/path/f1.pdf", DocumentCategory.INVOICE),
        ]

        result = analyze_all_groups("job123", docs, GroupMode.EXTENDED)

        assert result.analysis_timestamp is not None
        assert result.groups[0].group_mode == GroupMode.EXTENDED
