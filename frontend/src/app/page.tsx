"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AuditEntry,
  AuditLogResponse,
  ContactsReport,
  CorpusExplorationReport,
  DataHealthReport,
  GroupAnalysisResult,
  GroupSimilarityResponse,
  JobProgress,
  JobStatistics,
  RagQueryResponse,
  SearchResponse,
  SearchScope,
  GroupMode,
} from "@/lib/api";
import {
  executeReorganization,
  getApiBase,
  getAuditLog,
  getContacts,
  getExploration,
  getGroups,
  getGroupSimilarities,
  getJob,
  getReport,
  getStatistics,
  pruneJobs,
  queryRag,
  searchCorpus,
  setApiBase,
  setApiKey,
  startScan,
} from "@/lib/api";
import ClusterMap from "@/components/ClusterMap";
import FilterConfiguration from "@/components/FilterConfiguration";
import GroupAnalysis from "@/components/GroupAnalysis";
import HealthReport from "@/components/HealthReport";
import JobStatusCard from "@/components/JobStatusCard";
import NerReport from "@/components/NerReport";
import RelationGraph from "@/components/RelationGraph";
import StatisticsCharts from "@/components/StatisticsCharts";

const POLL_INTERVAL_MS = 2_000;

type Tab = "dashboard" | "clusters" | "groups" | "audit" | "exploration" | "search" | "rag" | "entities";

export default function Home() {
  const [path, setPath] = useState("/data/scan");
  const [apiUrl, setApiUrl] = useState(getApiBase());
  const [apiKey, setApiKeyState] = useState("");
  const [enablePii, setEnablePii] = useState(true);
  const [enableEmbed, setEnableEmbed] = useState(true);
  const [enableCluster, setEnableCluster] = useState(true);
  const [groupMode, setGroupMode] = useState<GroupMode>("strict");
  const [sourceProvider, setSourceProvider] = useState<"local" | "google_drive" | "sharepoint">("local");
  const [googleDriveFolderId, setGoogleDriveFolderId] = useState("");
  const [googleDriveServiceAccountJson, setGoogleDriveServiceAccountJson] = useState("");
  const [sharepointSiteId, setSharepointSiteId] = useState("");
  const [sharepointDriveId, setSharepointDriveId] = useState("");

  // Filter configuration overrides
  const [filterOverrides, setFilterOverrides] = useState<{
    ingestion_mode?: string;
    allowed_extensions?: string;
    denied_extensions?: string;
    allowed_mime_types?: string;
    denied_mime_types?: string;
  }>({});

  const [job, setJob] = useState<JobProgress | null>(null);
  const [report, setReport] = useState<DataHealthReport | null>(null);
  const [statistics, setStatistics] = useState<JobStatistics | null>(null);
  const [exploration, setExploration] = useState<CorpusExplorationReport | null>(null);
  const [groupAnalysis, setGroupAnalysis] = useState<GroupAnalysisResult | null>(null);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [ragResponse, setRagResponse] = useState<RagQueryResponse | null>(null);
  const [contacts, setContacts] = useState<ContactsReport | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLoadingInsights, setIsLoadingInsights] = useState(false);
  const [isLoadingGroups, setIsLoadingGroups] = useState(false);
  const [isLoadingContacts, setIsLoadingContacts] = useState(false);
  const [isLoadingSimilarities, setIsLoadingSimilarities] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [searchScope, setSearchScope] = useState<SearchScope>("hybrid");
  const [searchDirectory, setSearchDirectory] = useState("");
  const [searchCategory, setSearchCategory] = useState("");
  const [searchExtension, setSearchExtension] = useState("");
  const [ragQuery, setRagQuery] = useState("");
  const [ragIncludeAnswer, setRagIncludeAnswer] = useState(true);
  const [auditLog, setAuditLog] = useState<AuditLogResponse | null>(null);
  const [isLoadingAudit, setIsLoadingAudit] = useState(false);
  const [isPruning, setIsPruning] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  useEffect(() => {
    setApiBase(apiUrl.trim() || getApiBase());
  }, [apiUrl]);

  const resetInsights = useCallback(() => {
    setStatistics(null);
    setExploration(null);
    setGroupAnalysis(null);
    setSearchResponse(null);
    setRagResponse(null);
    setContacts(null);
  }, []);

  const loadInsights = useCallback(async (jobId: string) => {
    setIsLoadingInsights(true);
    setIsLoadingGroups(true);
    setIsLoadingContacts(true);
    try {
      const [stats, exp, groups, cts] = await Promise.all([
        getStatistics(jobId),
        getExploration(jobId),
        getGroups(jobId).catch(() => null),
        getContacts(jobId).catch(() => null),
      ]);
      setStatistics(stats);
      setExploration(exp);
      if (groups) {
        setGroupAnalysis(groups);
      }
      if (cts) {
        setContacts(cts);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error al cargar analíticas";
      setError(message);
    } finally {
      setIsLoadingInsights(false);
      setIsLoadingGroups(false);
      setIsLoadingContacts(false);
    }
  }, []);

  const handleLoadGroupSimilarities = useCallback(async (groupId: string) => {
    if (!job) throw new Error("Job not found");
    setIsLoadingSimilarities(true);
    try {
      return await getGroupSimilarities(job.job_id, groupId);
    } finally {
      setIsLoadingSimilarities(false);
    }
  }, [job]);

  const parseBackendValidationErrors = (err: unknown): Record<string, string> | null => {
    const axiosError = err as { response?: any };
    const detail = axiosError?.response?.data?.detail;
    if (!Array.isArray(detail)) {
      return null;
    }

    const fieldNameMap: Record<string, string> = {
      folder_id: "googleDriveFolderId",
      service_account_json: "googleDriveServiceAccountJson",
      site_id: "sharepointSiteId",
      drive_id: "sharepointDriveId",
      path: "path",
    };

    const parsed: Record<string, string> = {};
    detail.forEach((item: any) => {
      if (typeof item.msg !== "string") {
        return;
      }
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const rawField = loc.length > 0 ? String(loc[loc.length - 1]) : "form";
      const field = fieldNameMap[rawField] ?? rawField;
      parsed[field] = item.msg;
    });

    return Object.keys(parsed).length > 0 ? parsed : null;
  };

  const handleScan = async () => {
    setError(null);
    setFormError(null);
    setFieldErrors({});
    setReport(null);
    setJob(null);
    resetInsights();
    stopPolling();

    const errors: Record<string, string> = {};
    if (!path.trim()) {
      errors.path = "Debe ingresar una ruta o ID raíz para iniciar el análisis.";
    }

    if (sourceProvider === "google_drive") {
      if (!googleDriveFolderId.trim() && !path.trim()) {
        errors.googleDriveFolderId =
          "Google Drive requiere un folder_id o un path de carpeta válido.";
      }
      if (googleDriveServiceAccountJson.trim()) {
        try {
          JSON.parse(googleDriveServiceAccountJson);
        } catch {
          errors.googleDriveServiceAccountJson =
            "El JSON de la cuenta de servicio de Google Drive no es válido.";
        }
      }
    }

    if (sourceProvider === "sharepoint") {
      if (!sharepointSiteId.trim()) {
        errors.sharepointSiteId = "SharePoint requiere un Site ID.";
      }
      if (!sharepointDriveId.trim()) {
        errors.sharepointDriveId = "SharePoint requiere un Drive ID.";
      }
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setFormError("Corrige los errores del formulario antes de continuar.");
      return;
    }

    setApiBase(apiUrl.trim() || getApiBase());
    setApiKey(apiKey.trim());

    try {
      const sourceOptions: Record<string, string> = {};
      if (sourceProvider === "google_drive") {
        if (googleDriveFolderId.trim()) {
          sourceOptions.folder_id = googleDriveFolderId.trim();
        }
        if (googleDriveServiceAccountJson.trim()) {
          sourceOptions.service_account_json = googleDriveServiceAccountJson.trim();
        }
      }
      if (sourceProvider === "sharepoint") {
        sourceOptions.site_id = sharepointSiteId.trim();
        sourceOptions.drive_id = sharepointDriveId.trim();
      }

      const newJob = await startScan({
        path: path.trim(),
        source_provider: sourceProvider,
        source_options: sourceOptions,
        enable_pii_detection: enablePii,
        enable_embeddings: enableEmbed,
        enable_clustering: enableCluster,
        group_mode: groupMode,
        ...filterOverrides,
      });
      setJob(newJob);

      pollRef.current = setInterval(async () => {
        try {
          const updated = await getJob(newJob.job_id);
          setJob(updated);
          if (updated.status === "completed") {
            stopPolling();
            const rep = await getReport(newJob.job_id);
            setReport(rep);
            await loadInsights(newJob.job_id);
          } else if (updated.status === "failed") {
            stopPolling();
          }
        } catch {
          // network blip – keep polling
        }
      }, POLL_INTERVAL_MS);
    } catch (err: unknown) {
      const axiosError = err as { response?: any };
      if (axiosError?.response?.status === 422) {
        const parsedFieldErrors = parseBackendValidationErrors(err);
        if (parsedFieldErrors) {
          setFieldErrors(parsedFieldErrors);
          setFormError("Corrige los errores del formulario antes de continuar.");
          return;
        }
      }

      const message =
        err instanceof Error ? err.message : "Error al iniciar el análisis";
      setError(message);
    }
  };

  const handleExecuteReorg = async () => {
    if (!job) return;
    setIsExecuting(true);
    try {
      await executeReorganization(job.job_id);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Error al ejecutar reorganización";
      setError(message);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleSearch = async () => {
    if (!job) return;
    setIsSearching(true);
    setError(null);
    try {
      const response = await searchCorpus({
        job_id: job.job_id,
        query: searchQuery.trim() || undefined,
        category: searchCategory
          ? searchCategory.split(",").map((item) => item.trim()).filter(Boolean)
          : [],
        extension: searchExtension
          ? searchExtension.split(",").map((item) => item.trim()).filter(Boolean)
          : [],
        directory: searchDirectory
          ? searchDirectory.split(",").map((item) => item.trim()).filter(Boolean)
          : [],
        scope: searchScope,
        top_k: 10,
      });
      setSearchResponse(response);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error al buscar";
      setError(message);
    } finally {
      setIsSearching(false);
    }
  };

  const handleRag = async () => {
    if (!job || !ragQuery.trim()) return;
    setIsAsking(true);
    setError(null);
    try {
      const response = await queryRag({
        query: ragQuery.trim(),
        job_id: job.job_id,
        top_k: 5,
        include_answer: ragIncludeAnswer,
      });
      setRagResponse(response);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error al consultar RAG";
      setError(message);
    } finally {
      setIsAsking(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "dashboard", label: "Dashboard" },
    { id: "clusters", label: "Mapa de Clusters" },
    { id: "groups", label: "Análisis de Grupos" },
    { id: "entities", label: "Entidades (NER)" },
    { id: "audit", label: "Auditoría" },
    { id: "exploration", label: "Exploración" },
    { id: "search", label: "Búsqueda" },
    { id: "rag", label: "RAG" },
  ];

  const topStats = useMemo(() => {
    if (!statistics) return [];
    return [
      { label: "Cobertura semántica", value: `${Math.round(statistics.semantic_coverage * 100)}%` },
      { label: "Extensiones", value: Object.keys(statistics.extension_breakdown).length },
      { label: "Clusters", value: statistics.cluster_summary.length },
      {
        label: "PII",
        value: Object.values(statistics.pii_risk_distribution).reduce(
          (a, b) => a + b,
          0
        ),
      },
    ];
  }, [statistics]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto max-w-6xl">
          <h1 className="text-2xl font-bold text-gray-900">
            🧠 Analizador de Archivos Inteligente
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Gobernanza de Datos · Powered by Gemini - Por Alexander Espina Leyton
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8 space-y-6">
        {/* Scan form */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            Iniciar Análisis
          </h2>

          <div className="space-y-4">
            <div className="grid gap-4">
              <label className="flex flex-col gap-2 text-sm text-gray-700">
                <span>API Endpoint</span>
                <input
                  type="text"
                  value={apiUrl}
                  onChange={(e) => {
                    setApiUrl(e.target.value);
                    setApiBase(e.target.value.trim() || getApiBase());
                  }}
                  placeholder="http://localhost:8080"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </label>
              <label className="flex flex-col gap-2 text-sm text-gray-700">
                <span>API Key <span className="font-normal text-gray-400">(opcional — dejar vacío si no está configurada)</span></span>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKeyState(e.target.value)}
                  placeholder="sk-..."
                  autoComplete="off"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </label>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm text-gray-700">
                <span>Proveedor de fuente</span>
                <select
                  value={sourceProvider}
                  onChange={(e) => setSourceProvider(e.target.value as any)}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="local">Local</option>
                  <option value="google_drive">Google Drive</option>
                  <option value="sharepoint">SharePoint</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-sm text-gray-700">
                <span>Ruta / ID raíz</span>
                <input
                  type="text"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder={
                    sourceProvider === "local"
                      ? "/ruta/a/los/archivos"
                      : sourceProvider === "google_drive"
                      ? "Google Drive folder ID"
                      : "SharePoint path dentro del sitio"
                  }
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {fieldErrors.path ? (
                  <span className="text-sm text-red-700">{fieldErrors.path}</span>
                ) : null}
              </label>
            </div>

            {sourceProvider === "google_drive" ? (
              <div className="space-y-4 rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
                <p className="font-medium">Opciones de Google Drive</p>
                <label className="flex flex-col gap-2 text-sm text-blue-900">
                  <span>Folder ID</span>
                  <input
                    type="text"
                    value={googleDriveFolderId}
                    onChange={(e) => setGoogleDriveFolderId(e.target.value)}
                    placeholder="Carpeta raíz de Google Drive"
                    className="rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  {fieldErrors.googleDriveFolderId ? (
                    <span className="text-sm text-red-700">
                      {fieldErrors.googleDriveFolderId}
                    </span>
                  ) : null}
                </label>
                <label className="flex flex-col gap-2 text-sm text-blue-900">
                  <span>Service Account JSON</span>
                  <textarea
                    value={googleDriveServiceAccountJson}
                    onChange={(e) => setGoogleDriveServiceAccountJson(e.target.value)}
                    placeholder="PEM/JSON de cuenta de servicio"
                    rows={4}
                    className="min-h-[120px] rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  {fieldErrors.googleDriveServiceAccountJson ? (
                    <span className="text-sm text-red-700">
                      {fieldErrors.googleDriveServiceAccountJson}
                    </span>
                  ) : null}
                </label>
              </div>
            ) : null}

            {sourceProvider === "sharepoint" ? (
              <div className="space-y-4 rounded-xl border border-green-100 bg-green-50 p-4 text-sm text-green-900">
                <p className="font-medium">Opciones de SharePoint</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="flex flex-col gap-2 text-sm text-green-900">
                    <span>Site ID</span>
                    <input
                      type="text"
                      value={sharepointSiteId}
                      onChange={(e) => setSharepointSiteId(e.target.value)}
                      placeholder="SharePoint site ID"
                      className="rounded-lg border border-green-200 bg-white px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    {fieldErrors.sharepointSiteId ? (
                      <span className="text-sm text-red-700">
                        {fieldErrors.sharepointSiteId}
                      </span>
                    ) : null}
                  </label>
                  <label className="flex flex-col gap-2 text-sm text-green-900">
                    <span>Drive ID</span>
                    <input
                      type="text"
                      value={sharepointDriveId}
                      onChange={(e) => setSharepointDriveId(e.target.value)}
                      placeholder="SharePoint drive ID"
                      className="rounded-lg border border-green-200 bg-white px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    {fieldErrors.sharepointDriveId ? (
                      <span className="text-sm text-red-700">
                        {fieldErrors.sharepointDriveId}
                      </span>
                    ) : null}
                  </label>
                </div>
              </div>
            ) : null}

            <FilterConfiguration key={apiUrl} onConfigChange={setFilterOverrides} />

            <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
              <button
                onClick={handleScan}
                disabled={!path || job?.status === "running"}
                className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {job?.status === "running" ? "Analizando…" : "Analizar"}
              </button>
            </div>
            {formError ? (
              <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
                {formError}
              </div>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm text-gray-700">
                <span>Modo de agrupación</span>
                <select
                  value={groupMode}
                  onChange={(e) => setGroupMode(e.target.value as GroupMode)}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="strict">Strict (solo directorio inmediato)</option>
                  <option value="extended">Extended (directorio + ancestros)</option>
                </select>
                <p className="text-xs text-gray-500">
                  {groupMode === "strict"
                    ? "El análisis agrupa cada archivo solo en su carpeta inmediata."
                    : "El análisis también agregará archivos a las carpetas ancestro del directorio."}
                </p>
              </label>
            </div>

            <div className="flex flex-wrap gap-5 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enablePii}
                  onChange={(e) => setEnablePii(e.target.checked)}
                  className="rounded"
                />
                Detección PII
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableEmbed}
                  onChange={(e) => setEnableEmbed(e.target.checked)}
                  className="rounded"
                />
                Vectorización
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableCluster}
                  onChange={(e) => setEnableCluster(e.target.checked)}
                  className="rounded"
                />
                Clustering
              </label>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Job status */}
        {job && <JobStatusCard job={job} />}

        {/* Results */}
        {report && (
          <div>
            {/* Tabs */}
            <div className="mb-4 flex gap-1 border-b border-gray-200">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`px-4 py-2 text-sm font-medium transition-colors ${
                    activeTab === t.id
                      ? "border-b-2 border-blue-600 text-blue-600"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {activeTab === "dashboard" && (
              <div className="space-y-6">
                {statistics && (
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {topStats.map((stat) => (
                      <div key={stat.label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-xs text-gray-500">{stat.label}</p>
                        <p className="mt-1 text-2xl font-bold text-gray-800">{stat.value}</p>
                      </div>
                    ))}
                  </div>
                )}
                <HealthReport
                  report={report}
                  onExecuteReorg={handleExecuteReorg}
                  isExecuting={isExecuting}
                />
                {statistics && (
                  <StatisticsCharts statistics={statistics} />
                )}
              </div>
            )}

            {activeTab === "clusters" && (
              <ClusterMap clusters={report.clusters} />
            )}

            {activeTab === "groups" && (
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900">
                      Análisis de Grupos de Directorio
                    </h2>
                    <p className="mt-2 text-sm text-gray-600 max-w-2xl">
                      Revisa los perfiles de carpetas que se generaron durante el análisis y compara grupos con una vista clara de salud y similitud.
                      El resultado se mostrará automáticamente cuando termine el job.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">
                      Grupos: {groupAnalysis?.group_count ?? "—"}
                    </span>
                    <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700">
                      Modo: {groupAnalysis?.groups?.[0]?.group_mode ?? groupMode}
                    </span>
                    <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-indigo-700">
                      Similitudes: {groupAnalysis?.group_similarities?.length ?? "—"}
                    </span>
                  </div>
                </div>

                <div className="mb-6 grid gap-4 sm:grid-cols-3">
                  <div className="rounded-2xl border border-gray-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Total de grupos</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">
                      {groupAnalysis?.group_count ?? "—"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-gray-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Grupos saludables</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">
                      {groupAnalysis ? groupAnalysis.groups.filter((g) => g.health_score >= 80).length : "—"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-gray-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Carga de análisis</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">
                      {isLoadingGroups ? "Cargando..." : groupAnalysis ? "Listo" : isLoadingSimilarities ? "Cargando similitudes..." : "Pendiente"}
                    </p>
                  </div>
                </div>

                {!groupAnalysis && !isLoadingGroups ? (
                  <div className="mb-6 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    El análisis de grupos todavía no está disponible. Espera a que el job termine o revisa que la vectorización y el agrupamiento estén activados en la configuración.
                  </div>
                ) : null}

                <GroupAnalysis
                  analysis={groupAnalysis}
                  isLoading={isLoadingGroups}
                  onLoadSimilarities={handleLoadGroupSimilarities}
                />
              </div>
            )}

            {activeTab === "entities" && (
              <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <div>
                  <h2 className="text-lg font-semibold text-gray-800">Entidades Nombradas (NER)</h2>
                  <p className="text-sm text-gray-500">Personas, organizaciones, lugares y más extraídos de los documentos</p>
                </div>
                {isLoadingContacts && (
                  <p className="text-sm text-gray-500 animate-pulse">Cargando entidades…</p>
                )}
                {!isLoadingContacts && !contacts && (
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    No hay datos de entidades disponibles. Asegúrate de que el job haya finalizado.
                  </div>
                )}
                {contacts && <NerReport report={contacts} />}
              </div>
            )}

            {activeTab === "audit" && (
              <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-800">Registro de Auditoría</h2>
                    <p className="text-sm text-gray-500">Historial inmutable de operaciones del sistema</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={async () => {
                        setIsLoadingAudit(true);
                        try {
                          const log = await getAuditLog({ limit: 200 });
                          setAuditLog(log);
                        } catch {
                          // ignore
                        } finally {
                          setIsLoadingAudit(false);
                        }
                      }}
                      disabled={isLoadingAudit}
                      className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {isLoadingAudit ? "Cargando…" : "Actualizar log"}
                    </button>
                    <button
                      onClick={async () => {
                        setIsPruning(true);
                        try {
                          const result = await pruneJobs();
                          alert(`${result.pruned} job(s) purgados según la política de retención.`);
                        } catch {
                          alert("Error al purgar jobs.");
                        } finally {
                          setIsPruning(false);
                        }
                      }}
                      disabled={isPruning}
                      className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {isPruning ? "Purgando…" : "Purgar jobs antiguos"}
                    </button>
                  </div>
                </div>

                {!auditLog && (
                  <div className="flex h-32 items-center justify-center text-gray-400 text-sm">
                    Haz clic en "Actualizar log" para cargar el registro de auditoría.
                  </div>
                )}

                {auditLog && (
                  <>
                    <p className="text-xs text-gray-500">
                      {auditLog.total} entradas en total · mostrando {auditLog.entries.length}
                    </p>
                    <div className="overflow-x-auto rounded-lg border border-gray-200">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left font-semibold text-gray-600">Timestamp</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-600">Operación</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-600">Recurso</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-600">Resultado</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-600">Detalles</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {auditLog.entries.map((entry: AuditEntry) => (
                            <tr key={entry.entry_id} className="hover:bg-gray-50">
                              <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{entry.timestamp}</td>
                              <td className="px-3 py-2 font-mono text-gray-800">{entry.operation}</td>
                              <td className="px-3 py-2 text-gray-600 truncate max-w-[200px]">
                                {entry.resource_id ? (
                                  <span title={entry.resource_id}>{entry.resource_id.slice(0, 8)}…</span>
                                ) : "—"}
                              </td>
                              <td className="px-3 py-2">
                                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                  entry.outcome === "success"
                                    ? "bg-green-100 text-green-700"
                                    : entry.outcome === "failure"
                                    ? "bg-red-100 text-red-700"
                                    : "bg-blue-100 text-blue-700"
                                }`}>
                                  {entry.outcome}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-gray-500 max-w-[300px] truncate">
                                {Object.entries(entry.details)
                                  .map(([k, v]) => `${k}: ${v}`)
                                  .join(" · ")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}

            {activeTab === "exploration" && exploration && (
              <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-800">Exploración del corpus</h2>
                    <p className="text-sm text-gray-500">
                      {isLoadingInsights ? "Actualizando métricas…" : "Carpetas dominantes, concentración y ruido semántico"}
                    </p>
                  </div>
                  <div className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">
                    Concentración: {Math.round(exploration.concentration_index * 100)}%
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    ["Total", exploration.total_files],
                    ["Únicos", exploration.unique_files],
                    ["Duplicados", exploration.duplicate_files],
                    ["PII", `${Math.round(exploration.pii_share * 100)}%`],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                      <p className="text-xs text-gray-500">{label}</p>
                      <p className="mt-1 text-2xl font-bold text-gray-800">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="grid gap-6 lg:grid-cols-2">
                  <div>
                    <h3 className="mb-3 font-semibold text-gray-800">Extensiones dominantes</h3>
                    <div className="space-y-2">
                      {exploration.top_extensions.map((item) => (
                        <div key={item.label} className="rounded-lg border border-gray-100 p-3">
                          <div className="flex items-center justify-between text-sm">
                            <span>{item.label}</span>
                            <span className="text-gray-500">{item.count}</span>
                          </div>
                          <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100">
                            <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.round(item.share * 100)}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3 className="mb-3 font-semibold text-gray-800">Directorios ruidosos</h3>
                    <div className="space-y-2">
                      {exploration.noisy_directories.map((item) => (
                        <div key={item.path} className="rounded-lg border border-gray-100 p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <span className="truncate font-medium text-gray-700">{item.path}</span>
                            <span className="text-gray-500">{item.count}</span>
                          </div>
                          <p className="mt-1 text-xs text-gray-500">
                            duplicados: {item.duplicate_count} · sin categoría: {item.unknown_count}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid gap-6 lg:grid-cols-2">
                  <div>
                    <h3 className="mb-3 font-semibold text-gray-800">Categorías dominantes</h3>
                    <div className="space-y-2">
                      {exploration.dominant_categories.map((item) => (
                        <div key={item.label} className="rounded-lg border border-gray-100 p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <span>{item.label}</span>
                            <span className="text-gray-500">{Math.round(item.share * 100)}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3 className="mb-3 font-semibold text-gray-800">Clusters dominantes</h3>
                    <div className="space-y-2">
                      {exploration.dominant_clusters.map((item) => (
                        <div key={item.label} className="rounded-lg border border-gray-100 p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <span>{item.label.replace(/_/g, " ")}</span>
                            <span className="text-gray-500">{item.document_count} docs</span>
                          </div>
                          <p className="mt-1 text-xs text-gray-500">
                            inconsistencias: {item.inconsistency_count} · {Math.round(item.share * 100)}%
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid gap-6 lg:grid-cols-2 mt-6">
                  <div>
                    <h3 className="mb-3 font-semibold text-gray-800">Heatmap temporal</h3>
                    <div className="space-y-2">
                      {exploration.temporal_heatmap.slice(0, 8).map((item) => (
                        <div key={item.label} className="rounded-lg border border-gray-100 p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <span>{item.label}</span>
                            <span className="text-gray-500">{item.count}</span>
                          </div>
                          <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100">
                            <div
                              className="h-full rounded-full bg-blue-500"
                              style={{ width: `${Math.round(item.share * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="lg:col-span-2">
                    <h3 className="mb-3 font-semibold text-gray-800">Grafo de relaciones</h3>
                    <RelationGraph graph={exploration.relation_graph} />
                  </div>
                </div>
              </div>
            )}

            {activeTab === "search" && (
              <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <div>
                  <h2 className="text-lg font-semibold text-gray-800">Búsqueda híbrida</h2>
                  <p className="text-sm text-gray-500">
                    Filtra por facetas o busca por contenido, usando ranking textual y semántico.
                  </p>
                </div>

                <div className="grid gap-4">
                  <input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="¿Qué estás buscando?"
                    className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <input
                      value={searchCategory}
                      onChange={(e) => setSearchCategory(e.target.value)}
                      placeholder="Categorías separadas por coma"
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
                    />
                    <input
                      value={searchExtension}
                      onChange={(e) => setSearchExtension(e.target.value)}
                      placeholder="Extensiones .pdf, .txt"
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
                    />
                    <input
                      value={searchDirectory}
                      onChange={(e) => setSearchDirectory(e.target.value)}
                      placeholder="Directorios separados por coma"
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
                    />
                    <select
                      value={searchScope}
                      onChange={(e) => setSearchScope(e.target.value as SearchScope)}
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
                    >
                      <option value="hybrid">Hybrid</option>
                      <option value="all">All</option>
                      <option value="documents">Documents</option>
                      <option value="chunks">Chunks</option>
                    </select>
                  </div>
                  <button
                    onClick={handleSearch}
                    disabled={isSearching}
                    className="w-fit rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {isSearching ? "Buscando…" : "Buscar"}
                  </button>
                </div>

                {searchResponse && (
                  <div className="space-y-6">
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="rounded-lg border border-gray-100 p-4">
                        <p className="text-xs text-gray-500">Resultados</p>
                        <p className="mt-1 text-2xl font-bold text-gray-800">{searchResponse.total_results}</p>
                      </div>
                      <div className="rounded-lg border border-gray-100 p-4">
                        <p className="text-xs text-gray-500">Facetas por categoría</p>
                        <p className="mt-1 text-2xl font-bold text-gray-800">{searchResponse.categories.length}</p>
                      </div>
                      <div className="rounded-lg border border-gray-100 p-4">
                        <p className="text-xs text-gray-500">Facetas por directorio</p>
                        <p className="mt-1 text-2xl font-bold text-gray-800">{searchResponse.directories.length}</p>
                      </div>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-3">
                      <div>
                        <h3 className="mb-2 font-semibold text-gray-800">Categorías</h3>
                        <div className="space-y-2">
                          {searchResponse.categories.map((facet) => (
                            <div key={facet.label} className="rounded-lg border border-gray-100 p-3 text-sm">
                              <div className="flex items-center justify-between">
                                <span>{facet.label}</span>
                                <span className="text-gray-500">{facet.count}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <h3 className="mb-2 font-semibold text-gray-800">Extensiones</h3>
                        <div className="space-y-2">
                          {searchResponse.extensions.map((facet) => (
                            <div key={facet.label} className="rounded-lg border border-gray-100 p-3 text-sm">
                              <div className="flex items-center justify-between">
                                <span>{facet.label}</span>
                                <span className="text-gray-500">{facet.count}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <h3 className="mb-2 font-semibold text-gray-800">Directorios</h3>
                        <div className="space-y-2">
                          {searchResponse.directories.map((facet) => (
                            <div key={facet.label} className="rounded-lg border border-gray-100 p-3 text-sm">
                              <div className="flex items-center justify-between">
                                <span className="truncate">{facet.label}</span>
                                <span className="text-gray-500">{facet.count}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      {searchResponse.results.map((result) => (
                        <div key={result.source_id} className="rounded-lg border border-gray-100 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <h3 className="font-medium text-gray-800">{result.title || result.path}</h3>
                            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                              {result.kind} · {Math.round(result.score * 100)}%
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-gray-500">{result.path}</p>
                          <p className="mt-2 text-sm text-gray-700">{result.snippet}</p>
                        </div>
                      ))}
                    </div>

                    <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm text-blue-800">
                      <p className="font-semibold">Sugerencias</p>
                      <ul className="mt-2 space-y-1">
                        {searchResponse.suggestions.map((item) => (
                          <li key={item}>• {item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "rag" && (
              <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <div>
                  <h2 className="text-lg font-semibold text-gray-800">Asistente RAG</h2>
                  <p className="text-sm text-gray-500">
                    Consulta el corpus con contexto recuperado y respuesta asistida por LLM.
                  </p>
                </div>

                <div className="space-y-4">
                  <textarea
                    value={ragQuery}
                    onChange={(e) => setRagQuery(e.target.value)}
                    placeholder="Escribe una pregunta sobre el corpus..."
                    className="min-h-28 w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <label className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={ragIncludeAnswer}
                      onChange={(e) => setRagIncludeAnswer(e.target.checked)}
                    />
                    Generar respuesta con Gemini
                  </label>
                  <button
                    onClick={handleRag}
                    disabled={isAsking || !ragQuery.trim()}
                    className="w-fit rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {isAsking ? "Consultando…" : "Consultar"}
                  </button>
                </div>

                {ragResponse && (
                  <div className="space-y-4">
                    <div className="rounded-lg border border-gray-100 p-4">
                      <h3 className="font-semibold text-gray-800">Respuesta</h3>
                      <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700">
                        {ragResponse.answer || "No se generó respuesta automática; revisa el contexto recuperado."}
                      </p>
                    </div>

                    <div className="rounded-lg border border-gray-100 p-4">
                      <h3 className="font-semibold text-gray-800">Contexto recuperado</h3>
                      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                        {ragResponse.context}
                      </pre>
                    </div>

                    <div className="space-y-2">
                      <h3 className="font-semibold text-gray-800">Fuentes</h3>
                      {ragResponse.sources.map((source) => (
                        <div key={source.source_id} className="rounded-lg border border-gray-100 p-4 text-sm">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-gray-800">{source.title || source.path || source.source_id}</span>
                            <span className="text-gray-500">{Math.round(source.score * 100)}%</span>
                          </div>
                          <p className="mt-1 text-xs text-gray-500">{source.path}</p>
                          <p className="mt-2 text-gray-700">{source.snippet}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
