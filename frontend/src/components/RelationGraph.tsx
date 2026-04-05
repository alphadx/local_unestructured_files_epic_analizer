"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

interface RelationNode {
  id: string;
  label: string;
  kind: string;
  group?: string | null;
}

interface RelationEdge {
  source: string;
  target: string;
  relation_type: string;
  count: number;
}

interface RelationGraph {
  nodes: RelationNode[];
  edges: RelationEdge[];
  node_count: number;
  edge_count: number;
}

interface Props {
  graph: RelationGraph;
}

const KIND_COLOR: Record<string, string> = {
  document: "#3b82f6",
  work_order: "#f97316",
  tender: "#a855f7",
};

const KIND_LABEL: Record<string, string> = {
  document: "Documento",
  work_order: "Orden de Trabajo",
  tender: "Licitación",
};

const DEFAULT_COLOR = "#9ca3af";

function nodeColor(kind: string): string {
  return KIND_COLOR[kind] ?? DEFAULT_COLOR;
}

function nodeRadius(kind: string): number {
  return kind === "document" ? 8 : 12;
}

interface TooltipState {
  x: number;
  y: number;
  label: string;
  kind: string;
  group?: string | null;
}

// D3 simulation node type that extends RelationNode with positional fields
interface SimNode extends RelationNode, d3.SimulationNodeDatum {}

// D3 link type using SimNode references
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  relation_type: string;
  count: number;
}

export default function RelationGraph({ graph }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  useEffect(() => {
    if (!svgRef.current || graph.nodes.length === 0) return;

    const width = svgRef.current.clientWidth || 800;
    const height = 400;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    // Arrow marker definition
    svg
      .append("defs")
      .append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 20)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "#9ca3af");

    const nodes: SimNode[] = graph.nodes.map((n) => ({ ...n }));
    const nodeById = new Map(nodes.map((n) => [n.id, n]));

    const links: SimLink[] = graph.edges
      .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
      .map((e) => ({
        source: nodeById.get(e.source)!,
        target: nodeById.get(e.target)!,
        relation_type: e.relation_type,
        count: e.count,
      }));

    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(80)
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force(
        "collide",
        d3.forceCollide<SimNode>((d) => nodeRadius(d.kind) + 6)
      );

    const g = svg.append("g");

    // Zoom behaviour
    svg.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 4])
        .on("zoom", (event) => g.attr("transform", event.transform))
    );

    const link = g
      .append("g")
      .selectAll<SVGLineElement, SimLink>("line")
      .data(links)
      .join("line")
      .attr("stroke", "#9ca3af")
      .attr("stroke-width", (d) => Math.max(1, Math.sqrt(d.count)))
      .attr("marker-end", "url(#arrow)");

    const node = g
      .append("g")
      .selectAll<SVGCircleElement, SimNode>("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => nodeRadius(d.kind))
      .attr("fill", (d) => nodeColor(d.kind))
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5)
      .style("cursor", "pointer")
      .on("mouseover", (event, d) => {
        const rect = svgRef.current!.getBoundingClientRect();
        setTooltip({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top - 20,
          label: d.label,
          kind: d.kind,
          group: d.group,
        });
      })
      .on("mouseout", () => setTooltip(null))
      .call(
        d3
          .drag<SVGCircleElement, SimNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    const label = g
      .append("g")
      .selectAll<SVGTextElement, SimNode>("text")
      .data(nodes)
      .join("text")
      .attr("font-size", 10)
      .attr("fill", "#374151")
      .attr("pointer-events", "none")
      .attr("dx", (d) => nodeRadius(d.kind) + 3)
      .attr("dy", "0.35em")
      .text((d) => d.label.length > 20 ? d.label.substring(0, 20) + "…" : d.label);

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);

      node.attr("cx", (d) => d.x ?? 0).attr("cy", (d) => d.y ?? 0);
      label.attr("x", (d) => d.x ?? 0).attr("y", (d) => d.y ?? 0);
    });

    return () => {
      simulation.stop();
    };
  }, [graph]);

  const legendKinds = Object.entries(KIND_COLOR);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">
        Grafo de Relaciones entre Documentos
      </h2>

      {graph.nodes.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-gray-400">
          No se detectaron relaciones entre documentos.
        </div>
      ) : (
        <div className="relative">
          <svg
            ref={svgRef}
            className="w-full rounded-xl bg-slate-50"
            style={{ height: 400 }}
          />

          {tooltip && (
            <div
              className="pointer-events-none absolute z-10 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-lg"
              style={{ left: tooltip.x, top: tooltip.y }}
            >
              <p className="font-semibold text-gray-800">{tooltip.label}</p>
              <p className="text-gray-500">
                {KIND_LABEL[tooltip.kind] ?? tooltip.kind}
              </p>
              {tooltip.group && (
                <p className="text-gray-400 text-xs">Grupo: {tooltip.group}</p>
              )}
            </div>
          )}

          {/* Legend */}
          <div className="mt-3 flex flex-wrap gap-4">
            {legendKinds.map(([kind, color]) => (
              <div key={kind} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="text-xs text-gray-600">
                  {KIND_LABEL[kind] ?? kind}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
