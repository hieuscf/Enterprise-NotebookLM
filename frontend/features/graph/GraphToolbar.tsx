/**
 * =============================================================================
 * File: GraphToolbar.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Floating glass toolbar for graph view controls.
 * Responsibilities:
 *   - Zoom, fit, reset, labels, relations, layout mode, depth
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - GraphToolbar
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Buttons are icon-first with tooltips; active states use soft color.
 * =============================================================================
 */

"use client";

import {
  Focus,
  Layers3,
  Maximize2,
  Minus,
  Plus,
  RefreshCw,
  Tag,
  Waypoints,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { KnowledgeGraphLayoutMode } from "@/types/knowledge-graph";

type Props = {
  showLabels: boolean;
  showRelations: boolean;
  showAllEdges: boolean;
  hiddenEdgeCount: number;
  layoutMode: KnowledgeGraphLayoutMode;
  depth: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onCenterSelected: () => void;
  onResetLayout: () => void;
  onToggleLabels: () => void;
  onToggleRelations: () => void;
  onToggleAllEdges: () => void;
  onLayoutMode: (mode: KnowledgeGraphLayoutMode) => void;
  onDepth: (depth: number) => void;
  className?: string;
};

const LAYOUT_MODES: { id: KnowledgeGraphLayoutMode; label: string; short: string }[] = [
  { id: "structured", label: "Cấu trúc", short: "Cấu trúc" },
  { id: "focus", label: "Trọng tâm", short: "Tâm" },
  { id: "explore", label: "Tự do", short: "Tự do" },
];

function ToolButton({
  label,
  onClick,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-secondary transition-all hover:bg-elevated hover:text-primary",
        active && "bg-accent-secondary-soft text-accent-secondary",
      )}
    >
      {children}
    </button>
  );
}

function ToolbarDivider() {
  return <span className="mx-0.5 hidden h-4 w-px bg-border-default sm:block" aria-hidden />;
}

export function GraphToolbar({
  showLabels,
  showRelations,
  showAllEdges,
  hiddenEdgeCount,
  layoutMode,
  depth,
  onZoomIn,
  onZoomOut,
  onFit,
  onCenterSelected,
  onResetLayout,
  onToggleLabels,
  onToggleRelations,
  onToggleAllEdges,
  onLayoutMode,
  onDepth,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex max-w-[min(100vw-1.5rem,48rem)] flex-wrap items-center gap-1 rounded-xl border border-border-default bg-surface/90 p-1.5 shadow-md backdrop-blur-md",
        className,
      )}
      role="toolbar"
      aria-label="Điều khiển đồ thị"
    >
      <ToolButton label="Phóng to (+)" onClick={onZoomIn}>
        <Plus className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
      <ToolButton label="Thu nhỏ (−)" onClick={onZoomOut}>
        <Minus className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
      <ToolButton label="Vừa khung (0)" onClick={onFit}>
        <Maximize2 className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
      <ToolButton label="Căn giữa nút đã chọn" onClick={onCenterSelected}>
        <Focus className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
      <ToolButton label="Đặt lại bố cục" onClick={onResetLayout}>
        <RefreshCw className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>

      <ToolbarDivider />

      <ToolButton label="Bật/tắt nhãn quan hệ" onClick={onToggleLabels} active={showLabels}>
        <Tag className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
      <ToolButton label="Bật/tắt quan hệ" onClick={onToggleRelations} active={showRelations}>
        <Waypoints className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>

      {hiddenEdgeCount > 0 || showAllEdges ? (
        <button
          type="button"
          onClick={onToggleAllEdges}
          className={cn(
            "h-8 cursor-pointer rounded-md px-2.5 text-[11px] font-medium transition-all",
            showAllEdges
              ? "bg-accent-secondary-soft text-accent-secondary"
              : "text-secondary hover:bg-elevated hover:text-primary",
          )}
          aria-pressed={showAllEdges}
        >
          {showAllEdges ? "Thu gọn" : `+ ${hiddenEdgeCount} quan hệ`}
        </button>
      ) : null}

      <ToolbarDivider />

      <div
        className="hidden items-center gap-0.5 rounded-md border border-border-default bg-base p-0.5 sm:flex"
        role="group"
        aria-label="Kiểu bố cục"
      >
        <Layers3 className="ml-1.5 h-3 w-3 text-tertiary" aria-hidden />
        {LAYOUT_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            onClick={() => onLayoutMode(mode.id)}
            className={cn(
              "h-7 cursor-pointer rounded px-2 text-[11px] font-medium transition-all",
              layoutMode === mode.id
                ? "bg-accent-secondary-soft text-accent-secondary"
                : "text-secondary hover:bg-elevated hover:text-primary",
            )}
            aria-pressed={layoutMode === mode.id}
          >
            {mode.short}
          </button>
        ))}
      </div>

      <div
        className="flex items-center gap-0.5 rounded-md border border-border-default bg-base p-0.5"
        role="group"
        aria-label="Độ sâu"
      >
        {[1, 2, 3].map((hop) => (
          <button
            key={hop}
            type="button"
            onClick={() => onDepth(hop)}
            className={cn(
              "h-7 w-8 cursor-pointer rounded text-[11px] font-medium tabular-nums transition-all",
              depth === hop
                ? "bg-accent-secondary-soft text-accent-secondary"
                : "text-secondary hover:bg-elevated hover:text-primary",
            )}
            aria-pressed={depth === hop}
            aria-label={`Độ sâu ${hop} bước`}
          >
            {hop}
          </button>
        ))}
      </div>
    </div>
  );
}
