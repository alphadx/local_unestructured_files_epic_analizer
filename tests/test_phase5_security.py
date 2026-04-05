"""
Tests for Phase 5 – Security and compliance.

Covers:
- API key authentication middleware
- Audit log endpoint (/api/audit)
- Job retention / pruning (prune_old_jobs)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.main import app
from app.services import audit_log as _audit_log_module
from app.services import job_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(api_key: str = "") -> TestClient:
    """Return a TestClient configured with a specific API key in settings."""
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------


class TestApiKeyMiddleware:
    def test_no_api_key_configured_allows_all_requests(self):
        """When API_KEY env var is empty, all requests pass without a key."""
        with patch("app.main.settings") as mock_settings:
            mock_settings.api_key = ""
            mock_settings.cors_origins = ["*"]
            # Rebuild a fresh client against the patched settings
            client = TestClient(app)
            response = client.get("/health")
        assert response.status_code == 200

    def test_api_key_required_when_configured(self):
        """When API_KEY is set, requests without it should be rejected with 401."""
        with patch("app.main.settings") as mock_settings:
            mock_settings.api_key = "supersecret"
            client = TestClient(app)
            response = client.get("/api/jobs")
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]

    def test_wrong_api_key_is_rejected(self):
        """A wrong key value should still return 401."""
        with patch("app.main.settings") as mock_settings:
            mock_settings.api_key = "supersecret"
            client = TestClient(app)
            response = client.get("/api/jobs", headers={"X-Api-Key": "wrong"})
        assert response.status_code == 401

    def test_correct_api_key_is_accepted(self):
        """The correct key value lets the request through."""
        with patch("app.main.settings") as mock_settings:
            mock_settings.api_key = "supersecret"
            client = TestClient(app)
            response = client.get("/api/jobs", headers={"X-Api-Key": "supersecret"})
        # /api/jobs returns 200 (empty list) when authenticated
        assert response.status_code == 200

    def test_health_endpoint_exempt_from_api_key(self):
        """The /health endpoint should never require an API key."""
        with patch("app.main.settings") as mock_settings:
            mock_settings.api_key = "supersecret"
            client = TestClient(app)
            response = client.get("/health")
        assert response.status_code == 200

    def test_docs_endpoint_exempt_from_api_key(self):
        """The /docs endpoint should never require an API key."""
        with patch("app.main.settings") as mock_settings:
            mock_settings.api_key = "supersecret"
            client = TestClient(app)
            response = client.get("/docs")
        # 200 (HTML docs) or redirect, but not 401
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Audit Log Endpoint
# ---------------------------------------------------------------------------


client = TestClient(app)


class TestAuditEndpoint:
    def setup_method(self):
        """Clear the audit log before each test."""
        _audit_log_module._audit_log.clear()

    def test_audit_endpoint_returns_empty_when_no_entries(self):
        response = client.get("/api/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["entries"] == []

    def test_audit_endpoint_records_job_creation(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
        # Create a job to trigger audit record
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

        audit_response = client.get("/api/audit")
        assert audit_response.status_code == 200
        data = audit_response.json()
        assert data["total"] >= 1
        operations = [e["operation"] for e in data["entries"]]
        assert "job.created" in operations

    def test_audit_endpoint_filter_by_operation(self):
        _audit_log_module.record("job.completed", resource_id="j1", resource_type="job")
        _audit_log_module.record("job.failed", resource_id="j2", resource_type="job", outcome="failure")

        response = client.get("/api/audit?operation=job.completed")
        assert response.status_code == 200
        data = response.json()
        assert all(e["operation"] == "job.completed" for e in data["entries"])

    def test_audit_endpoint_filter_by_resource_type(self):
        _audit_log_module.record("search.query", resource_id="s1", resource_type="search")
        _audit_log_module.record("job.created", resource_id="j1", resource_type="job")

        response = client.get("/api/audit?resource_type=search")
        assert response.status_code == 200
        data = response.json()
        assert all(e["resource_type"] == "search" for e in data["entries"])

    def test_audit_endpoint_pagination(self):
        for i in range(5):
            _audit_log_module.record("op.test", resource_id=str(i), resource_type="test")

        response_page1 = client.get("/api/audit?limit=3&offset=0")
        assert response_page1.status_code == 200
        page1 = response_page1.json()
        assert len(page1["entries"]) == 3
        assert page1["total"] == 5

        response_page2 = client.get("/api/audit?limit=3&offset=3")
        page2 = response_page2.json()
        assert len(page2["entries"]) == 2

    def test_audit_entries_newest_first(self):
        _audit_log_module.record("op.first", resource_id="a", resource_type="test")
        _audit_log_module.record("op.second", resource_id="b", resource_type="test")
        _audit_log_module.record("op.third", resource_id="c", resource_type="test")

        response = client.get("/api/audit")
        data = response.json()
        ops = [e["operation"] for e in data["entries"]]
        assert ops[0] == "op.third"
        assert ops[-1] == "op.first"

    def test_audit_entry_has_required_fields(self):
        _audit_log_module.record("job.created", resource_id="j1", resource_type="job")

        response = client.get("/api/audit")
        entry = response.json()["entries"][0]
        for field in ("entry_id", "timestamp", "operation", "actor", "resource_id", "resource_type", "outcome", "details"):
            assert field in entry, f"Missing field: {field}"

    def test_audit_limit_validation(self):
        response = client.get("/api/audit?limit=0")
        assert response.status_code == 422

    def test_audit_offset_validation(self):
        response = client.get("/api/audit?offset=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Job Retention / prune_old_jobs
# ---------------------------------------------------------------------------


class TestJobRetention:
    def setup_method(self):
        """Clear job stores before each test."""
        job_manager._jobs.clear()
        job_manager._reports.clear()
        job_manager._documents.clear()
        job_manager._chunks.clear()
        job_manager._job_logs.clear()
        job_manager._group_analysis.clear()
        job_manager._job_creation_times.clear()

    def _create_completed_job(self, age_seconds: float = 0) -> str:
        from app.models.schemas import JobStatus
        job_id = job_manager.create_job()
        job_manager._jobs[job_id].status = JobStatus.COMPLETED
        # Backdate creation time
        job_manager._job_creation_times[job_id] = time.time() - age_seconds
        return job_id

    def test_no_retention_limits_prunes_nothing(self):
        with patch("app.services.job_manager.settings") as mock:
            mock.max_jobs_retained = 0
            mock.job_max_age_hours = 0
            j1 = self._create_completed_job()
            pruned = job_manager.prune_old_jobs()
        assert pruned == 0
        assert j1 in job_manager._jobs

    def test_age_based_pruning_removes_old_jobs(self):
        with patch("app.services.job_manager.settings") as mock:
            mock.max_jobs_retained = 0
            mock.job_max_age_hours = 1  # 1 hour
            old_job = self._create_completed_job(age_seconds=7201)  # ~2h old
            new_job = self._create_completed_job(age_seconds=10)    # 10s old
            pruned = job_manager.prune_old_jobs()
        assert pruned == 1
        assert old_job not in job_manager._jobs
        assert new_job in job_manager._jobs

    def test_count_based_pruning_keeps_newest(self):
        with patch("app.services.job_manager.settings") as mock:
            mock.max_jobs_retained = 2
            mock.job_max_age_hours = 0
            old1 = self._create_completed_job(age_seconds=300)
            old2 = self._create_completed_job(age_seconds=200)
            newest = self._create_completed_job(age_seconds=10)
            pruned = job_manager.prune_old_jobs()
        assert pruned == 1
        assert old1 not in job_manager._jobs
        assert old2 in job_manager._jobs
        assert newest in job_manager._jobs

    def test_pruning_does_not_remove_running_jobs(self):
        from app.models.schemas import JobStatus
        with patch("app.services.job_manager.settings") as mock:
            mock.max_jobs_retained = 1
            mock.job_max_age_hours = 0
            running = job_manager.create_job()
            job_manager._jobs[running].status = JobStatus.RUNNING
            completed = self._create_completed_job(age_seconds=100)
            extra = self._create_completed_job(age_seconds=50)
            pruned = job_manager.prune_old_jobs()
        # The running job should never be pruned
        assert running in job_manager._jobs
        assert pruned == 1

    def test_pruning_clears_all_related_stores(self):
        from app.models.schemas import JobStatus, DataHealthReport
        with patch("app.services.job_manager.settings") as mock:
            mock.max_jobs_retained = 0
            mock.job_max_age_hours = 1
            old = self._create_completed_job(age_seconds=7201)
            # Populate associated stores
            job_manager._documents[old] = []
            job_manager._chunks[old] = []
            job_manager._job_logs[old] = ["log line"]
            job_manager.prune_old_jobs()
        assert old not in job_manager._documents
        assert old not in job_manager._chunks
        assert old not in job_manager._job_logs

    def test_pruning_writes_audit_entry(self):
        _audit_log_module._audit_log.clear()
        with patch("app.services.job_manager.settings") as mock:
            mock.max_jobs_retained = 0
            mock.job_max_age_hours = 1
            self._create_completed_job(age_seconds=7201)
            job_manager.prune_old_jobs()
        ops = [e.operation for e in _audit_log_module._audit_log]
        assert "job.pruned" in ops
