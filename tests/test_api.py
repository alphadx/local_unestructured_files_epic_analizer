"""
Integration tests for the FastAPI app – no external services required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.main import app

client = TestClient(app)


class TestHealth:
    def test_health_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestJobsEndpoint:
    def test_list_jobs_empty(self):
        response = client.get("/api/jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nonexistent_job(self):
        response = client.get("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    def test_start_scan_returns_202(self, tmp_path):
        # Create a temp file so the path exists
        (tmp_path / "test.txt").write_text("hello")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ("pending", "running", "completed")

    def test_start_scan_job_retrievable(self, tmp_path):
        (tmp_path / "doc.pdf").write_bytes(b"pdf content")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        get_response = client.get(f"/api/jobs/{job_id}")
        assert get_response.status_code == 200
        assert get_response.json()["job_id"] == job_id

    def test_start_scan_rejects_google_drive_without_folder_id(self):
        response = client.post(
            "/api/jobs",
            json={
                "path": "",
                "source_provider": "google_drive",
                "source_options": {},
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 422

    def test_start_scan_rejects_google_drive_with_invalid_service_account_json(self):
        response = client.post(
            "/api/jobs",
            json={
                "path": "my-folder-id",
                "source_provider": "google_drive",
                "source_options": {
                    "folder_id": "my-folder-id",
                    "service_account_json": "not-json",
                },
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 422

    def test_start_scan_rejects_sharepoint_without_site_or_drive(self):
        response = client.post(
            "/api/jobs",
            json={
                "path": "documents/folder",
                "source_provider": "sharepoint",
                "source_options": {},
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 422


class TestReportsEndpoint:
    def test_get_nonexistent_report(self):
        response = client.get("/api/reports/nonexistent-id")
        assert response.status_code == 404

    def test_get_documents_nonexistent_job(self):
        response = client.get("/api/reports/nonexistent-id/documents")
        assert response.status_code == 404

    def test_statistics_endpoint_returns_distribution_data(self, tmp_path):
        (tmp_path / "invoice.pdf").write_bytes(b"invoice content")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        stats_response = client.get(f"/api/reports/{job_id}/statistics")
        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert stats["job_id"] == job_id
        assert "extension_breakdown" in stats
        assert "mime_breakdown" in stats
        assert "size_bucket_distribution" in stats
        assert "directory_breakdown" in stats
        assert "semantic_coverage" in stats

    def test_exploration_endpoint_returns_pattern_summary(self, tmp_path):
        (tmp_path / "a.txt").write_text("uno", encoding="utf-8")
        (tmp_path / "b.txt").write_text("dos", encoding="utf-8")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        exploration_response = client.get(f"/api/reports/{job_id}/exploration")
        assert exploration_response.status_code == 200
        payload = exploration_response.json()
        assert payload["job_id"] == job_id
        assert "top_extensions" in payload
        assert "top_directories" in payload
        assert "dominant_categories" in payload
        assert "noisy_directories" in payload
        assert "concentration_index" in payload

    def test_chunks_endpoint_returns_extracted_chunks(self, tmp_path):
        (tmp_path / "report.md").write_text(
            "# Informe\n\nSección uno.\n\nSección dos.",
            encoding="utf-8",
        )
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        chunks_response = client.get(f"/api/reports/{job_id}/chunks")
        assert chunks_response.status_code == 200
        chunks = chunks_response.json()
        assert isinstance(chunks, list)
        assert len(chunks) >= 1
        assert chunks[0]["documento_id"]

    def test_export_json_endpoint_returns_inventory(self, tmp_path):
        (tmp_path / "exportable.txt").write_text("contenido", encoding="utf-8")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        export_response = client.get(f"/api/reports/{job_id}/export/json")
        assert export_response.status_code == 200
        payload = export_response.json()
        assert payload["job_id"] == job_id
        assert payload["total_documents"] >= 1
        assert isinstance(payload["documents"], list)

    def test_export_csv_endpoint_returns_inventory_file(self, tmp_path):
        (tmp_path / "exportable.md").write_text("# Titulo", encoding="utf-8")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        export_response = client.get(f"/api/reports/{job_id}/export/csv")
        assert export_response.status_code == 200
        assert export_response.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=\"inventory_" in export_response.headers[
            "content-disposition"
        ]
        body = export_response.text
        assert "documento_id,path,name,extension" in body
        assert "exportable.md" in body

    def test_compare_scans_detects_new_modified_deleted(self, tmp_path):
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("v1", encoding="utf-8")
        file_b.write_text("to-delete", encoding="utf-8")

        base_response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert base_response.status_code == 202
        base_job_id = base_response.json()["job_id"]

        file_a.write_text("v2", encoding="utf-8")
        file_b.unlink()
        (tmp_path / "c.txt").write_text("new-file", encoding="utf-8")

        target_response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert target_response.status_code == 202
        target_job_id = target_response.json()["job_id"]

        comparison_response = client.get(
            f"/api/reports/{base_job_id}/compare/{target_job_id}"
        )
        assert comparison_response.status_code == 200
        payload = comparison_response.json()

        assert payload["summary"]["new_files"] == 1
        assert payload["summary"]["modified_files"] == 1
        assert payload["summary"]["deleted_files"] == 1

        assert any(item["path"].endswith("/c.txt") for item in payload["new_files"])
        assert any(
            item["path"].endswith("/a.txt") for item in payload["modified_files"]
        )
        assert any(
            item["path"].endswith("/b.txt") for item in payload["deleted_files"]
        )

    def test_compare_scans_include_unchanged_and_limit(self, tmp_path):
        (tmp_path / "stable.txt").write_text("same", encoding="utf-8")
        (tmp_path / "changing.txt").write_text("before", encoding="utf-8")

        base_response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert base_response.status_code == 202
        base_job_id = base_response.json()["job_id"]

        (tmp_path / "changing.txt").write_text("after", encoding="utf-8")

        target_response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert target_response.status_code == 202
        target_job_id = target_response.json()["job_id"]

        comparison_response = client.get(
            f"/api/reports/{base_job_id}/compare/{target_job_id}"
            "?include_unchanged=true&limit=1"
        )
        assert comparison_response.status_code == 200
        payload = comparison_response.json()

        assert payload["summary"]["unchanged_files"] >= 1
        assert payload["summary"]["modified_files"] == 1
        assert len(payload["unchanged_files"]) == 1

    def test_compare_scans_nonexistent_job(self):
        response = client.get("/api/reports/does-not-exist/compare/other-job")
        assert response.status_code == 404

    def test_executive_summary_pdf_endpoint_returns_pdf(self, tmp_path):
        (tmp_path / "summary.txt").write_text("contenido base", encoding="utf-8")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        pdf_response = client.get(
            f"/api/reports/{job_id}/executive-summary/pdf?use_gemini=false"
        )
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"].startswith("application/pdf")
        assert "attachment; filename=\"executive_summary_" in pdf_response.headers[
            "content-disposition"
        ]
        assert pdf_response.content.startswith(b"%PDF-1.4")

    def test_executive_summary_pdf_nonexistent_job(self):
        response = client.get(
            "/api/reports/nonexistent-id/executive-summary/pdf?use_gemini=false"
        )
        assert response.status_code == 404


class TestRagEndpoint:
    def test_rag_query_endpoint(self, monkeypatch):
        from app.models.schemas import RagQueryResponse, RagSource
        from app.routers import rag as rag_router

        monkeypatch.setattr(
            rag_router,
            "query_rag",
            lambda request: RagQueryResponse(
                query=request.query,
                answer="Respuesta",
                context="Contexto",
                sources=[
                    RagSource(
                        source_id="chunk::1",
                        kind="chunk",
                        document_id="doc-1",
                        path="/data/doc.pdf",
                        title="Intro",
                        category="Informe",
                        cluster_sugerido="Informes",
                        chunk_index=0,
                        page_number=1,
                        snippet="Texto",
                        distance=0.2,
                        score=0.8,
                    )
                ],
            ),
        )

        response = client.post(
            "/api/rag/query",
            json={"query": "¿Qué dice el documento?", "job_id": "job-1", "top_k": 3},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["query"] == "¿Qué dice el documento?"
        assert payload["answer"] == "Respuesta"
        assert payload["sources"][0]["source_id"] == "chunk::1"


class TestSearchEndpoint:
    def test_search_endpoint_returns_matching_results(self, tmp_path):
        (tmp_path / "report.md").write_text(
            "# Reporte\n\nEste documento describe el análisis del sistema.",
            encoding="utf-8",
        )
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        search_response = client.post(
            "/api/search",
            json={
                "job_id": job_id,
                "query": "reporte análisis",
                "scope": "hybrid",
                "top_k": 5,
            },
        )
        assert search_response.status_code == 200
        payload = search_response.json()
        assert payload["job_id"] == job_id
        assert payload["total_results"] >= 1
        assert payload["results"][0]["path"].endswith("report.md")
        assert "categories" in payload
        assert "directories" in payload
