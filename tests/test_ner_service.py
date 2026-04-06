"""
Tests for NER service (Layer 1 regex + aggregation) and /api/reports/{job_id}/contacts endpoint.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import (
    ContactRecord,
    DocumentEntities,
    DocumentMetadata,
    FileIndex,
    NamedEntity,
    NamedEntityType,
)
from app.services import ner_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(doc_id: str, path: str, entities: list[NamedEntity]) -> DocumentMetadata:
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
        named_entities=entities,
    )


# ---------------------------------------------------------------------------
# Layer 1 — Regex extraction
# ---------------------------------------------------------------------------


class TestRegexExtraction:
    def test_extracts_email(self):
        entities = ner_service._extract_regex_entities("Contacta a juan@acme.cl para más info.")
        emails = [e for e in entities if e.entity_type == NamedEntityType.EMAIL]
        assert len(emails) == 1
        assert emails[0].value == "juan@acme.cl"
        assert emails[0].source == "regex"

    def test_extracts_multiple_emails(self):
        text = "De: a@b.com Para: c@d.org"
        entities = ner_service._extract_regex_entities(text)
        emails = [e for e in entities if e.entity_type == NamedEntityType.EMAIL]
        assert {e.value for e in emails} == {"a@b.com", "c@d.org"}

    def test_extracts_rut_with_dots(self):
        entities = ner_service._extract_regex_entities("RUT emisor: 12.345.678-9")
        ruts = [e for e in entities if e.entity_type == NamedEntityType.RUT]
        assert len(ruts) == 1
        assert ruts[0].value == "12345678-9"

    def test_extracts_rut_without_dots(self):
        entities = ner_service._extract_regex_entities("RUT: 76543210-K")
        ruts = [e for e in entities if e.entity_type == NamedEntityType.RUT]
        assert len(ruts) == 1
        assert ruts[0].value == "76543210-K"

    def test_extracts_phone(self):
        entities = ner_service._extract_regex_entities("Llame al +56912345678")
        phones = [e for e in entities if e.entity_type == NamedEntityType.PHONE]
        assert len(phones) == 1

    def test_no_false_positive_on_plain_text(self):
        entities = ner_service._extract_regex_entities("Hello world, no entities here.")
        assert entities == []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_deduplicates_same_type_and_value(self):
        entities = [
            NamedEntity(entity_type=NamedEntityType.EMAIL, value="a@b.com", confidence=0.9, source="regex"),
            NamedEntity(entity_type=NamedEntityType.EMAIL, value="A@B.COM", confidence=0.8, source="gemini"),
        ]
        result = ner_service._deduplicate(entities)
        assert len(result) == 1
        assert result[0].confidence == 0.9  # highest kept

    def test_keeps_different_types(self):
        entities = [
            NamedEntity(entity_type=NamedEntityType.EMAIL, value="a@b.com", confidence=1.0, source="regex"),
            NamedEntity(entity_type=NamedEntityType.PERSON, value="a@b.com", confidence=0.8, source="gemini"),
        ]
        result = ner_service._deduplicate(entities)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# extract_entities (no Gemini)
# ---------------------------------------------------------------------------


class TestExtractEntities:
    def test_extract_without_gemini(self):
        text = "Factura de juan@empresa.cl, RUT 12.345.678-9"
        entities = ner_service.extract_entities(text, use_gemini=False)
        types = {e.entity_type for e in entities}
        assert NamedEntityType.EMAIL in types
        assert NamedEntityType.RUT in types


# ---------------------------------------------------------------------------
# build_contacts_report
# ---------------------------------------------------------------------------


class TestBuildContactsReport:
    def test_empty_documents(self):
        report = ner_service.build_contacts_report("job-1", [])
        assert report.job_id == "job-1"
        assert report.total_documents_analyzed == 0
        assert report.total_entities_found == 0
        assert report.contacts == []

    def test_aggregates_across_documents(self):
        email_ent = NamedEntity(entity_type=NamedEntityType.EMAIL, value="a@b.com", confidence=1.0, source="regex")
        doc1 = _make_doc("d1", "/tmp/f1.txt", [email_ent])
        doc2 = _make_doc("d2", "/tmp/f2.txt", [email_ent])
        report = ner_service.build_contacts_report("job-2", [doc1, doc2])
        assert report.total_entities_found == 2
        assert len(report.contacts) == 1
        contact = report.contacts[0]
        assert contact.frequency == 2
        assert set(contact.document_ids) == {"d1", "d2"}

    def test_sorted_by_frequency(self):
        e1 = NamedEntity(entity_type=NamedEntityType.EMAIL, value="a@b.com", confidence=1.0, source="regex")
        e2 = NamedEntity(entity_type=NamedEntityType.EMAIL, value="c@d.com", confidence=1.0, source="regex")
        doc1 = _make_doc("d1", "/tmp/f1.txt", [e1, e2])
        doc2 = _make_doc("d2", "/tmp/f2.txt", [e1])
        report = ner_service.build_contacts_report("job-3", [doc1, doc2])
        assert report.contacts[0].value == "a@b.com"  # frequency 2
        assert report.contacts[1].value == "c@d.com"  # frequency 1


# ---------------------------------------------------------------------------
# /api/reports/{job_id}/contacts endpoint
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="TestContactsEndpoint relies on the Phase 1 in-memory job_manager._jobs "
    "and ._documents dicts which were removed in Phase 2 (replaced by PostgreSQL). "
    "Needs rewrite to insert test data via DB session."
)
class TestContactsEndpoint:
    @pytest.fixture
    def client_with_job(self, tmp_path):
        from app.main import app
        from app.services import job_manager
        from app.models.schemas import JobStatus

        job_id = "test-ner-job"
        # Bootstrap a completed job with two documents
        job_manager._jobs[job_id] = job_manager.JobProgress(
            job_id=job_id,
            status=JobStatus.COMPLETED,
        )
        email_ent = NamedEntity(
            entity_type=NamedEntityType.EMAIL, value="test@corp.cl", confidence=1.0, source="regex"
        )
        org_ent = NamedEntity(
            entity_type=NamedEntityType.ORGANIZATION, value="Corp SA", confidence=0.9, source="gemini"
        )
        fi = FileIndex(
            path=str(tmp_path / "doc.txt"),
            name="doc.txt",
            extension=".txt",
            size_bytes=50,
            created_at="2026-01-01T00:00:00",
            modified_at="2026-01-01T00:00:00",
            sha256="sha-test",
        )
        doc = DocumentMetadata(
            documento_id="sha-test",
            file_index=fi,
            named_entities=[email_ent, org_ent],
        )
        job_manager._documents[job_id] = [doc]

        with TestClient(app) as c:
            yield c, job_id

        # Cleanup
        job_manager._jobs.pop(job_id, None)
        job_manager._documents.pop(job_id, None)

    def test_contacts_returns_all_entities(self, client_with_job):
        client, job_id = client_with_job
        resp = client.get(f"/api/reports/{job_id}/contacts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["total_documents_analyzed"] == 1
        assert len(data["contacts"]) == 2

    def test_contacts_filter_by_entity_type(self, client_with_job):
        client, job_id = client_with_job
        resp = client.get(f"/api/reports/{job_id}/contacts?entity_type=EMAIL")
        assert resp.status_code == 200
        data = resp.json()
        assert all(c["entity_type"] == "EMAIL" for c in data["contacts"])

    def test_contacts_filter_by_min_frequency(self, client_with_job):
        client, job_id = client_with_job
        resp = client.get(f"/api/reports/{job_id}/contacts?min_frequency=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["contacts"] == []  # all entities appear only once

    def test_contacts_not_found(self, client_with_job):
        client, _ = client_with_job
        resp = client.get("/api/reports/nonexistent-job/contacts")
        assert resp.status_code == 404
