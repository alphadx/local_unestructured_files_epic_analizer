"""Tests for admin API endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.main import app
from app.services import audit_log

client = TestClient(app)


class TestAdminFilterStats:
    """Test /api/admin/filter-stats endpoint."""

    def test_filter_stats_empty(self):
        """Test endpoint returns empty stats when no filters applied."""
        response = client.get("/api/admin/filter-stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_scans_with_filters"] == 0
        assert data["total_files_filtered"] == 0
        assert data["scans"] == []

    def test_filter_stats_with_filtered_files(self):
        """Test endpoint returns stats when files have been filtered."""
        job_id = "test-job-123"
        skipped_files = [
            {"path": "/home/test/file.exe", "reason": "extension in blacklist: .exe"},
            {"path": "/home/test/lib.so", "reason": "extension in blacklist: .so"},
        ]

        # Record a filter event
        audit_log.record(
            "scan.files_filtered",
            actor="system",
            resource_id=job_id,
            resource_type="job",
            outcome="success",
            skipped_count=2,
            skipped_files=skipped_files,
            filters_applied=True,
        )

        response = client.get("/api/admin/filter-stats")
        assert response.status_code == 200
        data = response.json()

        assert data["total_scans_with_filters"] == 1
        assert data["total_files_filtered"] == 2
        assert len(data["scans"]) == 1

        scan = data["scans"][0]
        assert scan["job_id"] == job_id
        assert scan["skipped_count"] == 2
        assert len(scan["skipped_files"]) == 2
        assert scan["skipped_files"][0]["path"] == "/home/test/file.exe"

    def test_filter_stats_with_job_id_filter(self):
        """Test filtering stats by job_id."""
        job_id_1 = "job-1"
        job_id_2 = "job-2"

        # Record events for two different jobs
        audit_log.record(
            "scan.files_filtered",
            actor="system",
            resource_id=job_id_1,
            resource_type="job",
            outcome="success",
            skipped_count=1,
            skipped_files=[{"path": "/home/test/file.exe", "reason": "extension in blacklist"}],
        )

        audit_log.record(
            "scan.files_filtered",
            actor="system",
            resource_id=job_id_2,
            resource_type="job",
            outcome="success",
            skipped_count=3,
            skipped_files=[
                {"path": "/home/test/lib.so", "reason": "extension in blacklist"},
                {"path": "/home/test/app.dll", "reason": "extension in blacklist"},
                {"path": "/home/test/exec.bin", "reason": "extension in blacklist"},
            ],
        )

        # Test filtering by job_id_1
        response = client.get(f"/api/admin/filter-stats?job_id={job_id_1}")
        assert response.status_code == 200
        data = response.json()
        assert data["total_scans_with_filters"] == 1
        assert data["total_files_filtered"] == 1
        assert data["scans"][0]["job_id"] == job_id_1

        # Test filtering by job_id_2
        response = client.get(f"/api/admin/filter-stats?job_id={job_id_2}")
        assert response.status_code == 200
        data = response.json()
        assert data["total_scans_with_filters"] == 1
        assert data["total_files_filtered"] == 3
        assert data["scans"][0]["job_id"] == job_id_2

    def test_filter_stats_pagination(self):
        """Test pagination parameters."""
        # Record multiple filter events
        for i in range(5):
            audit_log.record(
                "scan.files_filtered",
                actor="system",
                resource_id=f"job-{i}",
                resource_type="job",
                outcome="success",
                skipped_count=i + 1,
                skipped_files=[],
            )

        # Test with limit
        response = client.get("/api/admin/filter-stats?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["scans"]) == 2

        # Test with offset
        response = client.get("/api/admin/filter-stats?limit=2&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["scans"]) == 2

    def test_filter_stats_total_calculation(self):
        """Test that total files filtered is calculated correctly."""
        # Record events with different skipped counts
        for i in range(3):
            audit_log.record(
                "scan.files_filtered",
                actor="system",
                resource_id=f"job-calc-{i}",
                resource_type="job",
                outcome="success",
                skipped_count=10 * (i + 1),  # 10, 20, 30
                skipped_files=[],
            )

        response = client.get("/api/admin/filter-stats")
        assert response.status_code == 200
        data = response.json()
        # Total should be 10 + 20 + 30 = 60 (plus any from previous tests, but newest ones count)
        assert data["total_files_filtered"] >= 60
