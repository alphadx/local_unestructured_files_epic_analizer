"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DataHealthReport, JobProgress } from "@/lib/api";
import {
  executeReorganization,
  getJob,
  getReport,
  startScan,
} from "@/lib/api";
import ClusterMap from "@/components/ClusterMap";
import HealthReport from "@/components/HealthReport";
import JobStatusCard from "@/components/JobStatusCard";

const POLL_INTERVAL_MS = 2_000;

type Tab = "dashboard" | "clusters" | "audit";

export default function Home() {
  const [path, setPath] = useState("/mnt/c/temp/fiasco_test");
  const [enablePii, setEnablePii] = useState(true);
  const [enableEmbed, setEnableEmbed] = useState(true);
  const [enableCluster, setEnableCluster] = useState(true);

  const [job, setJob] = useState<JobProgress | null>(null);
  const [report, setReport] = useState<DataHealthReport | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [error, setError] = useState<string | null>(null);

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

  const handleScan = async () => {
    setError(null);
    setReport(null);
    setJob(null);
    stopPolling();

    try {
      const newJob = await startScan({
        path,
        enable_pii_detection: enablePii,
        enable_embeddings: enableEmbed,
        enable_clustering: enableCluster,
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
          } else if (updated.status === "failed") {
            stopPolling();
          }
        } catch {
          // network blip – keep polling
        }
      }, POLL_INTERVAL_MS);
    } catch (err: unknown) {
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

  const tabs: { id: Tab; label: string }[] = [
    { id: "dashboard", label: "Dashboard" },
    { id: "clusters", label: "Mapa de Clusters" },
    { id: "audit", label: "Auditoría" },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto max-w-6xl">
          <h1 className="text-2xl font-bold text-gray-900">
            🧠 Analizador de Archivos Inteligente
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Gobernanza de Datos · Powered by Gemini
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8 space-y-6">
        {/* Scan form */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            Iniciar Análisis
          </h2>
          <div className="flex flex-col gap-4 sm:flex-row">
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/ruta/a/los/archivos"
              className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              onClick={handleScan}
              disabled={!path || (job?.status === "running")}
              className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {job?.status === "running" ? "Analizando…" : "Analizar"}
            </button>
          </div>

          <div className="mt-3 flex gap-5 text-sm">
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
              <HealthReport
                report={report}
                onExecuteReorg={handleExecuteReorg}
                isExecuting={isExecuting}
              />
            )}

            {activeTab === "clusters" && (
              <ClusterMap clusters={report.clusters} />
            )}

            {activeTab === "audit" && (
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <h2 className="mb-4 text-lg font-semibold text-gray-800">
                  Vista de Auditoría
                </h2>
                <div className="space-y-4">
                  {report.clusters.map((c) => (
                    <div
                      key={c.cluster_id}
                      className="rounded-lg border border-gray-100 p-4"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <h3 className="font-medium text-gray-700">
                          {c.label.replace(/_/g, " ")}
                        </h3>
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                          {c.document_count} docs
                        </span>
                      </div>
                      {c.inconsistencies.length > 0 && (
                        <ul className="mb-2 text-xs text-red-500">
                          {c.inconsistencies.map((e, i) => (
                            <li key={i}>⚠ {e}</li>
                          ))}
                        </ul>
                      )}
                      <ul className="space-y-0.5 text-xs text-gray-500">
                        {c.documents.slice(0, 5).map((d) => (
                          <li key={d.documento_id} className="truncate">
                            📄 {d.path}
                          </li>
                        ))}
                        {c.documents.length > 5 && (
                          <li className="text-gray-400">
                            … y {c.documents.length - 5} más
                          </li>
                        )}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
