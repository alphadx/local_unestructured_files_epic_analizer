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


class TestAuditBinaryDetection:
    """Test that binary file detection is properly audited and queryable."""

    def test_binary_skip_registered_as_filtered_file(self):
        """Test that skipped binary files are logged as filtered."""
        job_id = "binary-test-job-001"
        
        # Simulate binary detection audit records
        audit_log.record(
            "scan.files_filtered",
            actor="system",
            resource_id=job_id,
            resource_type="job",
            outcome="success",
            skipped_count=3,
            skipped_files=[
                {
                    "path": "/data/image.jpg",
                    "reason": "extraction_method=skipped_binary (MIME: image/jpeg)",
                    "extraction_method": "skipped_binary",
                },
                {
                    "path": "/data/archive.zip",
                    "reason": "extraction_method=skipped_binary (extension: .zip)",
                    "extraction_method": "skipped_binary",
                },
                {
                    "path": "/data/binary.exe",
                    "reason": "extraction_method=skipped_binary (extension: .exe)",
                    "extraction_method": "skipped_binary",
                },
            ],
            filters_applied=True,
        )

        # Query filter stats
        response = client.get("/api/admin/filter-stats")
        assert response.status_code == 200
        data = response.json()

        # Find our job
        job_stats = None
        for scan in data["scans"]:
            if scan["job_id"] == job_id:
                job_stats = scan
                break

        assert job_stats is not None, "Job audit entry not found"
        assert job_stats["skipped_count"] == 3
        assert len(job_stats["skipped_files"]) == 3

        # Verify extraction_method is tagged on each skipped file
        for skipped_file in job_stats["skipped_files"]:
            assert "extraction_method=skipped_binary" in skipped_file["reason"]
            assert skipped_file["extraction_method"] == "skipped_binary"

    def test_binary_vs_extension_skip_differentiation(self):
        """Test that we can differentiate binary skip reasons."""
        job_id = "binary-reason-test-002"

        audit_log.record(
            "scan.files_filtered",
            actor="system",
            resource_id=job_id,
            resource_type="job",
            outcome="success",
            skipped_count=2,
            skipped_files=[
                {
                    "path": "/data/photo.jpg",
                    "reason": "extraction_method=skipped_binary (MIME: image/jpeg)",
                    "extraction_method": "skipped_binary",
                    "skip_type": "binary_mime",
                },
                {
                    "path": "/data/archive.zip",
                    "reason": "extraction_method=skipped_binary (extension: .zip)",
                    "extraction_method": "skipped_binary",
                    "skip_type": "binary_extension",
                },
            ],
            filters_applied=True,
        )

        response = client.get(f"/api/admin/filter-stats?job_id={job_id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["scans"]) == 1
        scan = data["scans"][0]
        assert scan["skipped_count"] == 2

        # Verify we can filter by skip type
        mime_skip = next(
            (f for f in scan["skipped_files"] if f.get("skip_type") == "binary_mime"),
            None,
        )
        ext_skip = next(
            (f for f in scan["skipped_files"] if f.get("skip_type") == "binary_extension"),
            None,
        )

        assert mime_skip is not None
        assert ext_skip is not None
        assert "image/jpeg" in mime_skip["reason"]
        assert ".zip" in ext_skip["reason"]

    def test_filter_stats_query_by_extraction_method(self):
        """Test filtering stats by extraction_method."""
        job_id = "binary-filter-query-003"

        audit_log.record(
            "scan.files_filtered",
            actor="system",
            resource_id=job_id,
            resource_type="job",
            outcome="success",
            skipped_count=2,
            skipped_files=[
                {
                    "path": "/data/exec.exe",
                    "reason": "extraction_method=skipped_binary",
                    "extraction_method": "skipped_binary",
                },
                {
                    "path": "/data/lib.so",
                    "reason": "extraction_method=skipped_binary",
                    "extraction_method": "skipped_binary",
                },
            ],
            filters_applied=True,
        )

        # Query stats
        response = client.get(f"/api/admin/filter-stats?job_id={job_id}")
        assert response.status_code == 200
        data = response.json()

        # All skipped files should have extraction_method="skipped_binary"
        for scan in data["scans"]:
            for skipped_file in scan["skipped_files"]:
                assert skipped_file.get("extraction_method") == "skipped_binary"
