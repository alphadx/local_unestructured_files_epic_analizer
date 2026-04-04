"use client";

import type { DataHealthReport } from "@/lib/api";

interface Props {
  report: DataHealthReport;
  onExecuteReorg: () => void;
  isExecuting: boolean;
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <div className={`rounded-lg border-l-4 bg-white p-4 shadow-sm ${color}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-800">{value}</p>
    </div>
  );
}

export default function HealthReport({
  report,
  onExecuteReorg,
  isExecuting,
}: Props) {
  const dupPct =
    report.total_files > 0
      ? Math.round((report.duplicates / report.total_files) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Total archivos"
          value={report.total_files}
          color="border-blue-400"
        />
        <StatCard
          label={`Duplicados (${dupPct}%)`}
          value={report.duplicates}
          color="border-orange-400"
        />
        <StatCard
          label="Archivos con PII"
          value={report.pii_files}
          color="border-red-400"
        />
        <StatCard
          label="Sin categoría"
          value={report.uncategorised_files}
          color="border-gray-400"
        />
      </div>

      {/* Consistency errors */}
      {report.consistency_errors.length > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <h3 className="mb-2 font-semibold text-red-700">
            ⚠ Inconsistencias detectadas ({report.consistency_errors.length})
          </h3>
          <ul className="space-y-1 text-sm text-red-600">
            {report.consistency_errors.slice(0, 10).map((e, i) => (
              <li key={i}>• {e}</li>
            ))}
            {report.consistency_errors.length > 10 && (
              <li className="text-gray-500">
                … y {report.consistency_errors.length - 10} más
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Duplicate groups */}
      {report.duplicate_groups.length > 0 && (
        <div className="rounded-xl border border-orange-200 bg-orange-50 p-4">
          <h3 className="mb-2 font-semibold text-orange-700">
            📋 Grupos de duplicados ({report.duplicate_groups.length})
          </h3>
          <div className="space-y-2 text-sm">
            {report.duplicate_groups.slice(0, 5).map((g) => (
              <div key={g.sha256} className="rounded bg-white p-2">
                <p className="font-mono text-xs text-gray-400">{g.sha256.substring(0, 16)}…</p>
                {g.files.map((f) => (
                  <p key={f} className="truncate text-gray-600">
                    {f}
                  </p>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reorganisation plan */}
      {report.reorganisation_plan.length > 0 && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold text-blue-700">
              🗂 Plan de reorganización ({report.reorganisation_plan.length} archivos)
            </h3>
            <button
              onClick={onExecuteReorg}
              disabled={isExecuting}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isExecuting ? "Ejecutando…" : "Ejecutar Organización"}
            </button>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1 text-xs text-blue-800">
            {report.reorganisation_plan.slice(0, 20).map((p, i) => (
              <div key={i} className="flex items-center gap-1">
                <span className="truncate text-gray-500 w-1/2">{p.current_path}</span>
                <span className="text-blue-400">→</span>
                <span className="truncate w-1/2">{p.suggested_path}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
