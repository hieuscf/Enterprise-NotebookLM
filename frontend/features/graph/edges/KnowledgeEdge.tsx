/**
 * =============================================================================
 * File: KnowledgeEdge.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Thin curved relationship edges with optional labels / path highlight.
 * Responsibilities:
 *   - Smooth Bézier path with low default weight
 *   - Emphasize selected / path edges; fade unrelated
 * Dependencies:
 *   - @xyflow/react, graph-style
 * Public Exports:
 *   - KnowledgeEdge, KnowledgeEdgeData
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Labels appear only when edge is selected or hovered.
 * =============================================================================
 */

"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

import { relationLabel } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";

export type KnowledgeEdgeData = {
  relation: string;
  emphasis: "path" | "selected" | "dimmed" | "default";
  showLabel: boolean;
};

export type KnowledgeFlowEdge = Edge<KnowledgeEdgeData, "knowledge">;

export function KnowledgeEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  markerEnd,
}: EdgeProps<KnowledgeFlowEdge>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const emphasis = data?.emphasis ?? "default";
  const isPath = selected || emphasis === "path" || emphasis === "selected";
  const isDimmed = emphasis === "dimmed";
  const showLabel = Boolean(data?.showLabel) || isPath;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: isPath
            ? "var(--accent-secondary)"
            : "var(--border-strong)",
          strokeWidth: isPath ? 1.75 : 1,
          strokeDasharray: isPath ? "5 4" : undefined,
          opacity: isDimmed ? 0.18 : isPath ? 1 : 0.55,
          transition: "stroke 180ms ease, opacity 180ms ease, stroke-width 180ms ease",
        }}
      />
      {showLabel && data?.relation ? (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "nodrag nopan pointer-events-none absolute rounded-sm border border-border-default bg-surface px-1.5 py-0.5 text-[10px] font-medium text-secondary shadow-xs",
              isDimmed && "opacity-0",
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            {relationLabel(data.relation)}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
