/**
 * =============================================================================
 * File: GraphStatusBar.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Bottom metadata strip with a clean legend and focus summary.
 * Responsibilities:
 *   - Show graph counts, focus label, and node-type legend
 * Dependencies:
 *   - lucide-react, graph-style, types/knowledge-graph
 * Public Exports:
 *   - GraphStatusBar, GraphLegend
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Single-line row on desktop, wraps on small screens.
 * =============================================================================
 */

"use client";

import { Sparkles } from "lucide-react";

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
      className={cn("flex flex-wrap items-center gap-2", className)}
      aria-label="Chú giải đồ thị"
    >
      {LEGEND_TYPES.map((type) => {
        const styles = nodeTypeStyles[type];
        return (
          <li
            key={type}
            className="flex items-center gap-1.5 rounded-full border border-border-default bg-base px-2 py-0.5 text-caption text-secondary"
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full border",
                styles.borderSelected,
                styles.fill,
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
  viewSummary?: string | null;
  dataSource?: "api" | "demo";
  className?: string;
};

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <span className="inline-flex items-baseline gap-1 text-caption text-secondary">
      <span className="font-semibold tabular-nums text-primary">{value.toLocaleString()}</span>
      <span>{label}</span>
    </span>
  );
}

export function GraphStatusBar({
  stats,
  selectedPathLabel,
  viewSummary,
  dataSource,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-t border-border-default bg-surface/95 px-4 py-2.5 text-caption text-secondary backdrop-blur-md",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        <Stat value={stats.entities} label="thực thể" />
        <span className="hidden text-tertiary sm:inline" aria-hidden>
          ·
        </span>
        <Stat value={stats.relationships} label="quan hệ" />
        <span className="hidden text-tertiary sm:inline" aria-hidden>
          ·
        </span>
        <Stat value={stats.topics} label="chủ đề" />
        <span className="hidden text-tertiary sm:inline" aria-hidden>
          ·
        </span>
        <Stat value={stats.documents} label="tài liệu" />
        {dataSource === "demo" ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-accent-secondary/30 bg-accent-secondary-soft px-2 py-0.5 text-[10px] font-medium text-accent-secondary">
            <Sparkles className="h-3 w-3" aria-hidden />
            Demo
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {viewSummary ? (
          <p className="max-w-xs truncate rounded-md bg-base px-2 py-0.5 text-caption text-secondary">
            {viewSummary}
          </p>
        ) : null}
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
