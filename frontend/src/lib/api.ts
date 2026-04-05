import axios from "axios";

const DEFAULT_API = "http://localhost:8080";
// Priority: build-time env var -> runtime window override (window.__API_BASE__) -> default
const API_BASE = process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? (window as any).__API_BASE__ : undefined) || DEFAULT_API;

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
});

// Allow changing the API endpoint at runtime (useful in Codespaces/GitHub.dev where localhost isn't reachable)
export function setApiBase(url: string) {
  api.defaults.baseURL = url;
}

export function getApiBase(): string {
  return api.defaults.baseURL as string;
}

export function setApiKey(key: string) {
  if (key) {
    api.defaults.headers.common["X-Api-Key"] = key;
  } else {
    delete api.defaults.headers.common["X-Api-Key"];
  }
}

// ---------------------------------------------------------------------------
// Types (mirrors backend Pydantic schemas)
// ---------------------------------------------------------------------------

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface JobProgress {
  job_id: string;
  status: JobStatus;
  total_files: number;
  processed_files: number;
  message: string;
  error?: string;
}

export type SourceProvider = "local" | "google_drive" | "sharepoint";

export interface ScanRequest {
  path: string;
  source_provider: SourceProvider;
  source_options?: Record<string, string>;
  enable_pii_detection: boolean;
  enable_embeddings: boolean;
  enable_clustering: boolean;
  group_mode: GroupMode;
}

export interface ClusterItem {
  documento_id: string;
  path: string;
  categoria: string;
  resumen?: string;
}

export interface DocumentChunk {
  chunk_id: string;
  documento_id: string;
  artifact_kind: "fragmento";
  source_path: string;
  chunk_index: number;
  text: string;
  title?: string | null;
  section_path: string[];
  page_number?: number | null;
  token_count?: number | null;
}

export interface Cluster {
  cluster_id: string;
  label: string;
  document_count: number;
  documents: ClusterItem[];
  inconsistencies: string[];
  suggested_path?: string;
  family_label?: string | null;
}

export interface DuplicateGroup {
  sha256: string;
  files: string[];
}

export interface DataHealthReport {
  job_id: string;
  total_files: number;
  duplicates: number;
  duplicate_groups: DuplicateGroup[];
  pii_files: number;
  uncategorised_files: number;
  consistency_errors: string[];
  clusters: Cluster[];
  reorganisation_plan: Array<{
    documento_id: string;
    current_path: string;
    suggested_path: string;
    cluster: string;
  }>;
}

export interface ClusterSummary {
  cluster_id: string;
  label: string;
  document_count: number;
  inconsistency_count: number;
}

export interface JobStatistics {
  job_id: string;
  total_files: number;
  unique_files: number;
  duplicate_files: number;
  extension_breakdown: Record<string, number>;
  category_distribution: Record<string, number>;
  mime_breakdown: Record<string, number>;
  size_bucket_distribution: Record<string, number>;
  directory_breakdown: Record<string, number>;
  temporal_distribution: Record<string, number>;
  pii_risk_distribution: Record<string, number>;
  keyword_distribution: Record<string, number>;
  semantic_coverage: number;
  cluster_summary: ClusterSummary[];
}

export interface CorpusFacetItem {
  label: string;
  count: number;
  share: number;
}

export interface DirectoryHotspot {
  path: string;
  count: number;
  duplicate_count: number;
  unknown_count: number;
  share: number;
}

export interface TopicSummary {
  label: string;
  document_count: number;
  inconsistency_count: number;
  share: number;
}

export interface RelationNode {
  id: string;
  label: string;
  kind: string;
  group?: string | null;
}

export interface RelationEdge {
  source: string;
  target: string;
  relation_type: string;
  count: number;
}

export interface RelationGraph {
  nodes: RelationNode[];
  edges: RelationEdge[];
  node_count: number;
  edge_count: number;
}

export interface TemporalBucket {
  label: string;
  count: number;
  share: number;
}

export interface CorpusExplorationReport {
  job_id: string;
  total_files: number;
  unique_files: number;
  duplicate_files: number;
  top_extensions: CorpusFacetItem[];
  top_directories: CorpusFacetItem[];
  dominant_categories: CorpusFacetItem[];
  dominant_clusters: TopicSummary[];
  noisy_directories: DirectoryHotspot[];
  temporal_heatmap: TemporalBucket[];
  relation_graph: RelationGraph;
  uncategorised_share: number;
  pii_share: number;
  concentration_index: number;
}

export type SearchScope = "all" | "documents" | "chunks" | "hybrid";

export interface SearchRequest {
  query?: string | null;
  job_id?: string | null;
  category?: string[];
  extension?: string[];
  directory?: string[];
  scope?: SearchScope;
  top_k?: number;
}

export interface SearchResult {
  source_id: string;
  kind: string;
  title?: string | null;
  path: string;
  document_id: string;
  category: string;
  cluster_sugerido?: string | null;
  snippet: string;
  score: number;
  distance: number;
}

export interface SearchFacet {
  label: string;
  count: number;
  share: number;
}

export interface SearchResponse {
  query?: string | null;
  job_id?: string | null;
  total_results: number;
  results: SearchResult[];
  categories: SearchFacet[];
  extensions: SearchFacet[];
  directories: SearchFacet[];
  suggestions: string[];
}

export interface RagQueryRequest {
  query: string;
  job_id?: string | null;
  top_k?: number;
  include_answer?: boolean;
}

export interface RagSource {
  source_id: string;
  kind: string;
  document_id?: string | null;
  path?: string | null;
  title?: string | null;
  category?: string | null;
  cluster_sugerido?: string | null;
  chunk_index?: number | null;
  page_number?: number | null;
  snippet: string;
  distance: number;
  score: number;
}

export interface RagQueryResponse {
  query: string;
  answer?: string | null;
  context: string;
  sources: RagSource[];
}

// Group analysis types
export type GroupMode = "strict" | "extended";

export interface GroupFeatures {
  group_path: string;
  depth: number;
  file_count: number;
  unique_file_count: number;
  duplicate_count: number;
  category_distribution: Record<string, number>;
  extension_distribution: Record<string, number>;
  mime_distribution: Record<string, number>;
  semantic_dispersion: number;
  dominant_category?: string | null;
  dominant_category_share: number;
  pii_detection_count: number;
  pii_share: number;
  pii_risk_distribution: Record<string, number>;
  uncategorised_count: number;
  uncategorised_share: number;
  duplicate_share: number;
  fiscal_period_distribution: Record<string, number>;
  date_range_start?: string | null;
  date_range_end?: string | null;
}

export interface GroupProfile {
  group_id: string;
  job_id: string;
  group_path: string;
  group_mode: GroupMode;
  created_at: string;
  features: GroupFeatures;
  inferred_purpose?: string | null;
  health_score: number;
  health_factors: Record<string, number>;
  alerts: string[];
  recommendations: string[];
  representative_docs: string[];
}

export interface GroupSimilarity {
  group_a_id: string;
  group_b_id: string;
  group_a_path: string;
  group_b_path: string;
  semantic_similarity: number;
  category_overlap: number;
  operational_similarity: number;
  composite_score: number;
  similarity_level: "dissimilar" | "similar" | "equivalent";
  interpretation?: string | null;
}

export interface GroupSimilarityResponse {
  group_id: string;
  group_path: string;
  job_id: string;
  similar_groups: GroupSimilarity[];
}

export interface GroupAnalysisResult {
  job_id: string;
  group_count: number;
  total_groups_analyzed: number;
  groups: GroupProfile[];
  group_similarities: GroupSimilarity[];
  analysis_timestamp: string;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

export async function startScan(request: ScanRequest): Promise<JobProgress> {
  const { data } = await api.post<JobProgress>("/api/jobs", request);
  return data;
}

export async function getJob(jobId: string): Promise<JobProgress> {
  const { data } = await api.get<JobProgress>(`/api/jobs/${jobId}`);
  return data;
}

export async function listJobs(): Promise<JobProgress[]> {
  const { data } = await api.get<JobProgress[]>("/api/jobs");
  return data;
}

export async function getReport(jobId: string): Promise<DataHealthReport> {
  const { data } = await api.get<DataHealthReport>(`/api/reports/${jobId}`);
  return data;
}

export async function getChunks(jobId: string): Promise<DocumentChunk[]> {
  const { data } = await api.get<DocumentChunk[]>(`/api/reports/${jobId}/chunks`);
  return data;
}

export async function getStatistics(jobId: string): Promise<JobStatistics> {
  const { data } = await api.get<JobStatistics>(`/api/reports/${jobId}/statistics`);
  return data;
}

export async function getExploration(jobId: string): Promise<CorpusExplorationReport> {
  const { data } = await api.get<CorpusExplorationReport>(`/api/reports/${jobId}/exploration`);
  return data;
}

export async function getJobLogs(jobId: string): Promise<string[]> {
  const { data } = await api.get<string[]>(`/api/jobs/${jobId}/logs`);
  return data;
}

export async function searchCorpus(request: SearchRequest): Promise<SearchResponse> {
  const { data } = await api.post<SearchResponse>("/api/search", request);
  return data;
}

export async function queryRag(request: RagQueryRequest): Promise<RagQueryResponse> {
  const { data } = await api.post<RagQueryResponse>("/api/rag/query", request);
  return data;
}

export async function executeReorganization(
  jobId: string
): Promise<{ moved: number; errors: number }> {
  const { data } = await api.post(`/api/reorganize/${jobId}/execute`);
  return data;
}

export async function getGroups(jobId: string): Promise<GroupAnalysisResult> {
  const { data } = await api.get<GroupAnalysisResult>(`/api/reports/${jobId}/groups`);
  return data;
}

export async function getGroupSimilarities(
  jobId: string,
  groupId: string
): Promise<GroupSimilarityResponse> {
  const { data } = await api.get<GroupSimilarityResponse>(
    `/api/reports/${jobId}/groups/${groupId}/similarity`
  );
  return data;
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export interface AuditEntry {
  entry_id: string;
  timestamp: string;
  operation: string;
  actor: string;
  resource_id: string | null;
  resource_type: string | null;
  outcome: string;
  details: Record<string, unknown>;
}

export interface AuditLogResponse {
  total: number;
  offset: number;
  limit: number;
  entries: AuditEntry[];
}

export async function getAuditLog(params?: {
  operation?: string;
  resource_type?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditLogResponse> {
  const { data } = await api.get<AuditLogResponse>("/api/audit", { params });
  return data;
}

export async function pruneJobs(): Promise<{ pruned: number }> {
  const { data } = await api.post<{ pruned: number }>("/api/jobs/prune");
  return data;
}
