"""
Integration tests for the FastAPI app – no external services required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import time

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
            "group_mode": "strict",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ("pending", "running", "completed")

    def test_start_scan_e2e_pipeline_applies_filters(self, tmp_path):
        (tmp_path / "allowed.txt").write_text("hello")
        (tmp_path / "denied.py").write_text("print('nope')")
        (tmp_path / "included.md").write_text("markdown content")

        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "strict",
                "ingestion_mode": "blacklist",
                "denied_extensions": ".py",
            },
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        deadline = time.time() + 15
        final_status = None

        while time.time() < deadline:
            status_resp = client.get(f"/api/jobs/{job_id}")
            assert status_resp.status_code == 200
            job_data = status_resp.json()
            if job_data["status"] in ("completed", "failed"):
                final_status = job_data["status"]
                break
            time.sleep(0.2)

        assert final_status == "completed", f"Job {job_id} did not complete in time"
        assert job_data["total_files"] == 2

        stats_resp = client.get(f"/api/reports/{job_id}/statistics")
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["job_id"] == job_id
        assert ".py" not in stats_data["extension_breakdown"]
        assert stats_data["total_files"] == 2

    def test_start_scan_e2e_whitelist_rejects_unapproved_files(self, tmp_path):
        (tmp_path / "allowed.txt").write_text("hello")
        (tmp_path / "rejected.py").write_text("print('nope')")
        (tmp_path / "rejected.bin").write_text("binary")

        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "strict",
                "ingestion_mode": "whitelist",
                "allowed_extensions": ".txt",
            },
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        deadline = time.time() + 15
        final_status = None

        while time.time() < deadline:
            status_resp = client.get(f"/api/jobs/{job_id}")
            assert status_resp.status_code == 200
            job_data = status_resp.json()
            if job_data["status"] in ("completed", "failed"):
                final_status = job_data["status"]
                break
            time.sleep(0.2)

        assert final_status == "completed", f"Job {job_id} did not complete in time"
        assert job_data["total_files"] == 1

        stats_resp = client.get(f"/api/reports/{job_id}/statistics")
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["job_id"] == job_id
        assert ".txt" in stats_data["extension_breakdown"]
        assert ".py" not in stats_data["extension_breakdown"]
        assert ".bin" not in stats_data["extension_breakdown"]
        assert stats_data["total_files"] == 1

    def test_start_scan_passes_filter_overrides_to_pipeline(self, tmp_path, monkeypatch):
        captured: dict[str, object] = {}

        async def fake_run_pipeline(job_id, request):
            captured["job_id"] = job_id
            captured["request"] = request

        monkeypatch.setattr("app.services.job_manager.run_pipeline", fake_run_pipeline)

        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "strict",
                "ingestion_mode": "whitelist",
                "allowed_extensions": ".txt,.pdf",
                "denied_extensions": ".py",
            },
        )

        assert response.status_code == 202
        assert "job_id" in captured
        request = captured["request"]
        assert request.ingestion_mode == "whitelist"
        assert request.allowed_extensions == ".txt,.pdf"
        assert request.denied_extensions == ".py"

    def test_start_scan_job_retrievable(self, tmp_path):
        (tmp_path / "doc.pdf").write_bytes(b"pdf content")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
                "group_mode": "strict",
            },
        )
        assert response.status_code == 422

    def test_start_scan_defaults_group_mode_to_strict(self, tmp_path):
        """Omitting group_mode is allowed — it defaults to 'strict'."""
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

    def test_start_scan_rejects_invalid_group_mode(self, tmp_path):
        (tmp_path / "doc.pdf").write_bytes(b"pdf content")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "invalid_mode",
            },
        )
        assert response.status_code == 422
        assert any(
            err["loc"][-1] == "group_mode" and "group_mode must be either 'strict' or 'extended'" in err["msg"]
            for err in response.json()["detail"]
        )


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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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
            "group_mode": "strict",
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

    def test_groups_endpoint_returns_group_analysis(self, tmp_path):
        (tmp_path / "a.txt").write_text("hola mundo", encoding="utf-8")
        (tmp_path / "b.txt").write_text("otro archivo", encoding="utf-8")
        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
            "group_mode": "strict",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        groups_response = client.get(f"/api/reports/{job_id}/groups")
        assert groups_response.status_code == 200
        payload = groups_response.json()
        assert payload["job_id"] == job_id
        assert payload["group_count"] >= 1
        assert isinstance(payload["groups"], list)

    def test_group_similarity_endpoint_returns_similar_groups(self, tmp_path):
        (tmp_path / "a/file1.txt").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "a/file1.txt").write_text("uno", encoding="utf-8")
        (tmp_path / "b/file2.txt").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "b/file2.txt").write_text("dos", encoding="utf-8")

        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "strict",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        groups_response = client.get(f"/api/reports/{job_id}/groups")
        assert groups_response.status_code == 200
        groups_payload = groups_response.json()
        assert groups_payload["groups"]
        group_id = groups_payload["groups"][0]["group_id"]

        similarity_response = client.get(
            f"/api/reports/{job_id}/groups/{group_id}/similarity"
        )
        assert similarity_response.status_code == 200
        sim_payload = similarity_response.json()
        assert sim_payload["group_id"] == group_id
        assert isinstance(sim_payload["similar_groups"], list)

    def test_scan_request_defaults_to_strict_group_mode(self, tmp_path):
        (tmp_path / "a/b/file1.txt").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "a/b/file1.txt").write_text("contenido", encoding="utf-8")

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

        groups_response = client.get(f"/api/reports/{job_id}/groups")
        assert groups_response.status_code == 200
        payload = groups_response.json()
        assert payload["job_id"] == job_id
        group_paths = [g["group_path"] for g in payload["groups"]]
        assert str(tmp_path / "a/b") in group_paths
        assert str(tmp_path) not in group_paths
        assert all(g["group_mode"] == "strict" for g in payload["groups"])

    def test_groups_response_preserves_group_mode_in_output(self, tmp_path):
        (tmp_path / "a/b/file1.txt").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "a/b/file1.txt").write_text("contenido", encoding="utf-8")

        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "extended",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        groups_response = client.get(f"/api/reports/{job_id}/groups")
        assert groups_response.status_code == 200
        payload = groups_response.json()
        assert payload["job_id"] == job_id
        assert payload["groups"]
        assert all(g["group_mode"] == "extended" for g in payload["groups"])

    def test_scan_request_accepts_extended_group_mode(self, tmp_path):
        (tmp_path / "a/b/file1.txt").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "a/b/file1.txt").write_text("contenido", encoding="utf-8")

        response = client.post(
            "/api/jobs",
            json={
                "path": str(tmp_path),
                "enable_pii_detection": False,
                "enable_embeddings": False,
                "enable_clustering": False,
                "group_mode": "extended",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        groups_response = client.get(f"/api/reports/{job_id}/groups")
        assert groups_response.status_code == 200
        payload = groups_response.json()
        assert payload["job_id"] == job_id
        assert payload["group_count"] >= 2
        group_paths = [g["group_path"] for g in payload["groups"]]
        assert str(tmp_path) in group_paths
        assert str(tmp_path / "a") in group_paths


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
            "group_mode": "strict",
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
