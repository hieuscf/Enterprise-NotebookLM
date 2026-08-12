/**
 * =============================================================================
 * File: GraphStatusBar.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Subtle graph metadata strip — stats, legend, selected path hint.
 * Responsibilities:
 *   - Render entity/relationship counts without dashboard chrome
 *   - Compact legend for node types
 * Dependencies:
 *   - graph-style, types/knowledge-graph
 * Public Exports:
 *   - GraphStatusBar, GraphLegend
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Metadata tone — not a statistics dashboard.
 * =============================================================================
 */

"use client";

import { nodeTypeLabel, nodeTypeStyles } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type {
  KnowledgeGraphNodeType,
  KnowledgeGraphStats,
} from "@/types/knowledge-graph";

const LEGEND_TYPES: KnowledgeGraphNodeType[] = [
  "topic",
  "entity",
  "document",
  "concept",
];

export function GraphLegend({ className }: { className?: string }) {
  return (
    <ul
      className={cn("flex flex-wrap items-center gap-3", className)}
      aria-label="Chú giải đồ thị"
    >
      {LEGEND_TYPES.map((type) => {
        const styles = nodeTypeStyles[type];
        return (
          <li key={type} className="flex items-center gap-1.5 text-caption text-secondary">
            <span
              className={cn(
                "h-2.5 w-2.5 rounded-[3px] border bg-surface",
                styles.borderSelected,
              )}
              aria-hidden
            />
            {nodeTypeLabel(type)}
          </li>
        );
      })}
    </ul>
  );
}

type Props = {
  stats: KnowledgeGraphStats;
  selectedPathLabel?: string | null;
  dataSource?: "api" | "demo";
  className?: string;
};

export function GraphStatusBar({
  stats,
  selectedPathLabel,
  dataSource,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-t border-border-default bg-surface/90 px-4 py-2 text-caption text-secondary backdrop-blur-sm",
        className,
      )}
    >
      <p className="tabular-nums">
        <span className="text-primary">{stats.entities.toLocaleString()}</span>{" "}
        thực thể
        <span className="mx-2 text-tertiary">·</span>
        <span className="text-primary">
          {stats.relationships.toLocaleString()}
        </span>{" "}
        quan hệ
        <span className="mx-2 text-tertiary">·</span>
        <span className="text-primary">{stats.topics.toLocaleString()}</span>{" "}
        chủ đề
        <span className="mx-2 text-tertiary">·</span>
        <span className="text-primary">{stats.documents.toLocaleString()}</span>{" "}
        tài liệu
        {dataSource === "demo" ? (
          <>
            <span className="mx-2 text-tertiary">·</span>
            <span className="text-tertiary">Đồ thị demo</span>
          </>
        ) : null}
      </p>

      <div className="flex flex-wrap items-center gap-4">
        {selectedPathLabel ? (
          <p className="max-w-xs truncate text-tertiary">
            Đường dẫn · <span className="text-secondary">{selectedPathLabel}</span>
          </p>
        ) : null}
        <GraphLegend />
      </div>
    </div>
  );
}
