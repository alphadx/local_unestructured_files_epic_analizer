"use client";

interface JobStatistics {
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
  cluster_summary: Array<{
    cluster_id: string;
    label: string;
    document_count: number;
    inconsistency_count: number;
  }>;
}

interface Props {
  statistics: JobStatistics;
}

const CATEGORY_COLORS: Record<string, string> = {
  Factura_Proveedor: "#22c55e",
  Orden_Trabajo: "#f97316",
  Licitacion: "#a855f7",
  Contrato: "#3b82f6",
  Informe: "#06b6d4",
  Nota_Credito: "#eab308",
  Imagen: "#ec4899",
  Desconocido: "#9ca3af",
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
  suffix,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
  suffix?: string;
}) {
  const share = max > 0 ? value / max : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-32 truncate text-gray-600 text-right shrink-0" title={label}>
        {label}
      </span>
      <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
        <div
          className="h-4 rounded-full"
          style={{ width: `${Math.round(share * 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-16 text-gray-500 shrink-0">
        {value.toLocaleString()}
        {suffix}
      </span>
    </div>
  );
}

function ExtensionChart({ data }: { data: Record<string, number> }) {
  const sorted = Object.entries(data)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8);
  const max = sorted[0]?.[1] ?? 1;
  return (
    <Card title="Extensiones de archivo">
      <div className="flex flex-col gap-2">
        {sorted.map(([ext, count]) => (
          <HorizontalBar key={ext} label={ext || "(sin ext)"} value={count} max={max} color="#3b82f6" />
        ))}
      </div>
    </Card>
  );
}

function CategoryChart({ data }: { data: Record<string, number> }) {
  const total = Object.values(data).reduce((s, v) => s + v, 0) || 1;
  const sorted = Object.entries(data).sort(([, a], [, b]) => b - a);
  const max = sorted[0]?.[1] ?? 1;
  return (
    <Card title="Distribución por categoría">
      <div className="flex flex-col gap-2">
        {sorted.map(([cat, count]) => {
          const color = CATEGORY_COLORS[cat] ?? "#9ca3af";
          const pct = Math.round((count / total) * 100);
          return (
            <div key={cat} className="flex items-center gap-2 text-xs">
              <span className="w-36 truncate text-gray-600 text-right shrink-0" title={cat}>
                {cat}
              </span>
              <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                <div
                  className="h-4 rounded-full"
                  style={{ width: `${Math.round((count / max) * 100)}%`, backgroundColor: color }}
                />
              </div>
              <span className="w-20 text-gray-500 shrink-0">
                {count.toLocaleString()} ({pct}%)
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

const PII_CONFIG: Array<{ key: string; label: string; bg: string; text: string; border: string }> = [
  { key: "verde", label: "Bajo riesgo", bg: "bg-green-50", text: "text-green-700", border: "border-green-300" },
  { key: "amarillo", label: "Riesgo medio", bg: "bg-yellow-50", text: "text-yellow-700", border: "border-yellow-300" },
  { key: "rojo", label: "Alto riesgo", bg: "bg-red-50", text: "text-red-700", border: "border-red-300" },
];

function PiiChart({ data }: { data: Record<string, number> }) {
  return (
    <Card title="Distribución de riesgo PII">
      <div className="flex gap-3">
        {PII_CONFIG.map(({ key, label, bg, text, border }) => (
          <div
            key={key}
            className={`flex-1 flex flex-col items-center gap-1 rounded-lg border p-3 ${bg} ${border}`}
          >
            <span className={`text-2xl font-bold ${text}`}>{(data[key] ?? 0).toLocaleString()}</span>
            <span className={`text-xs font-medium ${text}`}>{label}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function TemporalChart({ data }: { data: Record<string, number> }) {
  const sorted = Object.entries(data)
    .filter(([k]) => k !== "(desconocido)")
    .sort(([a], [b]) => a.localeCompare(b));
  const max = Math.max(...sorted.map(([, v]) => v), 1);
  return (
    <Card title="Distribución temporal">
      <div className="flex flex-col gap-2">
        {sorted.length === 0 && <p className="text-xs text-gray-400">Sin datos temporales.</p>}
        {sorted.map(([month, count]) => (
          <HorizontalBar key={month} label={month} value={count} max={max} color="#6366f1" />
        ))}
      </div>
    </Card>
  );
}

function KeywordCloud({ data }: { data: Record<string, number> }) {
  const top = Object.entries(data)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 20);
  return (
    <Card title="Palabras clave principales">
      <div className="flex flex-wrap gap-2">
        {top.map(([kw, count]) => (
          <span
            key={kw}
            className="inline-flex items-baseline gap-0.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
          >
            {kw}
            <sup className="text-gray-400 text-[9px] ml-0.5">{count}</sup>
          </span>
        ))}
        {top.length === 0 && <p className="text-xs text-gray-400">Sin palabras clave.</p>}
      </div>
    </Card>
  );
}

function SizeBucketChart({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort(([, a], [, b]) => b - a);
  const colors = [
    "bg-blue-50 border-blue-200 text-blue-700",
    "bg-indigo-50 border-indigo-200 text-indigo-700",
    "bg-violet-50 border-violet-200 text-violet-700",
    "bg-sky-50 border-sky-200 text-sky-700",
    "bg-teal-50 border-teal-200 text-teal-700",
  ];
  return (
    <Card title="Distribución por tamaño de archivo">
      <div className="flex flex-wrap gap-2">
        {entries.map(([bucket, count], i) => (
          <div
            key={bucket}
            className={`flex flex-col items-center rounded-lg border px-3 py-2 ${colors[i % colors.length]}`}
          >
            <span className="text-lg font-bold">{count.toLocaleString()}</span>
            <span className="text-xs font-medium mt-0.5">{bucket}</span>
          </div>
        ))}
        {entries.length === 0 && <p className="text-xs text-gray-400">Sin datos.</p>}
      </div>
    </Card>
  );
}

export default function StatisticsCharts({ statistics }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ExtensionChart data={statistics.extension_breakdown} />
        <CategoryChart data={statistics.category_distribution} />
        <PiiChart data={statistics.pii_risk_distribution} />
        <TemporalChart data={statistics.temporal_distribution} />
        <KeywordCloud data={statistics.keyword_distribution} />
        <SizeBucketChart data={statistics.size_bucket_distribution} />
      </div>
    </div>
  );
}
