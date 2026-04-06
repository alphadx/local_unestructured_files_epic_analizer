from __future__ import annotations

"""
SQLAlchemy ORM models for Phase 2 persistent storage.

Complex nested Pydantic structures (documents, reports, etc.) are stored
as JSON to avoid mapping every nested field to a column.  This is pragmatic
for the current phase and can be normalised later.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Use JSON type that works with both PostgreSQL (JSONB) and SQLite (JSON).
# We declare a custom type that picks JSONB for PostgreSQL URLs.
class _FlexJSON(JSON):
    """JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite for tests)."""

    def __init__(self) -> None:
        super().__init__(none_as_null=False)

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    documents_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Extra fields used by the pipeline (total_files, processed_files)
    extra: Mapped[dict] = mapped_column(_FlexJSON(), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    logs: Mapped[list[JobLog]] = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    report: Mapped[Report | None] = relationship("Report", back_populates="job", uselist=False, cascade="all, delete-orphan")
    documents: Mapped[list[Document]] = relationship("Document", back_populates="job", cascade="all, delete-orphan")
    group_analysis: Mapped[GroupAnalysis | None] = relationship("GroupAnalysis", back_populates="job", uselist=False, cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Job logs (for persistent history + WebSocket replay)
# ---------------------------------------------------------------------------


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    job: Mapped[Job] = relationship("Job", back_populates="logs")


# ---------------------------------------------------------------------------
# Reports (DataHealthReport stored as JSON blob)
# ---------------------------------------------------------------------------


class Report(Base):
    __tablename__ = "reports"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(_FlexJSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    job: Mapped[Job] = relationship("Job", back_populates="report")


# ---------------------------------------------------------------------------
# Documents (DocumentMetadata stored as JSON blob)
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    documento_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    data: Mapped[dict] = mapped_column(_FlexJSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    job: Mapped[Job] = relationship("Job", back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Chunks (DocumentChunk stored as JSON blob)
# ---------------------------------------------------------------------------


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, primary_key=True)
    documento_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    data: Mapped[dict] = mapped_column(_FlexJSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "documento_id"],
            ["documents.job_id", "documents.documento_id"],
            ondelete="CASCADE",
        ),
    )

    document: Mapped[Document] = relationship("Document", back_populates="chunks")


# ---------------------------------------------------------------------------
# Group analysis (GroupAnalysisResult stored as JSON blob)
# ---------------------------------------------------------------------------


class GroupAnalysis(Base):
    __tablename__ = "group_analysis"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(_FlexJSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    job: Mapped[Job] = relationship("Job", back_populates="group_analysis")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditEntry(Base):
    __tablename__ = "audit_log"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    resource_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(_FlexJSON(), nullable=False, default=dict)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
