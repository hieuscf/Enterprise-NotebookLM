/**
 * =============================================================================
 * File: SummaryStyleSelector.tsx
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Four-style segmented control for AI Summary (FR6).
 * Responsibilities:
 *   - Keyboard-accessible style selection; Vietnamese labels
 * Dependencies:
 *   - summary-format SUMMARY_STYLE_OPTIONS
 * Public Exports:
 *   - SummaryStyleSelector
 * Database/Table: N/A
 * Related Modules: SummarySection
 * Important Notes: Does not trigger POST — parent owns generation decisions.
 * =============================================================================
 */

"use client";

import { SUMMARY_STYLE_OPTIONS } from "@/features/summaries/summary-format";
import { cn } from "@/lib/utils";
import type { SummaryStyle } from "@/types/summaries";

type Props = {
  value: SummaryStyle;
  onChange: (style: SummaryStyle) => void;
  disabled?: boolean;
};

export function SummaryStyleSelector({ value, onChange, disabled = false }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Kiểu tóm tắt"
      className="flex flex-wrap gap-1 rounded-lg border border-border-default bg-elevated/40 p-1"
    >
      {SUMMARY_STYLE_OPTIONS.map((opt) => {
        const selected = opt.style === value;
        return (
          <button
            key={opt.style}
            type="button"
            role="tab"
            aria-selected={selected}
            disabled={disabled}
            onClick={() => onChange(opt.style)}
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
  );
}
