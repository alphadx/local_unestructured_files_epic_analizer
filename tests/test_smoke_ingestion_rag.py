"""Smoke tests for ingestion regressions (.xlsx/.pdf extraction and RAG resiliency)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.main import app
from app.services import rag_service

client = TestClient(app)


def test_smoke_whitelist_xlsx_produces_documents(tmp_path, monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    from app.config import settings

    monkeypatch.setattr(settings, "local_scan_root", "")

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Planilla"
    sheet["A1"] = "persona"
    sheet["B1"] = "correo"
    sheet["A2"] = "Ana"
    sheet["B2"] = "ana@example.com"

    xlsx_file = tmp_path / "contactos.xlsx"
    workbook.save(xlsx_file)
    workbook.close()

    response = client.post(
        "/api/jobs",
        json={
            "path": str(tmp_path),
            "enable_pii_detection": False,
            "enable_embeddings": False,
            "enable_clustering": False,
            "group_mode": "strict",
            "ingestion_mode": "whitelist",
            "allowed_extensions": ".xlsx",
        },
    )
    assert response.status_code == 202

    job_id = response.json()["job_id"]
    deadline = time.time() + 20
    final_status = None
    while time.time() < deadline:
        status_resp = client.get(f"/api/jobs/{job_id}")
        assert status_resp.status_code == 200
        payload = status_resp.json()
        if payload["status"] in ("completed", "failed"):
            final_status = payload["status"]
            break
        time.sleep(0.2)

    assert final_status == "completed"

    docs_resp = client.get(f"/api/reports/{job_id}/documents")
    assert docs_resp.status_code == 200
    documents = docs_resp.json()
    assert len(documents) >= 1
    assert documents[0]["file_index"]["extension"] == ".xlsx"


def test_smoke_rag_query_no_vectors_no_500(monkeypatch):
    monkeypatch.setattr(rag_service.embeddings_service, "embed_text", lambda _text: None)
    monkeypatch.setattr(rag_service.vector_store, "query_similar", lambda *args, **kwargs: [])

    async def _async_empty_docs(_job_id: str):
        return []

    async def _async_empty_chunks(_job_id: str):
        return []

    monkeypatch.setattr(rag_service.job_manager, "get_documents", _async_empty_docs)
    monkeypatch.setattr(rag_service.job_manager, "get_chunks", _async_empty_chunks)

    response = client.post(
        "/api/rag/query",
        json={
            "query": "que entidades existen",
            "job_id": "job-inexistente",
            "top_k": 3,
            "include_answer": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "que entidades existen"
    assert payload["sources"] == []
    assert payload["context"] == ""
