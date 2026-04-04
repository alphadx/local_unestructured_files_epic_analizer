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


class ArtifactKind(str, Enum):
    PHYSICAL_FILE = "archivo_fisico"
    LOGICAL_DOCUMENT = "documento_logico"
    CHUNK = "fragmento"


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
    artifact_kind: ArtifactKind = ArtifactKind.LOGICAL_DOCUMENT
    categoria: DocumentCategory = DocumentCategory.UNKNOWN
    entidades: DocumentEntities = Field(default_factory=DocumentEntities)
    relaciones: DocumentRelations = Field(default_factory=DocumentRelations)
    analisis_semantico: SemanticAnalysis = Field(default_factory=SemanticAnalysis)
    pii_info: PiiInfo = Field(default_factory=PiiInfo)
    fecha_emision: str | None = None
    periodo_fiscal: str | None = None
    # Internal: not serialised to API clients
    embedding: list[float] | None = Field(default=None, exclude=True)


class DocumentChunk(BaseModel):
    """A semantic fragment extracted from a logical document."""

    chunk_id: str
    documento_id: str
    artifact_kind: ArtifactKind = ArtifactKind.CHUNK
    source_path: str
    chunk_index: int
    text: str
    title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_number: int | None = None
    token_count: int | None = None
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


class CorpusFacetItem(BaseModel):
    label: str
    count: int
    share: float = Field(ge=0.0, le=1.0)


class DirectoryHotspot(BaseModel):
    path: str
    count: int
    duplicate_count: int
    unknown_count: int
    share: float = Field(ge=0.0, le=1.0)


class TopicSummary(BaseModel):
    label: str
    document_count: int
    inconsistency_count: int
    share: float = Field(ge=0.0, le=1.0)


class CorpusExplorationReport(BaseModel):
    job_id: str
    total_files: int
    unique_files: int
    duplicate_files: int
    top_extensions: list[CorpusFacetItem] = Field(default_factory=list)
    top_directories: list[CorpusFacetItem] = Field(default_factory=list)
    dominant_categories: list[CorpusFacetItem] = Field(default_factory=list)
    dominant_clusters: list[TopicSummary] = Field(default_factory=list)
    noisy_directories: list[DirectoryHotspot] = Field(default_factory=list)
    uncategorised_share: float = Field(default=0.0, ge=0.0, le=1.0)
    pii_share: float = Field(default=0.0, ge=0.0, le=1.0)
    concentration_index: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchScope(str, Enum):
    ALL = "all"
    DOCUMENTS = "documents"
    CHUNKS = "chunks"
    HYBRID = "hybrid"


class SearchRequest(BaseModel):
    query: str | None = None
    job_id: str | None = None
    category: list[str] = Field(default_factory=list)
    extension: list[str] = Field(default_factory=list)
    directory: list[str] = Field(default_factory=list)
    scope: SearchScope = SearchScope.HYBRID
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    source_id: str
    kind: str
    title: str | None = None
    path: str
    document_id: str
    category: str
    cluster_sugerido: str | None = None
    snippet: str
    score: float = Field(ge=0.0, le=1.0)
    distance: float = Field(ge=0.0)


class SearchFacet(BaseModel):
    label: str
    count: int
    share: float = Field(ge=0.0, le=1.0)


class SearchResponse(BaseModel):
    query: str | None = None
    job_id: str | None = None
    total_results: int
    results: list[SearchResult] = Field(default_factory=list)
    categories: list[SearchFacet] = Field(default_factory=list)
    extensions: list[SearchFacet] = Field(default_factory=list)
    directories: list[SearchFacet] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


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
    mime_breakdown: dict[str, int] = Field(
        default_factory=dict,
        description="Count of documents per MIME type",
    )
    size_bucket_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of documents per file-size bucket",
    )
    directory_breakdown: dict[str, int] = Field(
        default_factory=dict,
        description="Count of documents per directory path",
    )
    # PII risk levels
    pii_risk_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of documents per RiskLevel value: verde / amarillo / rojo",
    )
    keyword_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of semantic keywords extracted from the corpus",
    )
    semantic_coverage: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Share of unique documents that were semantically classified",
    )
    # Cluster summary
    cluster_summary: list[ClusterSummary] = Field(default_factory=list)


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    job_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_answer: bool = True


class RagSource(BaseModel):
    source_id: str
    kind: str
    document_id: str | None = None
    path: str | None = None
    title: str | None = None
    category: str | None = None
    cluster_sugerido: str | None = None
    chunk_index: int | None = None
    page_number: int | None = None
    snippet: str
    distance: float
    score: float


class RagQueryResponse(BaseModel):
    query: str
    answer: str | None = None
    context: str
    sources: list[RagSource] = Field(default_factory=list)
