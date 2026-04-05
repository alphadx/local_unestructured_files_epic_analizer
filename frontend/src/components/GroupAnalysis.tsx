"use client";

import { useState } from "react";
import type {
  GroupAnalysisResult,
  GroupProfile,
  GroupSimilarityResponse,
} from "@/lib/api";

interface GroupAnalysisProps {
  analysis: GroupAnalysisResult | null;
  isLoading?: boolean;
  onLoadSimilarities?: (groupId: string) => Promise<GroupSimilarityResponse>;
}

interface HealthScoreProps {
  score: number;
}

function HealthScoreIndicator({ score }: HealthScoreProps) {
  const getColor = (score: number) => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    if (score >= 40) return "text-orange-600";
    return "text-red-600";
  };

  const getText = (score: number) => {
    if (score >= 80) return "Excelente";
    if (score >= 60) return "Bueno";
    if (score >= 40) return "Regular";
    return "Bajo";
  };

  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center">
        <span className={`text-lg font-bold ${getColor(score)}`}>
          {Math.round(score)}
        </span>
      </div>
      <span className={`font-semibold ${getColor(score)}`}>{getText(score)}</span>
    </div>
  );
}

function GroupCard({ group }: { group: GroupProfile }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <h3 className="font-bold text-lg text-gray-900">{group.group_path}</h3>
          <p className="text-sm text-gray-600 mt-1">{group.inferred_purpose}</p>
        </div>
        <HealthScoreIndicator score={group.health_score} />
      </div>

      <div className="grid grid-cols-4 gap-2 text-sm mb-3">
        <div className="bg-blue-50 p-2 rounded">
          <span className="font-semibold text-blue-900">
            {group.features.file_count}
          </span>
          <div className="text-gray-600 text-xs">Archivos</div>
        </div>
        <div className="bg-purple-50 p-2 rounded">
          <span className="font-semibold text-purple-900">
            {group.features.unique_file_count}
          </span>
          <div className="text-gray-600 text-xs">Únicos</div>
        </div>
        <div className="bg-orange-50 p-2 rounded">
          <span className="font-semibold text-orange-900">
            {Math.round(group.features.pii_share * 100)}%
          </span>
          <div className="text-gray-600 text-xs">PII</div>
        </div>
        <div className="bg-red-50 p-2 rounded">
          <span className="font-semibold text-red-900">
            {Math.round(group.features.duplicate_share * 100)}%
          </span>
          <div className="text-gray-600 text-xs">Duplicados</div>
        </div>
      </div>

      {group.alerts.length > 0 && (
        <div className="mb-3 bg-red-50 border border-red-200 rounded p-2">
          <div className="text-sm font-semibold text-red-800 mb-1">Alertas:</div>
          <ul className="text-sm text-red-700">
            {group.alerts.slice(0, 3).map((alert, i) => (
              <li key={i} className="text-xs line-clamp-1">
                • {alert}
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-sm text-blue-600 hover:text-blue-800 font-medium"
      >
        {showDetails ? "Ocultar detalles" : "Ver detalles"}
      </button>

      {showDetails && (
        <div className="mt-3 border-t pt-3 space-y-2 text-sm">
          <div>
            <span className="font-semibold text-gray-700">Categoría dominante:</span>
            <span className="ml-2 text-gray-600">
              {group.features.dominant_category || "N/A"}
              {group.features.dominant_category_share > 0 && (
                <span className="text-gray-500">
                  {" "}
                  ({Math.round(group.features.dominant_category_share * 100)}%)
                </span>
              )}
            </span>
          </div>

          {group.features.date_range_start && (
            <div>
              <span className="font-semibold text-gray-700">Período:</span>
              <span className="ml-2 text-gray-600">
                {group.features.date_range_start} a{" "}
                {group.features.date_range_end || "actual"}
              </span>
            </div>
          )}

          <div>
            <span className="font-semibold text-gray-700">Profundidad:</span>
            <span className="ml-2 text-gray-600">{group.features.depth} niveles</span>
          </div>

          {group.recommendations.length > 0 && (
            <div>
              <span className="font-semibold text-gray-700 block mb-1">
                Recomendaciones:
              </span>
              <ul className="text-sm text-gray-600 list-disc list-inside">
                {group.recommendations.slice(0, 2).map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </div>
          )}

          {group.representative_docs.length > 0 && (
            <div>
              <span className="font-semibold text-gray-700 block">
                Documentos representativos:
              </span>
              <div className="text-xs text-gray-600 mt-1">
                {group.representative_docs.slice(0, 2).map((doc, i) => (
                  <div key={i} className="truncate">
                    {doc}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function GroupAnalysis({
  analysis,
  isLoading = false,
  onLoadSimilarities,
}: GroupAnalysisProps) {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [similarities, setSimilarities] = useState<GroupSimilarityResponse | null>(null);
  const [isLoadingSimilarities, setIsLoadingSimilarities] = useState(false);

  const handleLoadSimilarities = async (groupId: string) => {
    if (!onLoadSimilarities) return;

    setIsLoadingSimilarities(true);
    try {
      const result = await onLoadSimilarities(groupId);
      setSimilarities(result);
      setSelectedGroupId(groupId);
    } catch (err) {
      console.error("Error loading similarities:", err);
    } finally {
      setIsLoadingSimilarities(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-8">
        <div className="text-gray-600">Analizando grupos de directorios...</div>
      </div>
    );
  }

  if (!analysis || analysis.group_count === 0) {
    return (
      <div className="bg-gray-50 rounded-lg p-6 text-center">
        <p className="text-gray-600">Ningún análisis de grupos disponible</p>
      </div>
    );
  }

  const highRiskGroups = analysis.groups.filter((g) => g.health_score < 50);
  const healthyGroups = analysis.groups.filter((g) => g.health_score >= 80);

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-3xl font-bold text-blue-900">
            {analysis.group_count}
          </div>
          <div className="text-sm text-gray-600">Grupos detectados</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-3xl font-bold text-green-900">{healthyGroups.length}</div>
          <div className="text-sm text-gray-600">Grupos saludables</div>
        </div>
        <div className="bg-red-50 rounded-lg p-4">
          <div className="text-3xl font-bold text-red-900">{highRiskGroups.length}</div>
          <div className="text-sm text-gray-600">Grupos con riesgo</div>
        </div>
      </div>

      {/* Groups list */}
      <div>
        <h3 className="text-lg font-bold mb-3">Grupos de Directorio</h3>
        <div className="space-y-2">
          {analysis.groups.map((group) => (
            <div key={group.group_id}>
              <GroupCard group={group} />
              {onLoadSimilarities && (
                <button
                  onClick={() => handleLoadSimilarities(group.group_id)}
                  disabled={isLoadingSimilarities}
                  className="text-xs text-gray-600 hover:text-gray-900 ml-4 mb-2"
                >
                  {selectedGroupId === group.group_id && similarities
                    ? `${similarities.similar_groups.length} grupos similares`
                    : "Ver similares"}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Similarities */}
      {similarities && selectedGroupId === similarities.group_id && (
        <div className="bg-blue-50 rounded-lg p-4">
          <h3 className="text-lg font-bold mb-3">
            Grupos similares a{" "}
            <span className="text-blue-600">{similarities.group_path}</span>
          </h3>

          {similarities.similar_groups.length === 0 ? (
            <p className="text-gray-600 text-sm">
              No se encontraron grupos similares
            </p>
          ) : (
            <div className="space-y-2">
              {similarities.similar_groups.map((sim) => (
                <div
                  key={`${sim.group_a_id}-${sim.group_b_id}`}
                  className="bg-white rounded p-3 border border-blue-200"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="font-semibold text-gray-900">
                        {sim.group_b_path}
                      </div>
                      <div className="text-sm text-gray-600">
                        Nivel: <span className="font-medium">{sim.similarity_level}</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-bold text-blue-600">
                        {Math.round(sim.composite_score * 100)}%
                      </div>
                      <div className="text-xs text-gray-500">similitud</div>
                    </div>
                  </div>

                  {sim.interpretation && (
                    <p className="text-xs text-gray-600 line-clamp-2">
                      {sim.interpretation}
                    </p>
                  )}

                  <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
                    <div>
                      <span className="text-gray-500">Semántica:</span>
                      <span className="ml-1 font-semibold">
                        {Math.round(sim.semantic_similarity * 100)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Categorías:</span>
                      <span className="ml-1 font-semibold">
                        {Math.round(sim.category_overlap * 100)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Operativo:</span>
                      <span className="ml-1 font-semibold">
                        {Math.round(sim.operational_similarity * 100)}%
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
