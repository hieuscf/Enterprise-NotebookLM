/**
 * =============================================================================
 * File: ExtractionControls.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Segmented controls for extraction_type + output_format (FR7).
 * Responsibilities:
 *   - Keyboard-accessible type/format selection; Vietnamese labels
 * Dependencies:
 *   - extraction-format options
 * Public Exports:
 *   - ExtractionControls
 * Database/Table: N/A
 * Related Modules: ExtractionSection
 * Important Notes: Does not trigger POST — parent owns generation decisions.
 * =============================================================================
 */

"use client";

import {
  EXTRACTION_TYPE_OPTIONS,
  OUTPUT_FORMAT_OPTIONS,
} from "@/features/extractions/extraction-format";
import { cn } from "@/lib/utils";
import type { ExtractionOutputFormat, ExtractionType } from "@/types/extractions";

type Props = {
  extractionType: ExtractionType;
  outputFormat: ExtractionOutputFormat;
  onTypeChange: (type: ExtractionType) => void;
  onFormatChange: (format: ExtractionOutputFormat) => void;
  disabled?: boolean;
};

export function ExtractionControls({
  extractionType,
  outputFormat,
  onTypeChange,
  onFormatChange,
  disabled = false,
}: Props) {
  return (
    <div className="flex flex-col gap-3">
      <div
        role="tablist"
        aria-label="Loại trích xuất"
        className="flex flex-wrap gap-1 rounded-lg border border-border-default bg-elevated/40 p-1"
      >
        {EXTRACTION_TYPE_OPTIONS.map((opt) => {
          const selected = opt.type === extractionType;
          return (
            <button
              key={opt.type}
              type="button"
              role="tab"
              aria-selected={selected}
              disabled={disabled}
              onClick={() => onTypeChange(opt.type)}
              className={cn(
                "rounded-md px-3 py-1.5 text-body-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                selected
                  ? "bg-surface text-primary shadow-sm"
                  : "text-secondary hover:bg-surface/70 hover:text-primary",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      <div
        role="tablist"
        aria-label="Định dạng kết quả"
        className="flex flex-wrap gap-1 rounded-lg border border-border-default bg-elevated/40 p-1 self-start"
      >
        {OUTPUT_FORMAT_OPTIONS.map((opt) => {
          const selected = opt.format === outputFormat;
          return (
            <button
              key={opt.format}
              type="button"
              role="tab"
              aria-selected={selected}
              disabled={disabled}
              onClick={() => onFormatChange(opt.format)}
              className={cn(
                "rounded-md px-3 py-1.5 text-body-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                selected
                  ? "bg-surface text-primary shadow-sm"
                  : "text-secondary hover:bg-surface/70 hover:text-primary",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
