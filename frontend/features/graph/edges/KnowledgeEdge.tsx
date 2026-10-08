/**
 * =============================================================================
 * File: KnowledgeEdge.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Relationship edges with subtle arrows and on-demand labels.
 * Responsibilities:
 *   - Smooth or orthogonal path depending on layout mode
 *   - Emphasize selected / hovered / important edges; fade unrelated
 *   - Show relation label on hover / path / explicit toggle
 * Dependencies:
 *   - @xyflow/react, graph-style
 * Public Exports:
 *   - KnowledgeEdge, KnowledgeEdgeData
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Labels appear only when useful — not on every edge by default.
 * =============================================================================
 */

"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { useState } from "react";

import { relationLabel } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";

export type KnowledgeEdgeData = {
  relation: string;
  emphasis: "path" | "selected" | "dimmed" | "default";
  showLabel: boolean;
  /** Structured views use orthogonal steps; explore keeps curves. */
  routing?: "smoothstep" | "bezier";
  important?: boolean;
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
  interactionWidth = 24,
}: EdgeProps<KnowledgeFlowEdge>) {
  const [hovered, setHovered] = useState(false);
  const pathArgs = {
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  };
  const [edgePath, labelX, labelY] =
    data?.routing === "bezier"
      ? getBezierPath(pathArgs)
      : getSmoothStepPath({ ...pathArgs, borderRadius: 16, offset: 20 });

  const emphasis = data?.emphasis ?? "default";
  const isPath = selected || emphasis === "path" || emphasis === "selected";
  const isDimmed = emphasis === "dimmed";
  const showLabel = Boolean(data?.showLabel) || isPath || (hovered && !isDimmed);
  const isImportant = Boolean(data?.important);

  return (
    <>
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={interactionWidth}
        className="react-flow__edge-interaction"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke:
            isPath || hovered || isImportant
              ? "var(--accent-secondary)"
              : "var(--border-strong)",
          strokeWidth: isPath || hovered || isImportant ? 1.75 : 1,
          strokeDasharray: isPath ? "5 4" : undefined,
          opacity: isDimmed ? 0.15 : isPath || hovered || isImportant ? 1 : 0.48,
          transition:
            "stroke 180ms ease, opacity 180ms ease, stroke-width 180ms ease",
          pointerEvents: "none",
        }}
      />
      {showLabel && data?.relation ? (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "nodrag nopan pointer-events-none absolute rounded-full border border-border-default bg-surface px-2 py-0.5 text-[10px] font-medium text-secondary shadow-xs",
              (isPath || hovered) &&
                "border-accent-secondary/30 text-accent-secondary",
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
