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

export interface ScanRequest {
  path: string;
  enable_pii_detection: boolean;
  enable_embeddings: boolean;
  enable_clustering: boolean;
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
