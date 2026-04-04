from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DocumentCategory(str, Enum):
    INVOICE = "Factura_Proveedor"
    WORK_ORDER = "Orden_Trabajo"
    TENDER = "Licitacion"
    CREDIT_NOTE = "Nota_Credito"
    CONTRACT = "Contrato"
    REPORT = "Informe"
    IMAGE = "Imagen"
    UNKNOWN = "Desconocido"


class RiskLevel(str, Enum):
    GREEN = "verde"
    YELLOW = "amarillo"
    RED = "rojo"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# File-level schemas
# ---------------------------------------------------------------------------


class FileIndex(BaseModel):
    """Raw metadata collected without calling any AI API."""

    path: str
    name: str
    extension: str
    size_bytes: int
    created_at: str
    modified_at: str
    sha256: str
    mime_type: str | None = None
    is_duplicate: bool = False
    duplicate_of: str | None = None


class DocumentEntities(BaseModel):
    emisor: str | None = None
    receptor: str | None = None
    monto_total: float | None = None
    moneda: str | None = None


class DocumentRelations(BaseModel):
    id_licitacion_vinculada: str | None = None
    id_ot_referencia: str | None = None


class SemanticAnalysis(BaseModel):
    resumen: str | None = None
    cluster_sugerido: str | None = None
    confianza_clasificacion: float | None = None
    palabras_clave: list[str] = Field(default_factory=list)


class PiiInfo(BaseModel):
    detected: bool = False
    risk_level: RiskLevel = RiskLevel.GREEN
    details: list[str] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    """Full AI-enriched record for a document."""

    documento_id: str
    file_index: FileIndex
    categoria: DocumentCategory = DocumentCategory.UNKNOWN
    entidades: DocumentEntities = Field(default_factory=DocumentEntities)
    relaciones: DocumentRelations = Field(default_factory=DocumentRelations)
    analisis_semantico: SemanticAnalysis = Field(default_factory=SemanticAnalysis)
    pii_info: PiiInfo = Field(default_factory=PiiInfo)
    fecha_emision: str | None = None
    periodo_fiscal: str | None = None
    # Internal: not serialised to API clients
    embedding: list[float] | None = Field(default=None, exclude=True)


# ---------------------------------------------------------------------------
# Cluster schemas
# ---------------------------------------------------------------------------


class ClusterItem(BaseModel):
    documento_id: str
    path: str
    categoria: str
    resumen: str | None = None


class Cluster(BaseModel):
    cluster_id: str
    label: str
    document_count: int
    documents: list[ClusterItem] = Field(default_factory=list)
    inconsistencies: list[str] = Field(default_factory=list)
    suggested_path: str | None = None


# ---------------------------------------------------------------------------
# Job / scan schemas
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    path: str = Field(..., description="Absolute path to scan (read-only)")
    enable_pii_detection: bool = True
    enable_embeddings: bool = True
    enable_clustering: bool = True


class JobProgress(BaseModel):
    job_id: str
    status: JobStatus
    total_files: int = 0
    processed_files: int = 0
    message: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class DuplicateGroup(BaseModel):
    sha256: str
    files: list[str]


class DataHealthReport(BaseModel):
    job_id: str
    total_files: int
    duplicates: int
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    pii_files: int
    uncategorised_files: int
    consistency_errors: list[str] = Field(default_factory=list)
    clusters: list[Cluster] = Field(default_factory=list)
    reorganisation_plan: list[dict[str, Any]] = Field(default_factory=list)


class ClusterSummary(BaseModel):
    cluster_id: str
    label: str
    document_count: int
    inconsistency_count: int


class JobStatistics(BaseModel):
    """Detailed distribution statistics derived from a completed analysis job."""

    job_id: str
    total_files: int
    unique_files: int
    duplicate_files: int
    # File-system breakdown
    extension_breakdown: dict[str, int] = Field(
        default_factory=dict,
        description="Count of files per lowercase extension, e.g. {'.pdf': 12, '.docx': 5}",
    )
    # AI-classification breakdown
    category_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of documents per DocumentCategory value",
    )
    # PII risk levels
    pii_risk_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of documents per RiskLevel value: verde / amarillo / rojo",
    )
    # Cluster summary
    cluster_summary: list[ClusterSummary] = Field(default_factory=list)
