"""
Additional tests for Phase 2 – Analytics service edge cases.

Covers concentration_index, pii_share, uncategorised_share,
empty corpus, and boundary behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import (
    DataHealthReport,
    DocumentCategory,
    DocumentEntities,
    DocumentMetadata,
    DocumentRelations,
    FileIndex,
    PiiInfo,
    RiskLevel,
    SemanticAnalysis,
)
from app.services.analytics_service import (
    bucket_file_size,
    build_corpus_exploration,
    build_job_statistics,
    normalize_extension,
    normalize_mime_type,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    doc_id: str,
    path: str,
    categoria: DocumentCategory = DocumentCategory.INVOICE,
    fecha_emision: str | None = None,
    pii_detected: bool = False,
    pii_level: RiskLevel = RiskLevel.GREEN,
    relation_ot: str | None = None,
    relation_tender: str | None = None,
    size_bytes: int = 100,
    extension: str = ".pdf",
    mime_type: str | None = "application/pdf",
    modified_at: str = "2026-01-01T00:00:00",
) -> DocumentMetadata:
    fi = FileIndex(
        path=path,
        name=Path(path).name,
        extension=extension,
        size_bytes=size_bytes,
        created_at="2026-01-01T00:00:00",
        modified_at=modified_at,
        sha256=doc_id,
        mime_type=mime_type,
    )
    return DocumentMetadata(
        documento_id=doc_id,
        file_index=fi,
        categoria=categoria,
        entidades=DocumentEntities(),
        relaciones=DocumentRelations(
            id_ot_referencia=relation_ot,
            id_licitacion_vinculada=relation_tender,
        ),
        analisis_semantico=SemanticAnalysis(
            resumen="Resumen",
            cluster_sugerido="Test",
            confianza_clasificacion=0.9,
            palabras_clave=["prueba"],
        ),
        pii_info=PiiInfo(detected=pii_detected, risk_level=pii_level),
        fecha_emision=fecha_emision,
        embedding=None,
    )


def _empty_report(job_id: str = "job-x") -> DataHealthReport:
    return DataHealthReport(
        job_id=job_id,
        total_files=0,
        duplicates=0,
        duplicate_groups=[],
        pii_files=0,
        uncategorised_files=0,
        consistency_errors=[],
        clusters=[],
        reorganisation_plan=[],
    )


def _report(job_id: str, total: int, duplicates: int = 0) -> DataHealthReport:
    return DataHealthReport(
        job_id=job_id,
        total_files=total,
        duplicates=duplicates,
        duplicate_groups=[],
        pii_files=0,
        uncategorised_files=0,
        consistency_errors=[],
        clusters=[],
        reorganisation_plan=[],
    )


# ---------------------------------------------------------------------------
# normalize_extension
# ---------------------------------------------------------------------------


class TestNormalizeExtension:
    def test_none_returns_no_extension(self):
        assert normalize_extension(None) == "(sin extensión)"

    def test_empty_string_returns_no_extension(self):
        assert normalize_extension("") == "(sin extensión)"

    def test_dot_only_returns_no_extension(self):
        assert normalize_extension(".") == "(sin extensión)"

    def test_extension_without_leading_dot_gets_dot(self):
        assert normalize_extension("pdf") == ".pdf"

    def test_extension_with_leading_dot_returned_as_is(self):
        assert normalize_extension(".pdf") == ".pdf"

    def test_uppercase_normalized_to_lowercase(self):
        assert normalize_extension(".PDF") == ".pdf"

    def test_whitespace_stripped(self):
        assert normalize_extension("  .docx  ") == ".docx"


# ---------------------------------------------------------------------------
# normalize_mime_type
# ---------------------------------------------------------------------------


class TestNormalizeMimeType:
    def test_none_returns_unknown(self):
        assert normalize_mime_type(None) == "(desconocido)"

    def test_empty_string_returns_unknown(self):
        assert normalize_mime_type("") == "(desconocido)"

    def test_whitespace_only_returns_unknown(self):
        assert normalize_mime_type("   ") == "(desconocido)"

    def test_value_normalized_to_lowercase(self):
        assert normalize_mime_type("Application/PDF") == "application/pdf"


# ---------------------------------------------------------------------------
# bucket_file_size
# ---------------------------------------------------------------------------


class TestBucketFileSize:
    def test_small_file_under_1mb(self):
        assert bucket_file_size(500_000) == "<1MB"

    def test_medium_file_1_to_10mb(self):
        assert bucket_file_size(5_000_000) == "1-10MB"

    def test_large_file_10_to_100mb(self):
        assert bucket_file_size(50_000_000) == "10-100MB"

    def test_very_large_file_over_100mb(self):
        assert bucket_file_size(200_000_000) == ">100MB"

    def test_boundary_exactly_1mb_goes_to_next_bucket(self):
        assert bucket_file_size(1_048_576) == "1-10MB"


# ---------------------------------------------------------------------------
# build_corpus_exploration — edge cases
# ---------------------------------------------------------------------------


class TestBuildCorpusExploration:
    def test_empty_corpus_returns_zero_shares(self):
        exploration = build_corpus_exploration("job-x", _empty_report(), [])
        assert exploration.uncategorised_share == 0.0
        assert exploration.pii_share == 0.0
        assert exploration.concentration_index == 0.0
        assert exploration.top_extensions == []
        assert exploration.top_directories == []

    def test_pii_share_all_pii(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", pii_detected=True, pii_level=RiskLevel.RED),
            _make_doc("d2", "/data/b.pdf", pii_detected=True, pii_level=RiskLevel.RED),
        ]
        exploration = build_corpus_exploration("j1", _report("j1", 2), docs)
        assert exploration.pii_share == 1.0

    def test_pii_share_no_pii(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", pii_detected=False),
            _make_doc("d2", "/data/b.pdf", pii_detected=False),
        ]
        exploration = build_corpus_exploration("j1", _report("j1", 2), docs)
        assert exploration.pii_share == 0.0

    def test_uncategorised_share(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", categoria=DocumentCategory.UNKNOWN),
            _make_doc("d2", "/data/b.pdf", categoria=DocumentCategory.INVOICE),
        ]
        exploration = build_corpus_exploration("j1", _report("j1", 2), docs)
        assert exploration.uncategorised_share == 0.5

    def test_concentration_index_all_same_extension(self):
        docs = [_make_doc(f"d{i}", f"/data/file{i}.pdf") for i in range(4)]
        exploration = build_corpus_exploration("j1", _report("j1", 4), docs)
        # All files have the same extension → concentration is 1.0
        assert exploration.concentration_index == 1.0

    def test_concentration_index_spread_across_extensions(self):
        # Files in different directories AND different extensions → low concentration
        docs = [
            _make_doc("d1", "/dir1/a.pdf", extension=".pdf"),
            _make_doc("d2", "/dir2/b.docx", extension=".docx"),
            _make_doc("d3", "/dir3/c.xlsx", extension=".xlsx"),
            _make_doc("d4", "/dir4/d.txt", extension=".txt"),
        ]
        exploration = build_corpus_exploration("j1", _report("j1", 4), docs)
        # Each extension AND each directory appears once → max count = 1 → concentration = 1/4
        assert exploration.concentration_index == 0.25

    def test_temporal_heatmap_sorted_chronologically(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", fecha_emision="2026-03-01"),
            _make_doc("d2", "/data/b.pdf", fecha_emision="2026-01-15"),
            _make_doc("d3", "/data/c.pdf", fecha_emision="2026-02-20"),
        ]
        exploration = build_corpus_exploration("j1", _report("j1", 3), docs)
        labels = [b.label for b in exploration.temporal_heatmap]
        assert labels == sorted(labels)

    def test_fallback_to_modified_at_for_unknown_emission_date(self):
        doc = _make_doc(
            "d1",
            "/data/a.pdf",
            fecha_emision=None,
            modified_at="2026-06-15T00:00:00",
        )
        exploration = build_corpus_exploration("j1", _report("j1", 1), [doc])
        labels = [b.label for b in exploration.temporal_heatmap]
        assert "2026-06" in labels

    def test_relation_graph_empty_docs(self):
        exploration = build_corpus_exploration("j1", _empty_report("j1"), [])
        assert exploration.relation_graph is None or (
            hasattr(exploration, "relation_graph")
            and (exploration.relation_graph is None or exploration.relation_graph.node_count == 0)
        )

    def test_noisy_directories_includes_top_directories(self):
        docs = [_make_doc(f"d{i}", "/hot/dir/file.pdf") for i in range(3)]
        docs += [_make_doc("dx", "/cold/dir/file.pdf")]
        exploration = build_corpus_exploration("j1", _report("j1", 4), docs)
        hotspot_paths = [h.path for h in exploration.noisy_directories]
        assert "/hot/dir" in hotspot_paths


# ---------------------------------------------------------------------------
# build_job_statistics — edge cases
# ---------------------------------------------------------------------------


class TestBuildJobStatistics:
    def test_semantic_coverage_all_classified(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", categoria=DocumentCategory.INVOICE),
            _make_doc("d2", "/data/b.pdf", categoria=DocumentCategory.CONTRACT),
        ]
        stats = build_job_statistics("j1", _report("j1", 2), docs)
        assert stats.semantic_coverage == 1.0

    def test_semantic_coverage_none_classified(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", categoria=DocumentCategory.UNKNOWN),
        ]
        stats = build_job_statistics("j1", _report("j1", 1), docs)
        assert stats.semantic_coverage == 0.0

    def test_semantic_coverage_partial(self):
        docs = [
            _make_doc("d1", "/data/a.pdf", categoria=DocumentCategory.INVOICE),
            _make_doc("d2", "/data/b.pdf", categoria=DocumentCategory.UNKNOWN),
        ]
        stats = build_job_statistics("j1", _report("j1", 2), docs)
        assert stats.semantic_coverage == 0.5

    def test_empty_documents_no_crash(self):
        stats = build_job_statistics("j1", _empty_report("j1"), [])
        assert stats.total_files == 0
        assert stats.semantic_coverage == 0.0
        assert stats.extension_breakdown == {}

    def test_keyword_distribution_normalizes_case(self):
        docs = [
            _make_doc("d1", "/a.pdf"),
        ]
        docs[0].analisis_semantico.palabras_clave = ["Factura", "FACTURA", "factura"]
        stats = build_job_statistics("j1", _report("j1", 1), docs)
        assert stats.keyword_distribution.get("factura") == 3

    def test_keyword_distribution_ignores_empty_keywords(self):
        docs = [_make_doc("d1", "/a.pdf")]
        docs[0].analisis_semantico.palabras_clave = ["valid", "", "  "]
        stats = build_job_statistics("j1", _report("j1", 1), docs)
        assert "" not in stats.keyword_distribution
        assert "   " not in stats.keyword_distribution
        assert stats.keyword_distribution.get("valid") == 1

    def test_pii_risk_distribution_counts_all_levels(self):
        docs = [
            _make_doc("d1", "/a.pdf", pii_level=RiskLevel.GREEN),
            _make_doc("d2", "/b.pdf", pii_level=RiskLevel.YELLOW),
            _make_doc("d3", "/c.pdf", pii_level=RiskLevel.RED),
        ]
        stats = build_job_statistics("j1", _report("j1", 3), docs)
        assert stats.pii_risk_distribution[RiskLevel.GREEN.value] == 1
        assert stats.pii_risk_distribution[RiskLevel.YELLOW.value] == 1
        assert stats.pii_risk_distribution[RiskLevel.RED.value] == 1

    def test_size_bucket_distribution(self):
        docs = [
            _make_doc("d1", "/a.pdf", size_bytes=500_000),    # <1MB
            _make_doc("d2", "/b.pdf", size_bytes=5_000_000),  # 1-10MB
        ]
        stats = build_job_statistics("j1", _report("j1", 2), docs)
        assert stats.size_bucket_distribution["<1MB"] == 1
        assert stats.size_bucket_distribution["1-10MB"] == 1
