/**
 * =============================================================================
 * File: KnowledgeNode.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Editorial card node with clear hierarchy and selection states.
 * Responsibilities:
 *   - Render type-aware card with label, subtype, connection count
 *   - Reflect selected / neighbor / dimmed / search-match / root states
 * Dependencies:
 *   - @xyflow/react, graph-style, types/knowledge-graph
 * Public Exports:
 *   - KnowledgeNode, KnowledgeNodeData
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Root gets a filled badge; secondary nodes are smaller.
 * =============================================================================
 */

"use client";

import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import {
  nodeTypeLabel,
  nodeTypeStyles,
  type NodeProminence,
} from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type { KnowledgeGraphNodeType } from "@/types/knowledge-graph";

const HANDLE_CLASS =
  "!h-1.5 !w-1.5 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0";

export type KnowledgeNodeData = {
  label: string;
  nodeType: KnowledgeGraphNodeType;
  subtype?: string;
  connectionCount?: number;
  prominence: NodeProminence;
  emphasis: "selected" | "neighbor" | "match" | "dimmed" | "default";
};

export type KnowledgeFlowNode = Node<KnowledgeNodeData, "knowledge">;

export const KnowledgeNode = memo(function KnowledgeNode({
  data,
  selected,
}: NodeProps<KnowledgeFlowNode>) {
  const styles = nodeTypeStyles[data.nodeType];
  const emphasis = data.emphasis;
  const prominence = data.prominence ?? "primary";
  const isRoot = prominence === "root";
  const isActive =
    selected || emphasis === "selected" || emphasis === "neighbor" || isRoot;
  const isMatch = emphasis === "match";
  const isDimmed = emphasis === "dimmed";

  return (
    <div
      className={cn(
        "group relative rounded-xl border bg-surface shadow-xs transition-[opacity,box-shadow,border-color,transform] duration-200 ease-out",
        "motion-reduce:transition-none",
        prominence === "root" && "w-[200px] px-3.5 py-2.5",
        prominence === "primary" && "w-[168px] px-3 py-2",
        prominence === "secondary" && "w-[152px] px-2.5 py-1.5",
        styles.fill,
        isActive ? styles.borderSelected : styles.border,
        isRoot && "z-10 bg-gradient-to-b from-surface to-elevated/40 shadow-md ring-2 ring-accent-secondary/15",
        (emphasis === "selected" || emphasis === "neighbor") &&
          "shadow-sm -translate-y-0.5",
        isMatch && "ring-2 ring-accent-secondary/30",
        isDimmed && "opacity-[0.28]",
        "hover:shadow-md hover:-translate-y-0.5",
      )}
    >
      <Handle id="target-top" type="target" position={Position.Top} className={HANDLE_CLASS} />
      <Handle id="source-top" type="source" position={Position.Top} className={HANDLE_CLASS} />
      <Handle id="target-left" type="target" position={Position.Left} className={HANDLE_CLASS} />
      <Handle id="source-left" type="source" position={Position.Left} className={HANDLE_CLASS} />
      <Handle id="target-right" type="target" position={Position.Right} className={HANDLE_CLASS} />
      <Handle id="source-right" type="source" position={Position.Right} className={HANDLE_CLASS} />

      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider",
            styles.chip,
            isActive && "shadow-xs",
          )}
        >
          {nodeTypeLabel(data.nodeType)}
        </span>
        {typeof data.connectionCount === "number" ? (
          <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-elevated px-1 text-[9px] tabular-nums text-tertiary">
            {data.connectionCount}
          </span>
        ) : null}
      </div>

      <p
        className={cn(
          "mt-1 truncate text-center font-semibold leading-tight text-primary",
          isRoot ? "text-[15px]" : prominence === "secondary" ? "text-[12px]" : "text-[13px]",
        )}
        title={data.label}
      >
        {data.label}
      </p>

      {data.subtype ? (
        <p
          className={cn(
            "mt-1 truncate text-center text-[10px] text-tertiary",
            isRoot && "text-secondary",
          )}
        >
          {data.subtype}
        </p>
      ) : null}

      <Handle id="target-bottom" type="target" position={Position.Bottom} className={HANDLE_CLASS} />
      <Handle id="source-bottom" type="source" position={Position.Bottom} className={HANDLE_CLASS} />
    </div>
  );
});
