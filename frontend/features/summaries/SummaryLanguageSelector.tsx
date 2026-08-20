/**
 * =============================================================================
 * File: SummaryLanguageSelector.tsx
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Output-language selector for AI Summary generation (FR6).
 * Responsibilities:
 *   - Expose Tiếng Việt / English options as text (no flag-only UX)
 * Dependencies:
 *   - types/summaries TargetLanguage
 * Public Exports:
 *   - SummaryLanguageSelector, TARGET_LANGUAGE_OPTIONS, languageLabel
 * Database/Table: N/A
 * Related Modules: SummarySection
 * Important Notes: Changing language does not translate locally — parent re-requests.
 * =============================================================================
 */

"use client";

import { cn } from "@/lib/utils";
import type { TargetLanguage } from "@/types/summaries";

export const TARGET_LANGUAGE_OPTIONS: ReadonlyArray<{
  value: TargetLanguage;
  label: string;
}> = [
  { value: "vi", label: "Tiếng Việt" },
  { value: "en", label: "English" },
];

export function languageLabel(language: TargetLanguage): string {
  return TARGET_LANGUAGE_OPTIONS.find((o) => o.value === language)?.label ?? language;
}

type Props = {
  value: TargetLanguage;
  onChange: (language: TargetLanguage) => void;
  disabled?: boolean;
  id?: string;
};

export function SummaryLanguageSelector({
  value,
  onChange,
  disabled = false,
  id = "summary-output-language",
}: Props) {
  return (
    <label className="flex flex-wrap items-center gap-2 text-body-sm text-secondary">
      <span className="whitespace-nowrap">Ngôn ngữ đầu ra:</span>
      <select
        id={id}
        value={value}
        disabled={disabled}
        aria-label="Ngôn ngữ đầu ra của tóm tắt"
        onChange={(e) => onChange(e.target.value as TargetLanguage)}
        className={cn(
          "h-9 min-w-[9.5rem] rounded-md border border-border-default bg-surface px-2.5",
          "text-body-sm font-medium text-primary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        {TARGET_LANGUAGE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
