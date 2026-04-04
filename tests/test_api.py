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


class TestReportsEndpoint:
    def test_get_nonexistent_report(self):
        response = client.get("/api/reports/nonexistent-id")
        assert response.status_code == 404

    def test_get_documents_nonexistent_job(self):
        response = client.get("/api/reports/nonexistent-id/documents")
        assert response.status_code == 404
