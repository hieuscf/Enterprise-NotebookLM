/**
 * =============================================================================
 * File: ViewerToolbar.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Compact attached toolbar — zoom, page nav, fit, find, file actions.
 * Responsibilities:
 *   - Group controls; icon + tooltip for density; page jump input
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - ViewerToolbar
 * Database/Table: N/A
 * Related Modules: DocumentViewer
 * Important Notes: Preserves zoom/download/print; adds page + in-doc search entry.
 * =============================================================================
 */

"use client";

import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Maximize,
  Minus,
  Plus,
  Printer,
  RefreshCw,
  RotateCw,
  Search,
} from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type Props = {
  scale: number;
  page: number;
  pageCount: number;
  searchOpen?: boolean;
  disabled?: boolean;
  variant?: "knowledge" | "original";
  sectionLabel?: string | null;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitWidth: () => void;
  onFitPage: () => void;
  onRotate: () => void;
  onRefresh?: () => void;
  onDownload: () => void;
  onOpenOriginal: () => void;
  onPrint?: () => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onJumpPage: (page: number) => void;
  onToggleSearch: () => void;
};

const iconBtn =
  "inline-flex h-8 w-8 items-center justify-center rounded-md text-secondary hover:bg-elevated hover:text-primary disabled:cursor-not-allowed disabled:opacity-40";

export function ViewerToolbar({
  scale,
  page,
  pageCount,
  searchOpen,
  disabled,
  variant = "original",
  sectionLabel = null,
  onZoomIn,
  onZoomOut,
  onFitWidth,
  onFitPage,
  onRotate,
  onRefresh,
  onDownload,
  onOpenOriginal,
  onPrint,
  onPrevPage,
  onNextPage,
  onJumpPage,
  onToggleSearch,
}: Props) {
  const [pageInput, setPageInput] = useState(String(page));
  const pdfControls = variant === "original";
  const pdfDisabled = !pdfControls || Boolean(disabled);

  useEffect(() => {
    setPageInput(String(page));
  }, [page]);

  function commitPage() {
    const n = Number.parseInt(pageInput, 10);
    if (Number.isFinite(n) && n >= 1 && n <= Math.max(1, pageCount)) {
      onJumpPage(n);
    } else {
      setPageInput(String(page));
    }
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1 rounded-md border border-border-default bg-surface/95 px-2 py-1.5 shadow-xs backdrop-blur-sm",
      )}
    >
      {pdfControls ? (
        <>
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          className={iconBtn}
          disabled={pdfDisabled}
          onClick={onZoomOut}
          aria-label="Zoom out"
          title="Zoom out (−)"
        >
          <Minus className="h-3.5 w-3.5" aria-hidden />
        </button>
        <span className="min-w-[3rem] text-center text-caption tabular-nums text-tertiary">
          {Math.round(scale * 100)}%
        </span>
        <button
          type="button"
          className={iconBtn}
          disabled={pdfDisabled}
          onClick={onZoomIn}
          aria-label="Zoom in"
          title="Zoom in (+)"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>

      <div className="mx-1 hidden h-5 w-px bg-border-default sm:block" />

      <div className="flex items-center gap-0.5">
        <button
          type="button"
          className={iconBtn}
          disabled={pdfDisabled || page <= 1}
          onClick={onPrevPage}
          aria-label="Previous page"
          title="Previous page (←)"
        >
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
        </button>
        <label className="sr-only" htmlFor="viewer-page-jump">
          Page number
        </label>
        <input
          id="viewer-page-jump"
          value={pageInput}
          disabled={pdfDisabled || pageCount < 1}
          onChange={(e) => setPageInput(e.target.value.replace(/[^\d]/g, ""))}
          onBlur={commitPage}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitPage();
            }
          }}
          className="h-7 w-10 rounded border border-border-default bg-base text-center text-caption tabular-nums text-primary outline-none focus:border-accent-primary"
        />
        <span className="text-caption tabular-nums text-tertiary">
          / {Math.max(pageCount, 1)}
        </span>
        <button
          type="button"
          className={iconBtn}
          disabled={pdfDisabled || page >= pageCount}
          onClick={onNextPage}
          aria-label="Next page"
          title="Next page (→)"
        >
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>

      <div className="mx-1 hidden h-5 w-px bg-border-default sm:block" />

      <button
        type="button"
        className={cn(iconBtn, "hidden sm:inline-flex")}
        disabled={pdfDisabled}
        onClick={onFitWidth}
        title="Fit width (F)"
        aria-label="Fit width"
      >
        <span className="px-1 text-[10px] font-semibold tracking-wide">WIDTH</span>
      </button>
      <button
        type="button"
        className={iconBtn}
        disabled={pdfDisabled}
        onClick={onFitPage}
        title="Fit page (0)"
        aria-label="Fit page"
      >
        <Maximize className="h-3.5 w-3.5" aria-hidden />
      </button>
      <button
        type="button"
        className={iconBtn}
        disabled={pdfDisabled}
        onClick={onRotate}
        title="Rotate"
        aria-label="Rotate"
      >
        <RotateCw className="h-3.5 w-3.5" aria-hidden />
      </button>
        </>
      ) : sectionLabel ? (
        <span className="max-w-[16rem] truncate px-1 text-caption text-tertiary" title={sectionLabel}>
          {sectionLabel}
        </span>
      ) : null}

      <button
        type="button"
        className={cn(iconBtn, searchOpen && "bg-accent-primary-soft text-accent-primary")}
        onClick={onToggleSearch}
        title="Search in document (/)"
        aria-label="Search in document"
      >
        <Search className="h-3.5 w-3.5" aria-hidden />
      </button>
      {onRefresh && pdfControls ? (
        <button
          type="button"
          className={iconBtn}
          disabled={pdfDisabled}
          onClick={onRefresh}
          title="Refresh"
          aria-label="Refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
        </button>
      ) : null}

      <div className="mx-1 hidden h-5 w-px bg-border-default sm:block" />

      <button
        type="button"
        className={iconBtn}
        onClick={onDownload}
        title="Download original"
        aria-label="Download original"
      >
        <Download className="h-3.5 w-3.5" aria-hidden />
      </button>
      <button
        type="button"
        className={iconBtn}
        onClick={onOpenOriginal}
        title="Open original"
        aria-label="Open original"
      >
        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
      </button>
      {onPrint ? (
        <button
          type="button"
          className={iconBtn}
          onClick={onPrint}
          title="Print"
          aria-label="Print"
        >
          <Printer className="h-3.5 w-3.5" aria-hidden />
        </button>
      ) : null}
    </div>
  );
}
