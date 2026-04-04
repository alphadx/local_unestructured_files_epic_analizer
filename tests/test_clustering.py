"""
Tests for clustering service – no API keys required.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import (
    DocumentCategory,
    DocumentMetadata,
    DocumentRelations,
    FileIndex,
    PiiInfo,
    SemanticAnalysis,
)
from app.services.clustering_service import (
    _label_based_clustering,
    build_clusters,
    detect_inconsistencies,
)


def _make_doc(
    doc_id: str,
    path: str,
    categoria: DocumentCategory,
    cluster_label: str,
    ot_ref: str | None = None,
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
        analisis_semantico=SemanticAnalysis(
            resumen="Resumen de prueba",
            cluster_sugerido=cluster_label,
            confianza_clasificacion=0.9,
        ),
        relaciones=DocumentRelations(id_ot_referencia=ot_ref),
    )


class TestLabelBasedClustering:
    def test_groups_by_label(self):
        docs = [
            _make_doc("a1", "/path/a1.pdf", DocumentCategory.INVOICE, "Facturas_2026"),
            _make_doc("a2", "/path/a2.pdf", DocumentCategory.INVOICE, "Facturas_2026"),
            _make_doc("b1", "/path/b1.pdf", DocumentCategory.TENDER, "Licitaciones"),
        ]
        clusters = _label_based_clustering(docs)
        labels = {c.label for c in clusters}
        assert "Facturas_2026" in labels
        assert "Licitaciones" in labels

    def test_counts_correct(self):
        docs = [
            _make_doc("a1", "/path/a1.pdf", DocumentCategory.INVOICE, "X"),
            _make_doc("a2", "/path/a2.pdf", DocumentCategory.INVOICE, "X"),
        ]
        clusters = _label_based_clustering(docs)
        assert len(clusters) == 1
        assert clusters[0].document_count == 2

    def test_empty_docs_returns_empty(self):
        assert _label_based_clustering([]) == []


class TestBuildClusters:
    def test_without_chroma_falls_back(self):
        docs = [
            _make_doc("x1", "/x1.pdf", DocumentCategory.UNKNOWN, "Sin_Cluster"),
        ]
        clusters = build_clusters(docs, chroma_data=None)
        assert len(clusters) == 1

    def test_empty_docs(self):
        assert build_clusters([]) == []


class TestDetectInconsistencies:
    def test_invoice_without_ot_flagged(self):
        docs = [
            _make_doc("inv1", "/inv1.pdf", DocumentCategory.INVOICE, "Facturas", ot_ref=None),
        ]
        clusters = _label_based_clustering(docs)
        result = detect_inconsistencies(clusters, docs)
        assert any("Factura sin OT" in e for cl in result for e in cl.inconsistencies)

    def test_invoice_with_ot_ok(self):
        docs = [
            _make_doc("inv2", "/inv2.pdf", DocumentCategory.INVOICE, "Facturas", ot_ref="OT-001"),
        ]
        clusters = _label_based_clustering(docs)
        result = detect_inconsistencies(clusters, docs)
        assert all(len(cl.inconsistencies) == 0 for cl in result)

    def test_non_invoice_not_flagged(self):
        docs = [
            _make_doc("rep1", "/rep1.pdf", DocumentCategory.REPORT, "Informes", ot_ref=None),
        ]
        clusters = _label_based_clustering(docs)
        result = detect_inconsistencies(clusters, docs)
        assert all(len(cl.inconsistencies) == 0 for cl in result)
