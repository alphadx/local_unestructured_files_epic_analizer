"use client";

import { useEffect, useRef, useState } from "react";
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

  // Minimum bubble radius (px) at which a text label is rendered
  const MIN_LABEL_RADIUS = 30;
  // Maximum number of characters shown in a bubble label
  const MAX_LABEL_LENGTH = 16;

  useEffect(() => {
    if (!svgRef.current || clusters.length === 0) return;

    const width = svgRef.current.clientWidth || 700;
    const height = 500;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const data: d3.HierarchyNode<BubbleData> = d3.hierarchy<BubbleData>({
      id: "root",
      label: "root",
      value: 0,
      inconsistencies: 0,
      children: clusters.map((c) => ({
        id: c.cluster_id,
        label: c.label,
        value: c.document_count,
        inconsistencies: c.inconsistencies.length,
      })),
    }).sum((d) => d.value);

    const pack = d3.pack<BubbleData>().size([width, height]).padding(8);
    const root = pack(data);

    const colorScale = d3
      .scaleOrdinal<string>()
      .domain(clusters.map((c) => c.cluster_id))
      .range(d3.schemeTableau10);

    const g = svg.append("g");

    const node = g
      .selectAll("g")
      .data(root.leaves())
      .join("g")
      .attr("transform", (d) => `translate(${d.x},${d.y})`);

    node
      .append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", (d) => colorScale(d.data.id))
      .attr("fill-opacity", 0.85)
      .attr("stroke", (d) =>
        d.data.inconsistencies > 0 ? "#ef4444" : "transparent"
      )
      .attr("stroke-width", 2)
      .style("cursor", "pointer")
      .on("mouseover", (event, d) => {
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

    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.3em")
      .attr("font-size", (d) => Math.min(14, d.r / 3.5))
      .attr("fill", "white")
      .attr("pointer-events", "none")
      .text((d) =>
        d.r > MIN_LABEL_RADIUS
          ? d.data.label.replace(/_/g, " ").substring(0, MAX_LABEL_LENGTH)
          : ""
      );
  }, [clusters]);

  return (
    <div className="relative w-full rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">
        Mapa de Clusters Semánticos
      </h2>
      {clusters.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-gray-400">
          Sin datos de clusters
        </div>
      ) : (
        <>
          <svg ref={svgRef} className="w-full" style={{ height: 500 }} />
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
        </>
      )}
    </div>
  );
}
