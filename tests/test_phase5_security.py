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
from datetime import datetime, timezone, timedelta
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
        """Cleanup is handled by conftest.py clean_tables fixture (no-op here)."""

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


# ---------------------------------------------------------------------------
# Job Retention / prune_old_jobs
# ---------------------------------------------------------------------------


class TestJobRetention:
    """
    Phase 2 rewrite: tests for prune_old_jobs(db) using the async DB-backed implementation.

    Jobs are seeded directly into the SQLite test DB via run_with_test_db().
    created_at is backdated to simulate old jobs.
    prune_old_jobs(db) is called via asyncio.run() with a fresh test DB session.
    Audit entries are verified via GET /api/audit.
    """

    def _seed_job(self, job_id: str, status: str = "completed", age_seconds: float = 0) -> None:
        """Insert a job into the test DB with an optionally backdated created_at."""
        from app.db import models as db_models
        from conftest import run_with_test_db

        created_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)

        async def _insert(db):
            db.add(db_models.Job(
                job_id=job_id,
                status=status,
                created_at=created_at,
                updated_at=created_at,
            ))
            await db.commit()

        run_with_test_db(_insert)

    def _run_prune(self, max_jobs_retained: int = 0, job_max_age_hours: float = 0) -> int:
        """Call prune_old_jobs(db) with the given settings and return the count pruned."""
        import asyncio
        from sqlalchemy import event
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from conftest import TEST_DATABASE_URL

        async def _do_prune():
            engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})

            @event.listens_for(engine.sync_engine, "connect")
            def _fk_on(dbapi_conn, _record):
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

            factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as db:
                with patch("app.services.job_manager.settings") as mock:
                    mock.max_jobs_retained = max_jobs_retained
                    mock.job_max_age_hours = job_max_age_hours
                    count = await job_manager.prune_old_jobs(db)
            await engine.dispose()
            return count

        return asyncio.run(_do_prune())

    def _list_job_ids(self) -> list[str]:
        """Return all job_ids currently in the DB."""
        from conftest import run_with_test_db
        from app.db import models as db_models
        from sqlalchemy import select

        async def _query(db):
            result = await db.execute(select(db_models.Job.job_id))
            return [r for r in result.scalars()]

        return run_with_test_db(_query)

    def _get_audit_ops(self) -> list[str]:
        """Return all operations in the audit_log table."""
        from conftest import run_with_test_db
        from app.db import models as db_models
        from sqlalchemy import select

        async def _query(db):
            result = await db.execute(select(db_models.AuditEntry.operation))
            return [r for r in result.scalars()]

        return run_with_test_db(_query)

    def test_no_retention_limits_prunes_nothing(self):
        self._seed_job("job-1", status="completed", age_seconds=7201)
        pruned = self._run_prune(max_jobs_retained=0, job_max_age_hours=0)
        assert pruned == 0
        assert "job-1" in self._list_job_ids()

    def test_age_based_pruning_removes_old_jobs(self):
        self._seed_job("old-job", status="completed", age_seconds=7201)  # ~2 hours old
        self._seed_job("new-job", status="completed", age_seconds=10)    # 10 seconds old
        pruned = self._run_prune(max_jobs_retained=0, job_max_age_hours=1)
        assert pruned == 1
        remaining = self._list_job_ids()
        assert "old-job" not in remaining
        assert "new-job" in remaining

    def test_count_based_pruning_keeps_newest(self):
        self._seed_job("oldest", status="completed", age_seconds=300)
        self._seed_job("middle", status="completed", age_seconds=200)
        self._seed_job("newest", status="completed", age_seconds=10)
        pruned = self._run_prune(max_jobs_retained=2, job_max_age_hours=0)
        assert pruned == 1
        remaining = self._list_job_ids()
        assert "oldest" not in remaining
        assert "middle" in remaining
        assert "newest" in remaining

    def test_pruning_does_not_remove_running_jobs(self):
        self._seed_job("running-job", status="running", age_seconds=0)
        self._seed_job("completed-old", status="completed", age_seconds=100)
        self._seed_job("completed-extra", status="completed", age_seconds=50)
        pruned = self._run_prune(max_jobs_retained=1, job_max_age_hours=0)
        assert pruned == 1
        assert "running-job" in self._list_job_ids()

    def test_pruning_clears_all_related_data(self):
        """Pruned jobs' cascade deletes remove related documents, chunks, and logs."""
        from app.db import models as db_models
        from conftest import run_with_test_db
        from sqlalchemy import select

        self._seed_job("old-with-data", status="completed", age_seconds=7201)

        async def _seed_related(db):
            db.add(db_models.Document(
                job_id="old-with-data",
                documento_id="doc-sha",
                data={"documento_id": "doc-sha", "file_index": {}, "named_entities": []},
            ))
            db.add(db_models.JobLog(job_id="old-with-data", message="some log"))
            await db.commit()

        run_with_test_db(_seed_related)

        self._run_prune(max_jobs_retained=0, job_max_age_hours=1)

        async def _check(db):
            docs = await db.execute(select(db_models.Document).where(db_models.Document.job_id == "old-with-data"))
            logs = await db.execute(select(db_models.JobLog).where(db_models.JobLog.job_id == "old-with-data"))
            return list(docs.scalars()), list(logs.scalars())

        docs, logs = run_with_test_db(_check)
        assert docs == []
        assert logs == []

    def test_pruning_writes_audit_entry(self):
        self._seed_job("prune-me", status="completed", age_seconds=7201)
        self._run_prune(max_jobs_retained=0, job_max_age_hours=1)
        ops = self._get_audit_ops()
        assert "job.pruned" in ops

