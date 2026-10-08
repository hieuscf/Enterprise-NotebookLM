/**
 * =============================================================================
 * File: GraphChromeNodes.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Visualization-only frames for semantic groups and collapsed components.
 * Responsibilities:
 *   - Draw group columns, hidden-relationship chips, and disconnected-component cards
 *   - Stay out of the Knowledge Graph data model
 * Dependencies:
 *   - @xyflow/react, graph-style
 * Public Exports:
 *   - GroupFrameNode, OverflowNode, ComponentNode and their flow node types
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: These nodes are not persisted. Click handlers live on the canvas.
 * =============================================================================
 */

"use client";

import { memo } from "react";
import type { Node, NodeProps } from "@xyflow/react";

import { nodeTypeStyles } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type { KnowledgeGraphNodeType } from "@/types/knowledge-graph";

export type GroupNodeData = {
  groupKey: string;
  label: string;
  count: number;
  hiddenCount: number;
  collapsed: boolean;
  accentType: KnowledgeGraphNodeType;
  width: number;
  height: number;
};

export type OverflowNodeData = {
  groupKey: string;
  hiddenCount: number;
  width: number;
  height: number;
};

export type ComponentNodeData = {
  focusId: string;
  label: string;
  count: number;
  more: boolean;
  width: number;
  height: number;
};

export type GroupFlowNode = Node<GroupNodeData, "group">;
export type OverflowFlowNode = Node<OverflowNodeData, "overflow">;
export type ComponentFlowNode = Node<ComponentNodeData, "component">;

export const GroupFrameNode = memo(function GroupFrameNode({
  data,
}: NodeProps<GroupFlowNode>) {
  const styles = nodeTypeStyles[data.accentType];
  const shown = data.collapsed ? 0 : data.count - data.hiddenCount;
  return (
    <div
      style={{ width: data.width, height: data.height }}
      className={cn(
        "group rounded-2xl border border-dashed bg-gradient-to-b from-elevated/60 to-elevated/30",
        styles.border,
      )}
    >
      <div className="pointer-events-auto flex cursor-pointer items-center justify-between gap-2 px-3 pt-3">
        <span
          className={cn(
            "min-w-0 truncate rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider shadow-xs",
            styles.accent,
            styles.chip,
          )}
        >
          {data.label}
        </span>
        <span
          className={cn(
            "shrink-0 rounded-full bg-surface px-2 py-0.5 text-[10px] tabular-nums text-tertiary shadow-xs",
            data.collapsed && "text-accent-secondary",
          )}
        >
          {data.collapsed ? data.count : shown}
          {!data.collapsed && data.hiddenCount > 0 ? `/${data.count}` : ""}
        </span>
      </div>
    </div>
  );
});

export const OverflowNode = memo(function OverflowNode({
  data,
}: NodeProps<OverflowFlowNode>) {
  return (
    <div
      style={{ width: data.width, height: data.height }}
      className="flex cursor-pointer items-center justify-center gap-1 rounded-full border border-accent-secondary/30 bg-accent-secondary-soft text-[11px] font-semibold text-accent-secondary shadow-xs transition-all hover:bg-accent-secondary/15 hover:shadow-sm"
    >
      <span>+</span>
      <span className="tabular-nums">{data.hiddenCount}</span>
      <span>quan hệ</span>
    </div>
  );
});

export const ComponentNode = memo(function ComponentNode({
  data,
}: NodeProps<ComponentFlowNode>) {
  return (
    <div
      style={{ width: data.width, height: data.height }}
      className="flex cursor-pointer flex-col justify-center rounded-xl border border-border-default bg-surface px-3 shadow-xs transition-all hover:border-accent-secondary/40 hover:bg-elevated"
    >
      <span className="truncate text-[10px] font-semibold uppercase tracking-wider text-tertiary">
        {data.more ? "Thành phần khác" : "Không liên kết"}
      </span>
      <span className="truncate text-[13px] font-semibold text-primary">
        {data.label}
      </span>
      {data.more ? null : (
        <span className="text-[10px] tabular-nums text-tertiary">
          {data.count} nút
        </span>
      )}
    </div>
  );
});
