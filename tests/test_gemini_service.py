"""
Tests for Gemini document classification and validation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import settings
from app.models.schemas import DocumentCategory, FileIndex, RiskLevel
from app.services import gemini_service


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate_content(self, model: str, contents: str):  # noqa: ANN001
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


def _file_index() -> FileIndex:
    return FileIndex(
        path="/tmp/example.pdf",
        name="example.pdf",
        extension=".pdf",
        size_bytes=123,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="abc123",
        mime_type="application/pdf",
    )


def test_classify_document_uses_extracted_text(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        gemini_service,
        "_get_client",
        lambda: _FakeClient(
            """
            {
              "categoria": "Informe",
              "entidades": {"emisor": "ACME", "receptor": "Cliente", "monto_total": 1234, "moneda": "clp"},
              "relaciones": {"id_licitacion_vinculada": "LIC-1", "id_ot_referencia": "OT-2"},
              "analisis_semantico": {
                "resumen": "Resumen de prueba",
                "cluster_sugerido": "Informes",
                "confianza_clasificacion": 0.87,
                "palabras_clave": ["analisis", "reporte", "analisis"]
              },
              "pii_info": {"detected": true, "risk_level": "amarillo", "details": ["correo"]},
              "fecha_emision": "2026-04-04",
              "periodo_fiscal": "2026-04"
            }
            """
        ),
    )

    doc = gemini_service.classify_document(_file_index(), extracted_text="Texto extraído relevante")

    assert doc.categoria == DocumentCategory.REPORT
    assert doc.entidades.moneda == "CLP"
    assert doc.analisis_semantico.confianza_clasificacion == pytest.approx(0.87)
    assert doc.analisis_semantico.palabras_clave == ["analisis", "reporte"]
    assert doc.pii_info.risk_level == RiskLevel.YELLOW
    assert doc.fecha_emision == "2026-04-04"
    assert doc.periodo_fiscal == "2026-04"


def test_classify_document_normalizes_invalid_payload(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        gemini_service,
        "_get_client",
        lambda: _FakeClient(
            """
            {
              "categoria": "NoExiste",
              "entidades": {"emisor": null, "receptor": null, "monto_total": 10, "moneda": "usd"},
              "relaciones": {},
              "analisis_semantico": {
                "resumen": "Resumen",
                "cluster_sugerido": "Otro",
                "confianza_clasificacion": 5,
                "palabras_clave": ["uno", "", "dos", "uno", null, "tres", "cuatro", "cinco", "seis"]
              },
              "pii_info": {"detected": false, "risk_level": "inexistente", "details": ["  "]},
              "fecha_emision": "04-04-2026",
              "periodo_fiscal": "2026/04"
            }
            """
        ),
    )

    doc = gemini_service.classify_document(_file_index(), extracted_text="Texto")

    assert doc.categoria == DocumentCategory.UNKNOWN
    assert doc.entidades.moneda == "USD"
    assert doc.analisis_semantico.confianza_clasificacion == 1.0
    assert doc.analisis_semantico.palabras_clave == ["uno", "dos", "tres", "cuatro", "cinco"]
    assert doc.pii_info.risk_level == RiskLevel.GREEN
    assert doc.pii_info.details == []
    assert doc.fecha_emision is None
    assert doc.periodo_fiscal is None
