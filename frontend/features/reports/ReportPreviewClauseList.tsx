/**
 * =============================================================================
 * File: ReportPreviewClauseList.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Scan-friendly clause change cards for CMP-25.
 * Responsibilities:
 *   - Render backend clause summaries; open detail on select
 * Dependencies:
 *   - comparison-badges, comparison-summary display helpers
 * Public Exports:
 *   - ReportPreviewClauseList, ReportPreviewClauseCard
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Only render statuses supplied by the backend. Cards scan;
 *   full legal text lives in the detail panel.
 * =============================================================================
 */

"use client";

import { RiskBadge, StatusBadge } from "@/features/comparisons/comparison-badges";
import { displayClauseId } from "@/features/comparisons/comparison-summary";
import { emptyClauseMessage } from "@/features/reports/comparison-report-preview";
import { cn } from "@/lib/utils";
import type { ReportPreviewClauseSummary } from "@/types/reports";

type Kind = "changed" | "added" | "removed";

type ListProps = {
  id: string;
  title: string;
  kind: Kind;
  clauses: ReportPreviewClauseSummary[];
  selectedId: string | null;
  onSelect: (clauseId: string) => void;
};

export function ReportPreviewClauseList({
  id,
  title,
  kind,
  clauses,
  selectedId,
  onSelect,
}: ListProps) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-4">
      <h2 id={`${id}-heading`} className="text-h3 text-primary">
        {title}
      </h2>
      {clauses.length === 0 ? (
        <p className="mt-2 text-body-sm text-secondary">{emptyClauseMessage(kind)}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {clauses.map((clause, index) => {
            const clauseId = clause.clause_id ?? clause.display_id ?? `${kind}-${index}`;
            return (
              <li key={clauseId}>
                <ReportPreviewClauseCard
                  clause={clause}
                  selected={selectedId === clause.clause_id || selectedId === clause.display_id}
                  onSelect={() => onSelect(clause.clause_id ?? clause.display_id ?? clauseId)}
                />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

type CardProps = {
  clause: ReportPreviewClauseSummary;
  selected: boolean;
  onSelect: () => void;
};

export function ReportPreviewClauseCard({ clause, selected, onSelect }: CardProps) {
  const heading = clause.display_id || displayClauseId(clause.clause_id);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "w-full rounded-md border px-3 py-2.5 text-left",
        selected
          ? "border-accent-primary/40 bg-elevated"
          : "border-border-default hover:bg-elevated/70",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-body-sm font-semibold text-primary">{heading}</span>
        {clause.status ? <StatusBadge status={clause.status} /> : null}
        {clause.risk_level ? <RiskBadge level={clause.risk_level} /> : null}
        {clause.risk_category ? (
          <span className="text-caption text-tertiary">{clause.risk_category}</span>
        ) : null}
      </div>
      {clause.change ? (
        <p className="mt-1 text-body-sm text-secondary">{clause.change}</p>
      ) : null}
      <p className="mt-1 text-caption text-accent-primary">Xem chi tiết</p>
    </button>
  );
}
