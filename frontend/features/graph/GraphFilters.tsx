/**
 * =============================================================================
 * File: GraphFilters.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Quiet left control rail for view mode, filters, depth, and scope.
 * Responsibilities:
 *   - Graph overview / topics / entities / documents modes
 *   - Node type + relationship toggles, depth slider
 * Dependencies:
 *   - types/knowledge-graph, graph-style
 * Public Exports:
 *   - GraphFilters
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Keep chrome visually quiet — canvas stays dominant.
 * =============================================================================
 */

"use client";

import { relationLabel, nodeTypeLabel } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type {
  KnowledgeGraphFilters,
  KnowledgeGraphNodeType,
  KnowledgeGraphViewMode,
} from "@/types/knowledge-graph";

type Props = {
  filters: KnowledgeGraphFilters;
  onChange: (next: KnowledgeGraphFilters) => void;
  className?: string;
};

const VIEW_MODES: { id: KnowledgeGraphViewMode; label: string }[] = [
  { id: "overview", label: "Tổng quan" },
  { id: "topics", label: "Chủ đề" },
  { id: "entities", label: "Thực thể" },
  { id: "documents", label: "Tài liệu" },
];

const NODE_TYPES: KnowledgeGraphNodeType[] = [
  "topic",
  "entity",
  "document",
  "concept",
];

export function GraphFilters({ filters, onChange, className }: Props) {
  const relationKeys = Object.keys(filters.relations);

  return (
    <aside
      className={cn(
        "flex h-full w-full flex-col gap-5 overflow-y-auto border-r border-border-default bg-surface px-4 py-4",
        className,
      )}
      aria-label="Điều khiển đồ thị"
    >
      <section>
        <h2 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
          Đồ thị
        </h2>
        <ul className="mt-2 flex flex-col gap-0.5">
          {VIEW_MODES.map((mode) => (
            <li key={mode.id}>
              <button
                type="button"
                onClick={() => onChange({ ...filters, viewMode: mode.id })}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-body-sm transition-colors",
                  filters.viewMode === mode.id
                    ? "bg-accent-secondary-soft text-accent-secondary"
                    : "text-secondary hover:bg-elevated hover:text-primary",
                )}
              >
                <span
                  className={cn(
                    "h-2 w-2 rounded-full border",
                    filters.viewMode === mode.id
                      ? "border-accent-secondary bg-accent-secondary"
                      : "border-border-strong bg-transparent",
                  )}
                  aria-hidden
                />
                {mode.label}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
          Loại nút
        </h2>
        <ul className="mt-2 flex flex-col gap-1.5">
          {NODE_TYPES.map((type) => (
            <li key={type}>
              <label className="flex cursor-pointer items-center gap-2 text-body-sm text-secondary">
                <input
                  type="checkbox"
                  checked={filters.nodeTypes[type]}
                  onChange={(e) =>
                    onChange({
                      ...filters,
                      nodeTypes: {
                        ...filters.nodeTypes,
                        [type]: e.target.checked,
                      },
                    })
                  }
                  className="h-3.5 w-3.5 rounded border-border-strong text-accent-secondary focus:ring-accent-secondary"
                />
                {nodeTypeLabel(type)}
              </label>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
          Quan hệ
        </h2>
        <ul className="mt-2 flex flex-col gap-1.5">
          {relationKeys.map((key) => (
            <li key={key}>
              <label className="flex cursor-pointer items-center gap-2 text-body-sm text-secondary">
                <input
                  type="checkbox"
                  checked={filters.relations[key] ?? true}
                  onChange={(e) =>
                    onChange({
                      ...filters,
                      relations: {
                        ...filters.relations,
                        [key]: e.target.checked,
                      },
                    })
                  }
                  className="h-3.5 w-3.5 rounded border-border-strong text-accent-secondary focus:ring-accent-secondary"
                />
                {relationLabel(key)}
              </label>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
          Phạm vi
        </h2>
        <div className="mt-2 flex flex-col gap-1">
          {(
            [
              ["workspace", "Workspace"],
              ["all_documents", "Tất cả tài liệu"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => onChange({ ...filters, scope: id })}
              className={cn(
                "rounded-md px-2 py-1.5 text-left text-body-sm transition-colors",
                filters.scope === id
                  ? "bg-elevated text-primary"
                  : "text-secondary hover:bg-elevated/70",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
            Độ sâu
          </h2>
          <span className="text-caption tabular-nums text-secondary">
            {filters.depth}
          </span>
        </div>
        <input
          type="range"
          min={1}
          max={5}
          step={1}
          value={filters.depth}
          onChange={(e) =>
            onChange({ ...filters, depth: Number(e.target.value) })
          }
          className="mt-3 w-full accent-[var(--accent-secondary)]"
          aria-label="Độ sâu quan hệ"
        />
        <div className="mt-1 flex justify-between text-[10px] text-tertiary">
          <span>1</span>
          <span>5</span>
        </div>
      </section>
    </aside>
  );
}
