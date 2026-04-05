import { render, screen } from "@testing-library/react";
import GroupAnalysis from "@/components/GroupAnalysis";
import type { GroupAnalysisResult } from "@/lib/api";

const mockAnalysis: GroupAnalysisResult = {
  job_id: "job-1",
  group_count: 2,
  total_groups_analyzed: 2,
  groups: [
    {
      group_id: "group_001",
      job_id: "job-1",
      group_path: "/data/ventas",
      group_mode: "strict",
      created_at: "2026-04-05T00:00:00Z",
      features: {
        group_path: "/data/ventas",
        depth: 2,
        file_count: 8,
        unique_file_count: 8,
        duplicate_count: 0,
        category_distribution: { Factura_Proveedor: 5, Contrato: 3 },
        extension_distribution: { ".pdf": 5, ".xlsx": 3 },
        mime_distribution: { "application/pdf": 5, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 3 },
        semantic_dispersion: 0.12,
        dominant_category: "Factura_Proveedor",
        dominant_category_share: 0.625,
        pii_detection_count: 1,
        pii_share: 0.125,
        pii_risk_distribution: { rojo: 0, amarillo: 1, verde: 0 },
        uncategorised_count: 0,
        uncategorised_share: 0,
        duplicate_share: 0,
        fiscal_period_distribution: { "2026-01": 5, "2026-02": 3 },
        date_range_start: "2026-01-05",
        date_range_end: "2026-02-15",
      },
      inferred_purpose: "Primarily Factura_Proveedor (62%)",
      health_score: 84,
      health_factors: { coherence: 0.9, coverage: 1.0, quality: 0.8, risk_profile: 0.8 },
      alerts: [],
      recommendations: ["Mantener el orden por tipo de documento."],
      representative_docs: ["doc-1", "doc-2"],
    },
    {
      group_id: "group_002",
      job_id: "job-1",
      group_path: "/data/operaciones",
      group_mode: "strict",
      created_at: "2026-04-05T00:00:00Z",
      features: {
        group_path: "/data/operaciones",
        depth: 2,
        file_count: 6,
        unique_file_count: 6,
        duplicate_count: 0,
        category_distribution: { Orden_Trabajo: 4, Contrato: 2 },
        extension_distribution: { ".pdf": 4, ".docx": 2 },
        mime_distribution: { "application/pdf": 4, "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 2 },
        semantic_dispersion: 0.25,
        dominant_category: "Orden_Trabajo",
        dominant_category_share: 0.667,
        pii_detection_count: 0,
        pii_share: 0,
        pii_risk_distribution: { rojo: 0, amarillo: 0, verde: 0 },
        uncategorised_count: 0,
        uncategorised_share: 0,
        duplicate_share: 0,
        fiscal_period_distribution: { "2026-03": 6 },
        date_range_start: "2026-03-01",
        date_range_end: "2026-03-31",
      },
      inferred_purpose: "Primarily Orden_Trabajo (67%)",
      health_score: 92,
      health_factors: { coherence: 0.85, coverage: 1.0, quality: 0.9, risk_profile: 0.9 },
      alerts: [],
      recommendations: ["Revisar los documentos antes de consolidar."],
      representative_docs: ["doc-3"],
    },
  ],
  group_similarities: [
    {
      group_a_id: "group_001",
      group_b_id: "group_002",
      group_a_path: "/data/ventas",
      group_b_path: "/data/operaciones",
      semantic_similarity: 0.78,
      category_overlap: 0.25,
      operational_similarity: 0.80,
      composite_score: 0.62,
      similarity_level: "similar",
      interpretation: "Groups have similar operational patterns.",
    },
  ],
  analysis_timestamp: "2026-04-05T00:00:00Z",
};

describe("GroupAnalysis component", () => {
  it("muestra el modo de agrupación y el resumen de grupos", () => {
    render(<GroupAnalysis analysis={mockAnalysis} isLoading={false} />);

    expect(screen.getByText(/Modo de agrupación/i)).toBeInTheDocument();
    expect(screen.getByText(/Grupos detectados/i)).toBeInTheDocument();
    expect(screen.getByText("group_001")).toBeInTheDocument();
    expect(screen.getByText("group_002")).toBeInTheDocument();
    expect(screen.getByText(/Top 3 grupos similares/i)).toBeInTheDocument();
    expect(screen.getByText("Primarily Factura_Proveedor (62%)")).toBeInTheDocument();
  });

  it("muestra estado de carga cuando isLoading es true", () => {
    render(<GroupAnalysis analysis={null} isLoading={true} />);

    expect(screen.getByText(/Analizando grupos de directorios/i)).toBeInTheDocument();
  });
});
