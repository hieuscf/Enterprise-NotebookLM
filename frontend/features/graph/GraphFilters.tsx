/**
 * =============================================================================
 * File: GraphFilters.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Polished left control rail for graph modes, filters, and depth.
 * Responsibilities:
 *   - View / layout modes, node type + relation toggles, depth slider
 *   - Clear visual sections without crowding the canvas
 * Dependencies:
 *   - lucide-react, types/knowledge-graph, graph-style
 * Public Exports:
 *   - GraphFilters
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Section headers use muted caps; active states use soft pills.
 * =============================================================================
 */

"use client";

import {
  Boxes,
  ChevronDown,
  ChevronRight,
  Eye,
  FileText,
  GitBranch,
  Layers3,
  Lightbulb,
  Maximize2,
  Network,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { useState } from "react";

import { relationLabel, nodeTypeLabel } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type {
  KnowledgeGraphFilters,
  KnowledgeGraphLayoutMode,
  KnowledgeGraphNodeType,
  KnowledgeGraphViewMode,
} from "@/types/knowledge-graph";

type Props = {
  filters: KnowledgeGraphFilters;
  onChange: (next: KnowledgeGraphFilters) => void;
  className?: string;
};

const VIEW_MODES: { id: KnowledgeGraphViewMode; label: string; icon: React.ReactNode }[] = [
  { id: "overview", label: "Tổng quan", icon: <Network className="h-3.5 w-3.5" aria-hidden /> },
  { id: "topics", label: "Chủ đề", icon: <Lightbulb className="h-3.5 w-3.5" aria-hidden /> },
  { id: "entities", label: "Thực thể", icon: <Boxes className="h-3.5 w-3.5" aria-hidden /> },
  { id: "documents", label: "Tài liệu", icon: <FileText className="h-3.5 w-3.5" aria-hidden /> },
];

const LAYOUT_MODES: { id: KnowledgeGraphLayoutMode; label: string; icon: React.ReactNode }[] = [
  { id: "structured", label: "Cấu trúc", icon: <Layers3 className="h-3.5 w-3.5" aria-hidden /> },
  { id: "focus", label: "Trọng tâm", icon: <Maximize2 className="h-3.5 w-3.5" aria-hidden /> },
  { id: "explore", label: "Tự do", icon: <GitBranch className="h-3.5 w-3.5" aria-hidden /> },
];

const NODE_TYPES: { id: KnowledgeGraphNodeType; icon: React.ReactNode }[] = [
  { id: "topic", icon: <Lightbulb className="h-3.5 w-3.5" aria-hidden /> },
  { id: "entity", icon: <Users className="h-3.5 w-3.5" aria-hidden /> },
  { id: "document", icon: <FileText className="h-3.5 w-3.5" aria-hidden /> },
  { id: "concept", icon: <Eye className="h-3.5 w-3.5" aria-hidden /> },
];

function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="rounded-lg border border-border-default bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-caption font-semibold uppercase tracking-wider text-tertiary hover:text-secondary"
      >
        {title}
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" aria-hidden />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        )}
      </button>
      {open ? <div className="border-t border-border-default px-3 py-3">{children}</div> : null}
    </section>
  );
}

function ModePill<T extends string>({
  current,
  value,
  label,
  icon,
  onClick,
}: {
  current: T;
  value: T;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  const active = current === value;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-left text-body-sm transition-all",
        active
          ? "border-accent-secondary/30 bg-accent-secondary-soft text-accent-secondary shadow-xs"
          : "border-border-default bg-base text-secondary hover:border-border-strong hover:bg-elevated hover:text-primary",
      )}
    >
      <span className={cn("shrink-0", active ? "text-accent-secondary" : "text-tertiary")}>
        {icon}
      </span>
      {label}
    </button>
  );
}

function ToggleChip({
  label,
  icon,
  checked,
  onChange,
}: {
  label: string;
  icon: React.ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-body-sm transition-all",
        checked
          ? "border-accent-secondary/30 bg-accent-secondary-soft text-accent-secondary"
          : "border-border-default bg-base text-secondary hover:border-border-strong hover:bg-elevated hover:text-primary",
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
      <span className={cn("shrink-0", checked ? "text-accent-secondary" : "text-tertiary")}>
        {icon}
      </span>
      <span className="min-w-0 truncate">{label}</span>
    </label>
  );
}

export function GraphFilters({ filters, onChange, className }: Props) {
  const relationKeys = Object.keys(filters.relations);

  return (
    <aside
      className={cn(
        "flex h-full w-full flex-col gap-3 overflow-y-auto border-r border-border-default bg-elevated/30 px-3 py-3",
        className,
      )}
      aria-label="Điều khiển đồ thị"
    >
      <div className="flex items-center gap-2 px-1 pt-1">
        <SlidersHorizontal className="h-4 w-4 text-accent-secondary" aria-hidden />
        <h2 className="text-body-sm font-semibold text-primary">Điều khiển</h2>
      </div>

      <Section title="Đồ thị" defaultOpen>
        <div className="grid grid-cols-2 gap-2">
          {VIEW_MODES.map((mode) => (
            <ModePill
              key={mode.id}
              current={filters.viewMode}
              value={mode.id}
              label={mode.label}
              icon={mode.icon}
              onClick={() => onChange({ ...filters, viewMode: mode.id })}
            />
          ))}
        </div>
      </Section>

      <Section title="Bố cục" defaultOpen>
        <div className="grid grid-cols-1 gap-2">
          {LAYOUT_MODES.map((mode) => (
            <ModePill
              key={mode.id}
              current={filters.layoutMode}
              value={mode.id}
              label={mode.label}
              icon={mode.icon}
              onClick={() => onChange({ ...filters, layoutMode: mode.id })}
            />
          ))}
        </div>
      </Section>

      <Section title="Loại nút" defaultOpen>
        <div className="grid grid-cols-1 gap-2">
          {NODE_TYPES.map((type) => (
            <ToggleChip
              key={type.id}
              label={nodeTypeLabel(type.id)}
              icon={type.icon}
              checked={filters.nodeTypes[type.id]}
              onChange={(checked) =>
                onChange({
                  ...filters,
                  nodeTypes: { ...filters.nodeTypes, [type.id]: checked },
                })
              }
            />
          ))}
        </div>
      </Section>

      <Section title="Quan hệ" defaultOpen={false}>
        <div className="flex flex-col gap-1.5">
          {relationKeys.map((key) => (
            <label
              key={key}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-body-sm text-secondary transition-colors hover:bg-elevated"
            >
              <input
                type="checkbox"
                checked={filters.relations[key] ?? true}
                onChange={(e) =>
                  onChange({
                    ...filters,
                    relations: { ...filters.relations, [key]: e.target.checked },
                  })
                }
                className="h-3.5 w-3.5 rounded border-border-strong text-accent-secondary focus:ring-accent-secondary"
              />
              {relationLabel(key)}
            </label>
          ))}
        </div>
      </Section>

      <Section title="Phạm vi" defaultOpen={false}>
        <div className="flex flex-col gap-1">
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
                  ? "bg-accent-secondary-soft text-accent-secondary"
                  : "text-secondary hover:bg-elevated hover:text-primary",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Độ sâu" defaultOpen>
        <div className="flex items-center gap-3">
          {[1, 2, 3].map((hop) => (
            <button
              key={hop}
              type="button"
              onClick={() => onChange({ ...filters, depth: hop })}
              className={cn(
                "h-8 w-10 cursor-pointer rounded-md text-body-sm font-medium tabular-nums transition-all",
                filters.depth === hop
                  ? "bg-accent-secondary-soft text-accent-secondary shadow-xs"
                  : "border border-border-default bg-base text-secondary hover:border-border-strong hover:bg-elevated hover:text-primary",
              )}
              aria-pressed={filters.depth === hop}
              aria-label={`Độ sâu ${hop} bước`}
            >
              {hop}
            </button>
          ))}
          <span className="text-caption text-tertiary">bước</span>
        </div>
      </Section>
    </aside>
  );
}
