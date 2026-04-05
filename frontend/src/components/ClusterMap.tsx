"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Cluster } from "@/lib/api";
import * as d3 from "d3";

interface Props {
  clusters: Cluster[];
}

interface BubbleData {
  id: string;
  label: string;
  value: number;
  inconsistencies: number;
  family?: string;
  children?: BubbleData[];
}

export default function ClusterMap({ clusters }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    label: string;
    count: number;
    errors: number;
  } | null>(null);
  const [selectedFamily, setSelectedFamily] = useState<string | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);

  // Minimum bubble radius (px) at which a text label is rendered
  const MIN_LABEL_RADIUS = 30;
  // Maximum number of characters shown in a bubble label
  const MAX_LABEL_LENGTH = 16;

  const families = useMemo(() => {
    return clusters.reduce<Record<string, BubbleData[]>>((acc, cluster) => {
      const family = cluster.family_label || cluster.label;
      acc[family] = acc[family] || [];
      acc[family].push({
        id: cluster.cluster_id,
        label: cluster.label,
        value: cluster.document_count,
        inconsistencies: cluster.inconsistencies.length,
        family,
      });
      return acc;
    }, {});
  }, [clusters]);

  const familyList = useMemo(
    () =>
      Object.entries(families).map(([label, children]) => ({
        label,
        count: children.reduce((sum, child) => sum + child.value, 0),
        children,
      })),
    [families]
  );

  useEffect(() => {
    if (!svgRef.current || clusters.length === 0) return;

    const width = svgRef.current.clientWidth || 700;
    const height = 500;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const data: d3.HierarchyNode<BubbleData> = d3
      .hierarchy<BubbleData>({
        id: "root",
        label: "root",
        value: 0,
        inconsistencies: 0,
        children: Object.entries(families).map(([familyLabel, children]) => ({
          id: familyLabel,
          label: familyLabel,
          value: 0,
          inconsistencies: 0,
          children,
        })),
      })
      .sum((d) => d.value)
      .sort((a, b) => b.value - a.value);

    const data: d3.HierarchyNode<BubbleData> = d3
      .hierarchy<BubbleData>({
        id: "root",
        label: "root",
        value: 0,
        inconsistencies: 0,
        children: Object.entries(families).map(([familyLabel, children]) => ({
          id: familyLabel,
          label: familyLabel,
          value: 0,
          inconsistencies: 0,
          children,
        })),
      })
      .sum((d) => d.value)
      .sort((a, b) => b.value - a.value);

    const pack = d3.pack<BubbleData>().size([width, height]).padding(8);
    const root = pack(data);

    const colorScale = d3
      .scaleOrdinal<string>()
      .domain(Object.keys(families))
      .range(d3.schemeTableau10);

    const g = svg.append("g");
    const nodes = g.selectAll("g").data(root.descendants().slice(1)).join("g");

    nodes.attr("transform", (d) => `translate(${d.x},${d.y})`);

    nodes
      .append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", (d) =>
        d.children ? "transparent" : colorScale(d.data.family ?? d.parent?.data.label ?? d.data.label)
      )
      .attr("fill-opacity", (d) => {
        if (d.children) {
          return 0.08;
        }
        if (selectedFamily) {
          return d.data.family === selectedFamily ? 0.95 : 0.25;
        }
        return 0.85;
      })
      .attr("stroke", (d) =>
        d.children ? "#6b7280" : d.data.inconsistencies > 0 ? "#ef4444" : "#ffffff"
      )
      .attr("stroke-width", (d) => (d.children ? 2 : d.data.id === selectedCluster ? 3 : 1.5))
      .attr("stroke-dasharray", (d) => (d.children ? "4 3" : "0"))
      .style("cursor", (d) => (d.children ? "default" : "pointer"))
      .on("mouseover", (event, d) => {
        if (d.children) return;
        const rect = svgRef.current!.getBoundingClientRect();
        setTooltip({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top - 20,
          label: d.data.label,
          count: d.data.value,
          errors: d.data.inconsistencies,
        });
      })
      .on("mouseout", () => setTooltip(null));

    nodes
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.3em")
      .attr("font-size", (d) => {
        if (d.children) {
          return Math.min(16, d.r / 4);
        }
        return Math.min(12, d.r / 4);
      })
      .attr("fill", (d) => (d.children ? "#111827" : "white"))
      .attr("pointer-events", "none")
      .text((d) => {
        if (d.children) {
          return d.r > 30 ? d.data.label.replace(/_/g, " ").substring(0, MAX_LABEL_LENGTH) : "";
        }
        return d.r > MIN_LABEL_RADIUS
          ? d.data.label.replace(/_/g, " ").substring(0, MAX_LABEL_LENGTH)
          : "";
      });
  }, [clusters, families, selectedFamily, selectedCluster]);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">
        Mapa de Clusters Semánticos
      </h2>
      {clusters.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-gray-400">
          Sin datos de clusters
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <aside className="rounded-xl border border-gray-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">Familias</h3>
              <button
                onClick={() => {
                  setSelectedFamily(null);
                  setSelectedCluster(null);
                }}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Ver todas
              </button>
            </div>
            <div className="space-y-2">
              {familyList.map((family) => (
                <div
                  key={family.label}
                  className={`rounded-lg border p-3 ${
                    selectedFamily === family.label
                      ? "border-blue-600 bg-blue-50"
                      : "border-gray-200 bg-white"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedFamily(family.label);
                      setSelectedCluster(null);
                    }}
                    className="text-left text-sm font-semibold text-gray-800"
                  >
                    {family.label.replace(/_/g, " ")}
                  </button>
                  <p className="text-xs text-gray-500">{family.count} docs</p>
                  {selectedFamily === family.label && (
                    <div className="mt-2 space-y-1">
                      {family.children.map((child) => (
                        <button
                          key={child.id}
                          type="button"
                          onClick={() => setSelectedCluster(child.id)}
                          className={`block w-full rounded px-2 py-1 text-left text-xs ${
                            selectedCluster === child.id
                              ? "bg-blue-100 text-blue-800"
                              : "bg-slate-50 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          {child.label.replace(/_/g, " ")} · {child.value}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </aside>

          <div className="relative">
            <svg ref={svgRef} className="w-full rounded-xl bg-white" style={{ height: 500 }} />
            {tooltip && (
              <div
                className="pointer-events-none absolute z-10 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-lg"
                style={{ left: tooltip.x, top: tooltip.y }}
              >
                <p className="font-semibold">{tooltip.label.replace(/_/g, " ")}</p>
                <p className="text-gray-500">{tooltip.count} documentos</p>
                {tooltip.errors > 0 && (
                  <p className="text-red-500">{tooltip.errors} inconsistencias</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
