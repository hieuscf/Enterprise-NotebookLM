/**
 * =============================================================================
 * File: GraphToolbar.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Compact floating canvas utilities for pan/zoom and label toggles.
 * Responsibilities:
 *   - Zoom / fit / center / reset / label visibility actions
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - GraphToolbar
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Refined utility strip — not a dashboard card.
 * =============================================================================
 */

"use client";

import {
  Focus,
  Maximize2,
  Minus,
  Plus,
  RefreshCw,
  Tag,
  Waypoints,
} from "lucide-react";

import { cn } from "@/lib/utils";

type Props = {
  showLabels: boolean;
  showRelations: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onCenterSelected: () => void;
  onResetLayout: () => void;
  onToggleLabels: () => void;
  onToggleRelations: () => void;
  className?: string;
};

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
        "flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-secondary transition-colors hover:bg-elevated hover:text-primary",
        active && "bg-accent-secondary-soft text-accent-secondary",
      )}
    >
      {children}
    </button>
  );
}

export function GraphToolbar({
  showLabels,
  showRelations,
  onZoomIn,
  onZoomOut,
  onFit,
  onCenterSelected,
  onResetLayout,
  onToggleLabels,
  onToggleRelations,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex items-center gap-0.5 rounded-md border border-border-default bg-surface/95 p-1 shadow-sm backdrop-blur-sm",
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
      <span className="mx-0.5 h-4 w-px bg-border-default" aria-hidden />
      <ToolButton
        label="Bật/tắt nhãn"
        onClick={onToggleLabels}
        active={showLabels}
      >
        <Tag className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
      <ToolButton
        label="Bật/tắt quan hệ"
        onClick={onToggleRelations}
        active={showRelations}
      >
        <Waypoints className="h-3.5 w-3.5" aria-hidden />
      </ToolButton>
    </div>
  );
}
