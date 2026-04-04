import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
});

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

export async function executeReorganization(
  jobId: string
): Promise<{ moved: number; errors: number }> {
  const { data } = await api.post(`/api/reorganize/${jobId}/execute`);
  return data;
}
