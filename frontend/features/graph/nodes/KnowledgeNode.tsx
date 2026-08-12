/**
 * =============================================================================
 * File: KnowledgeNode.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Compact editorial card node for the Knowledge Graph canvas.
 * Responsibilities:
 *   - Render type-aware card with label, subtype, connection count
 *   - Reflect selected / neighbor / dimmed / search-match states
 * Dependencies:
 *   - @xyflow/react, graph-style, types/knowledge-graph
 * Public Exports:
 *   - KnowledgeNode, KnowledgeNodeData
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Scholarly Precision — thin border, slight elevation, no neon.
 * =============================================================================
 */

"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import {
  nodeTypeLabel,
  nodeTypeStyles,
} from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type { KnowledgeGraphNodeType } from "@/types/knowledge-graph";

export type KnowledgeNodeData = {
  label: string;
  nodeType: KnowledgeGraphNodeType;
  subtype?: string;
  connectionCount?: number;
  emphasis: "selected" | "neighbor" | "match" | "dimmed" | "default";
};

export type KnowledgeFlowNode = Node<KnowledgeNodeData, "knowledge">;

export function KnowledgeNode({ data, selected }: NodeProps<KnowledgeFlowNode>) {
  const styles = nodeTypeStyles[data.nodeType];
  const emphasis = data.emphasis;
  const isActive =
    selected || emphasis === "selected" || emphasis === "neighbor";
  const isMatch = emphasis === "match";
  const isDimmed = emphasis === "dimmed";

  return (
    <div
      className={cn(
        "group relative w-[168px] rounded-md border bg-surface px-3 py-2 shadow-xs transition-[opacity,transform,box-shadow,border-color] duration-200 ease-out",
        "motion-reduce:transition-none motion-reduce:transform-none",
        styles.fill,
        isActive ? styles.borderSelected : styles.border,
        isActive && "scale-[1.03] shadow-sm",
        isMatch && "ring-2 ring-accent-secondary/30",
        isDimmed && "opacity-[0.28]",
        "hover:shadow-sm",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-1.5 !w-1.5 !border-border-strong !bg-elevated"
      />

      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "text-[10px] font-semibold uppercase tracking-wider",
            styles.accent,
          )}
        >
          {nodeTypeLabel(data.nodeType)}
        </span>
        {typeof data.connectionCount === "number" ? (
          <span className="text-[10px] tabular-nums text-tertiary">
            {data.connectionCount}
          </span>
        ) : null}
      </div>

      <p className="mt-0.5 truncate text-center text-[13px] font-semibold leading-tight text-primary">
        {data.label}
      </p>

      <div
        className={cn(
          "mx-auto mt-1.5 h-px w-10 transition-colors",
          isActive ? "bg-accent-secondary/50" : "bg-border-default",
        )}
        aria-hidden
      />

      {data.subtype ? (
        <p className="mt-1 truncate text-center text-[10px] text-tertiary">
          {data.subtype}
        </p>
      ) : null}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !border-border-strong !bg-elevated"
      />
    </div>
  );
}
