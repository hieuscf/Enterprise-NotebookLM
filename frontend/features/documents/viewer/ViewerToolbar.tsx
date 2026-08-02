/**
 * =============================================================================
 * File: ViewerToolbar.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Zoom / fit / download / open-original controls for Original Viewer.
 * Public Exports:
 *   - ViewerToolbar
 * =============================================================================
 */

"use client";

import {
  Download,
  ExternalLink,
  Maximize,
  Minus,
  Plus,
  Printer,
  RotateCw,
} from "lucide-react";

import { cn } from "@/lib/utils";

type Props = {
  scale: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitWidth: () => void;
  onFitPage: () => void;
  onRotate: () => void;
  onDownload: () => void;
  onOpenOriginal: () => void;
  onPrint?: () => void;
  disabled?: boolean;
};

export function ViewerToolbar({
  scale,
  onZoomIn,
  onZoomOut,
  onFitWidth,
  onFitPage,
  onRotate,
  onDownload,
  onOpenOriginal,
  onPrint,
  disabled,
}: Props) {
  const btn =
    "inline-flex h-8 items-center gap-1.5 rounded-md border border-border-default px-2.5 text-caption font-medium text-secondary hover:bg-elevated hover:text-primary disabled:opacity-40";

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-default bg-elevated/50 px-3 py-2">
      <button type="button" className={btn} disabled={disabled} onClick={onZoomOut} aria-label="Zoom out">
        <Minus className="h-3.5 w-3.5" />
      </button>
      <span className="min-w-[3.5rem] text-center text-caption tabular-nums text-tertiary">
        {Math.round(scale * 100)}%
      </span>
      <button type="button" className={btn} disabled={disabled} onClick={onZoomIn} aria-label="Zoom in">
        <Plus className="h-3.5 w-3.5" />
      </button>
      <button type="button" className={btn} disabled={disabled} onClick={onFitWidth}>
        Fit width
      </button>
      <button type="button" className={cn(btn, "gap-1")} disabled={disabled} onClick={onFitPage}>
        <Maximize className="h-3.5 w-3.5" />
        Fit page
      </button>
      <button type="button" className={btn} disabled={disabled} onClick={onRotate} aria-label="Rotate">
        <RotateCw className="h-3.5 w-3.5" />
      </button>
      <div className="mx-1 h-5 w-px bg-border-default" />
      <button type="button" className={btn} onClick={onDownload}>
        <Download className="h-3.5 w-3.5" />
        Download Original
      </button>
      <button type="button" className={btn} onClick={onOpenOriginal}>
        <ExternalLink className="h-3.5 w-3.5" />
        Open Original
      </button>
      {onPrint ? (
        <button type="button" className={btn} disabled={disabled} onClick={onPrint}>
          <Printer className="h-3.5 w-3.5" />
          Print
        </button>
      ) : null}
    </div>
  );
}
