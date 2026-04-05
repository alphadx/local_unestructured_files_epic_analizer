"""
Tests for analytics service – temporal and relation graph outputs.
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
    build_corpus_exploration,
    build_job_statistics,
)


def _make_doc(
    doc_id: str,
    path: str,
    categoria: DocumentCategory = DocumentCategory.INVOICE,
    fecha_emision: str | None = None,
    periodo_fiscal: str | None = None,
    pii_detected: bool = False,
    pii_level: RiskLevel = RiskLevel.GREEN,
    relation_ot: str | None = None,
    relation_tender: str | None = None,
) -> DocumentMetadata:
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
        periodo_fiscal=periodo_fiscal,
        embedding=None,
    )


def test_job_statistics_temporal_distribution():
    docs = [
        _make_doc("a1", "/data/a1.pdf", fecha_emision="2026-01-10"),
        _make_doc("a2", "/data/a2.pdf", fecha_emision="2026-01-20"),
        _make_doc("a3", "/data/a3.pdf", fecha_emision="2026-02-15"),
        _make_doc("a4", "/data/a4.pdf"),
    ]
    report = DataHealthReport(
        job_id="job123",
        total_files=4,
        duplicates=0,
        duplicate_groups=[],
        pii_files=0,
        uncategorised_files=0,
        consistency_errors=[],
        clusters=[],
        reorganisation_plan=[],
    )

    stats = build_job_statistics("job123", report, docs)

    assert stats.temporal_distribution["2026-01"] == 3
    assert stats.temporal_distribution["2026-02"] == 1


def test_corpus_exploration_relation_graph_and_heatmap():
    docs = [
        _make_doc(
            "a1",
            "/data/a1.pdf",
            fecha_emision="2026-01-10",
            relation_ot="OT-123",
        ),
        _make_doc(
            "a2",
            "/data/a2.pdf",
            fecha_emision="2026-01-15",
            relation_tender="T-999",
        ),
        _make_doc(
            "a3",
            "/data/a3.pdf",
            fecha_emision="2026-02-05",
            relation_ot="OT-123",
            relation_tender="T-999",
        ),
    ]
    report = DataHealthReport(
        job_id="job123",
        total_files=3,
        duplicates=0,
        duplicate_groups=[],
        pii_files=0,
        uncategorised_files=0,
        consistency_errors=[],
        clusters=[],
        reorganisation_plan=[],
    )

    exploration = build_corpus_exploration("job123", report, docs)

    assert len(exploration.temporal_heatmap) >= 2
    assert exploration.relation_graph.node_count >= 4
    assert exploration.relation_graph.edge_count >= 3
    assert any(edge.relation_type in {"referencia_OT", "referencia_Licitacion"} for edge in exploration.relation_graph.edges)
