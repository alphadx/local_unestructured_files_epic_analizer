"use client";

import { useEffect, useState } from "react";
import type { FilterConfiguration as FilterConfig } from "@/lib/api";
import { getFilterConfig } from "@/lib/api";

interface FilterConfigurationProps {
  onConfigChange?: (config: {
    ingestion_mode?: string;
    allowed_extensions?: string;
    denied_extensions?: string;
    allowed_mime_types?: string;
    denied_mime_types?: string;
  }) => void;
}

export default function FilterConfiguration({ onConfigChange }: FilterConfigurationProps) {
  const [systemConfig, setSystemConfig] = useState<FilterConfig | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Local overrides
  const [ingestionMode, setIngestionMode] = useState<string>("");
  const [allowedExtensions, setAllowedExtensions] = useState<string>("");
  const [deniedExtensions, setDeniedExtensions] = useState<string>("");
  const [allowedMimeTypes, setAllowedMimeTypes] = useState<string>("");
  const [deniedMimeTypes, setDeniedMimeTypes] = useState<string>("");

  useEffect(() => {
    const loadConfig = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const config = await getFilterConfig();
        setSystemConfig(config);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Error al cargar configuración";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    };

    loadConfig();
  }, []);

  const handleConfigChange = () => {
    const overrides: Parameters<NonNullable<typeof onConfigChange>>[0] = {};

    if (ingestionMode) overrides.ingestion_mode = ingestionMode;
    if (allowedExtensions) overrides.allowed_extensions = allowedExtensions;
    if (deniedExtensions) overrides.denied_extensions = deniedExtensions;
    if (allowedMimeTypes) overrides.allowed_mime_types = allowedMimeTypes;
    if (deniedMimeTypes) overrides.denied_mime_types = deniedMimeTypes;

    onConfigChange?.(overrides);
  };

  const resetOverrides = () => {
    setIngestionMode("");
    setAllowedExtensions("");
    setDeniedExtensions("");
    setAllowedMimeTypes("");
    setDeniedMimeTypes("");
    onConfigChange?.({});
  };

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <p className="text-sm text-gray-600">Cargando configuración de filtrado...</p>
      </div>
    );
  }

  if (error || !systemConfig) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
        <p className="text-sm text-yellow-900">
          {error || "No se pudo cargar la configuración de filtrado"}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-left font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
      >
        <div className="flex items-center justify-between">
          <span>⚙️ Configuración de Filtrado</span>
          <span className="text-gray-500">{isExpanded ? "▼" : "▶"}</span>
        </div>
      </button>

      {/* Expandable content */}
      {isExpanded && (
        <div className="space-y-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
          {/* Current system config info */}
          <div className="rounded-lg bg-blue-50 p-3">
            <p className="mb-2 text-sm font-medium text-blue-900">Configuración del Sistema</p>
            <dl className="space-y-1 text-xs text-blue-800">
              <div>
                <dt className="font-semibold">Modo de ingesta:</dt>
                <dd className="ml-4 font-mono">{systemConfig.ingestion_mode}</dd>
              </div>
              <div>
                <dt className="font-semibold">Extensiones permitidas:</dt>
                <dd className="ml-4 font-mono">
                  {systemConfig.allowed_extensions || "(vacío - todas permitidas en whitelist)"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold">Extensiones denegadas:</dt>
                <dd className="ml-4 font-mono">
                  {systemConfig.denied_extensions || "(vacío)"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold">MIME types permitidos:</dt>
                <dd className="ml-4 font-mono">
                  {systemConfig.allowed_mime_types || "(vacío)"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold">MIME types denegados:</dt>
                <dd className="ml-4 font-mono">
                  {systemConfig.denied_mime_types || "(vacío)"}
                </dd>
              </div>
            </dl>
          </div>

          {/* Override section */}
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-700">
              Sobrescribir para este Job (opcional)
            </p>

            <label className="flex flex-col gap-2 text-sm text-gray-700">
              <span>Modo de ingesta</span>
              <select
                value={ingestionMode}
                onChange={(e) => {
                  setIngestionMode(e.target.value);
                  handleConfigChange();
                }}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">Sin cambios (usar sistema)</option>
                <option value="whitelist">Whitelist (solo permitidos)</option>
                <option value="blacklist">Blacklist (todos excepto denegados)</option>
              </select>
            </label>

            <label className="flex flex-col gap-2 text-sm text-gray-700">
              <span>Extensiones permitidas (whitelist)</span>
              <input
                type="text"
                value={allowedExtensions}
                onChange={(e) => {
                  setAllowedExtensions(e.target.value);
                  handleConfigChange();
                }}
                placeholder=".txt,.pdf,.docx,.json,.csv"
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500">Separadas por comas. Ej: .txt,.pdf,.docx</p>
            </label>

            <label className="flex flex-col gap-2 text-sm text-gray-700">
              <span>Extensiones denegadas (blacklist)</span>
              <input
                type="text"
                value={deniedExtensions}
                onChange={(e) => {
                  setDeniedExtensions(e.target.value);
                  handleConfigChange();
                }}
                placeholder=".exe,.dll,.so,.bin"
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500">Separadas por comas. Ej: .exe,.dll,.bin</p>
            </label>

            <label className="flex flex-col gap-2 text-sm text-gray-700">
              <span>MIME types permitidos</span>
              <input
                type="text"
                value={allowedMimeTypes}
                onChange={(e) => {
                  setAllowedMimeTypes(e.target.value);
                  handleConfigChange();
                }}
                placeholder="text/,application/pdf,application/json"
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500">
                Prefijos separados por comas. Ej: text/,application/pdf
              </p>
            </label>

            <label className="flex flex-col gap-2 text-sm text-gray-700">
              <span>MIME types denegados</span>
              <input
                type="text"
                value={deniedMimeTypes}
                onChange={(e) => {
                  setDeniedMimeTypes(e.target.value);
                  handleConfigChange();
                }}
                placeholder="application/x-executable,application/x-sharedlib"
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500">
                Prefijos separados por comas. Ej: application/x-executable
              </p>
            </label>

            {/* Reset button */}
            {(ingestionMode || allowedExtensions || deniedExtensions || allowedMimeTypes || deniedMimeTypes) && (
              <button
                onClick={resetOverrides}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Limpiar personalizaciones
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
