"use client";

import { useState } from "react";
import type { ContactRecord, ContactsReport, NamedEntityType } from "@/lib/api";

interface Props {
  report: ContactsReport;
}

const ENTITY_COLORS: Record<NamedEntityType, string> = {
  PERSON: "#3b82f6",
  ORGANIZATION: "#f97316",
  LOCATION: "#22c55e",
  EMAIL: "#a855f7",
  PHONE: "#06b6d4",
  RUT: "#eab308",
  DATE: "#ec4899",
  MONEY: "#10b981",
  OTHER: "#9ca3af",
};

const ENTITY_LABELS: Record<NamedEntityType, string> = {
  PERSON: "Personas",
  ORGANIZATION: "Organizaciones",
  LOCATION: "Lugares",
  EMAIL: "Emails",
  PHONE: "Teléfonos",
  RUT: "RUTs",
  DATE: "Fechas",
  MONEY: "Montos",
  OTHER: "Otros",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-lg bg-white p-4 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">{title}</h3>
      {children}
    </div>
  );
}

function HorizontalBar({
  label,
  value,
  max,
  color,
  badge,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
  badge?: string;
}) {
  const share = max > 0 ? value / max : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-40 truncate text-gray-600 text-right shrink-0" title={label}>
        {badge && (
          <span
            className="inline-block mr-1 px-1 rounded text-white text-[10px] font-bold"
            style={{ backgroundColor: color }}
          >
            {badge}
          </span>
        )}
        {label}
      </span>
      <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
        <div
          className="h-4 rounded-full transition-all"
          style={{ width: `${Math.round(share * 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-12 text-gray-500 text-right shrink-0">{value.toLocaleString()}</span>
    </div>
  );
}

export default function NerReport({ report }: Props) {
  const [filterType, setFilterType] = useState<NamedEntityType | "ALL">("ALL");

  // Count per entity type
  const countByType = report.contacts.reduce<Record<string, number>>((acc, c) => {
    acc[c.entity_type] = (acc[c.entity_type] ?? 0) + c.frequency;
    return acc;
  }, {});

  const maxTypeCount = Math.max(...Object.values(countByType), 1);

  // Filtered top-10
  const filtered: ContactRecord[] =
    filterType === "ALL"
      ? report.contacts
      : report.contacts.filter((c) => c.entity_type === filterType);

  const top10 = [...filtered].sort((a, b) => b.frequency - a.frequency).slice(0, 10);
  const maxFreq = top10.length > 0 ? top10[0].frequency : 1;

  const entityTypes = Object.keys(countByType) as NamedEntityType[];

  return (
    <div className="flex flex-col gap-4">
      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="border border-gray-200 rounded-lg bg-white p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Total entidades</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">
            {report.total_entities_found.toLocaleString()}
          </p>
        </div>
        <div className="border border-gray-200 rounded-lg bg-white p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Documentos analizados</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">
            {report.total_documents_analyzed.toLocaleString()}
          </p>
        </div>
        <div className="border border-gray-200 rounded-lg bg-white p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Tipos de entidad</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">{entityTypes.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Distribution by type */}
        <Card title="Distribución por tipo">
          {entityTypes.length === 0 ? (
            <p className="text-sm text-gray-400">Sin datos</p>
          ) : (
            <div className="flex flex-col gap-2">
              {entityTypes
                .sort((a, b) => (countByType[b] ?? 0) - (countByType[a] ?? 0))
                .map((type) => (
                  <HorizontalBar
                    key={type}
                    label={ENTITY_LABELS[type] ?? type}
                    value={countByType[type] ?? 0}
                    max={maxTypeCount}
                    color={ENTITY_COLORS[type] ?? "#9ca3af"}
                  />
                ))}
            </div>
          )}
        </Card>

        {/* Top 10 */}
        <Card title="Top 10 entidades más frecuentes">
          {/* Filter chips */}
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setFilterType("ALL")}
              className={`px-2 py-0.5 rounded-full text-xs font-medium border transition-colors ${
                filterType === "ALL"
                  ? "bg-gray-700 text-white border-gray-700"
                  : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
              }`}
            >
              Todos
            </button>
            {entityTypes.map((type) => (
              <button
                key={type}
                onClick={() => setFilterType(type)}
                className={`px-2 py-0.5 rounded-full text-xs font-medium border transition-colors ${
                  filterType === type
                    ? "text-white border-transparent"
                    : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
                }`}
                style={filterType === type ? { backgroundColor: ENTITY_COLORS[type] } : {}}
              >
                {ENTITY_LABELS[type] ?? type}
              </button>
            ))}
          </div>

          {top10.length === 0 ? (
            <p className="text-sm text-gray-400">Sin entidades para este filtro</p>
          ) : (
            <div className="flex flex-col gap-2 mt-1">
              {top10.map((c, i) => (
                <HorizontalBar
                  key={`${c.entity_type}-${c.value}-${i}`}
                  label={c.value}
                  value={c.frequency}
                  max={maxFreq}
                  color={ENTITY_COLORS[c.entity_type] ?? "#9ca3af"}
                  badge={ENTITY_LABELS[c.entity_type]?.slice(0, 3) ?? c.entity_type}
                />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
