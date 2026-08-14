/**
 * =============================================================================
 * File: HighlightOverlay.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Draw chunk highlight overlay on a PDF page (bbox or approximate).
 * Responsibilities:
 *   - Absolute overlay with teal border + warm highlight; fade after ~7s
 * Public Exports:
 *   - HighlightOverlay
 * Important Notes: Coordinates are percentages of the rendered page box.
 * =============================================================================
 */

"use client";

import { cn } from "@/lib/utils";

export type HighlightRect = {
  /** 0–100 percentage of page width/height */
  left: number;
  top: number;
  width: number;
  height: number;
};

type Props = {
  rect: HighlightRect | null;
  active: boolean;
  settled: boolean;
};

export function HighlightOverlay({ rect, active, settled }: Props) {
  if (!rect) return null;
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute z-10 rounded-sm border-l-[3px] transition-opacity duration-500",
        active && "chunk-highlight-active opacity-100",
        settled && !active && "chunk-highlight-settled opacity-90",
      )}
      style={{
        left: `${rect.left}%`,
        top: `${rect.top}%`,
        width: `${rect.width}%`,
        height: `${rect.height}%`,
        borderColor: "var(--accent-tertiary, #0d9488)",
        backgroundColor: "color-mix(in srgb, var(--highlight-search) 55%, transparent)",
      }}
    />
  );
}

/** Convert layout bbox [x,y,w,h] in 0–1 or pixel space to page percentages. */
export function bboxToHighlightRect(
  bbox: number[] | null | undefined,
  pageWidth: number,
  pageHeight: number,
): HighlightRect | null {
  if (!bbox || bbox.length < 4 || pageWidth <= 0 || pageHeight <= 0) return null;
  const [x, y, w, h] = bbox;
  // Heuristic: values ≤ 1.5 → normalized; else pixel-like vs page size.
  const normalized = Math.max(x, y, w, h) <= 1.5;
  const left = normalized ? x * 100 : (x / pageWidth) * 100;
  const top = normalized ? y * 100 : (y / pageHeight) * 100;
  const width = normalized ? w * 100 : (w / pageWidth) * 100;
  const height = normalized ? h * 100 : (h / pageHeight) * 100;
  if (![left, top, width, height].every((n) => Number.isFinite(n))) return null;
  return {
    left: Math.max(0, Math.min(95, left)),
    top: Math.max(0, Math.min(95, top)),
    width: Math.max(4, Math.min(100 - left, width)),
    height: Math.max(3, Math.min(100 - top, height)),
  };
}

/** Approximate band — DEPRECATED for citations; kept for non-citation callers. */
export function approximatePageHighlight(): HighlightRect {
  return { left: 4, top: 8, width: 92, height: 18 };
}
