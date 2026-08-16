/**
 * =============================================================================
 * File: ReportPreviewNavigation.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Sticky section navigation for CMP-25 report preview.
 * Responsibilities:
 *   - Jump to existing report sections; mark the active section
 * Dependencies:
 *   - comparison-report-preview nav model
 * Public Exports:
 *   - ReportPreviewNavigation
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Do not invent sections that are absent from the payload.
 * =============================================================================
 */

"use client";

import { cn } from "@/lib/utils";
import type { ReportNavSection } from "@/features/reports/comparison-report-preview";

type Props = {
  sections: ReportNavSection[];
  activeId: string;
  onSelect: (id: string) => void;
};

export function ReportPreviewNavigation({ sections, activeId, onSelect }: Props) {
  if (sections.length === 0) return null;

  return (
    <nav aria-label="Mục lục báo cáo" className="lg:sticky lg:top-0">
      <p className="mb-2 text-caption font-semibold uppercase tracking-wide text-tertiary">
        Mục lục
      </p>
      <ul className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
        {sections.map((section) => {
          const active = section.id === activeId;
          return (
            <li key={section.id}>
              <button
                type="button"
                onClick={() => onSelect(section.id)}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-caption font-medium",
                  active
                    ? "bg-elevated text-primary"
                    : "text-secondary hover:bg-elevated/70 hover:text-primary",
                )}
              >
                {section.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
