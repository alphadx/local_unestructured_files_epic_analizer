"use client";

import { useEffect, useRef, useState } from "react";
import type { JobProgress } from "@/lib/api";
import { getApiBase, getJobLogs } from "@/lib/api";

interface Props {
  job: JobProgress;
}

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

const statusLabels: Record<string, string> = {
  pending: "Pendiente",
  running: "Procesando…",
  completed: "Completado",
  failed: "Error",
};

export default function JobStatusCard({ job }: Props) {
  const pct =
    job.total_files > 0
      ? Math.round((job.processed_files / job.total_files) * 100)
      : 0;

  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const entries = await getJobLogs(job.job_id);
        setLogs(entries);
      } catch {
        // network blip – ignore
      }
    };

    const connectWebSocket = () => {
      const base = getApiBase();
      const url = new URL(base);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.pathname = `/api/jobs/${job.job_id}/logs/ws`;
      const socket = new WebSocket(url.toString());
      wsRef.current = socket;

      socket.addEventListener("message", (event) => {
        setLogs((prev) => [...prev, event.data]);
      });

      socket.addEventListener("close", () => {
        wsRef.current = null;
      });
    };

    if (job.status === "running") {
      connectWebSocket();
    } else if (job.status === "completed" || job.status === "failed") {
      fetchLogs();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [job.job_id, job.status]);

  // Auto-scroll log panel to the bottom as new entries arrive
  useEffect(() => {
    if (showLogs) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, showLogs]);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-xs text-gray-400">{job.job_id}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[job.status]}`}
        >
          {statusLabels[job.status]}
        </span>
      </div>

      <p className="mb-3 text-sm text-gray-600">{job.message}</p>

      {job.status === "running" && (
        <div className="mb-3">
          <div className="mb-1 flex justify-between text-xs text-gray-500">
            <span>
              {job.processed_files} / {job.total_files} archivos
            </span>
            <span>{pct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {job.status === "completed" && (
        <div className="flex items-center gap-2 text-sm text-green-600">
          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
          {job.total_files} archivos procesados
        </div>
      )}

      {job.status === "failed" && job.error && (
        <p className="text-sm text-red-500">{job.error}</p>
      )}

      {/* Live log panel */}
      {logs.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <button
            onClick={() => setShowLogs((v) => !v)}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            <span>{showLogs ? "▾" : "▸"}</span>
            <span>
              {showLogs ? "Ocultar logs" : `Ver logs (${logs.length} entradas)`}
            </span>
          </button>
          {showLogs && (
            <div className="mt-2 max-h-48 overflow-y-auto rounded-lg bg-gray-900 p-3 font-mono text-xs text-gray-300">
              {logs.map((line, i) => (
                <div key={i} className="leading-5 whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
