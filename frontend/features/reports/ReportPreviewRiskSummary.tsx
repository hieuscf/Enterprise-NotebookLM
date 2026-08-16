/**
 * =============================================================================
 * File: ReportPreviewRiskSummary.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Risk distribution for CMP-25 Comparison Report Preview.
 * Responsibilities:
 *   - Display backend risk_summary.by_level / items without rescoring
 * Dependencies:
 *   - comparison-badges, comparison-summary labels
 * Public Exports:
 *   - ReportPreviewRiskSummary
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Risk taxonomy is backend-owned. Color is never the only cue.
 * =============================================================================
 */

"use client";

import { RiskBadge } from "@/features/comparisons/comparison-badges";
import { riskLevelHelp, riskLevelLabel } from "@/features/comparisons/comparison-summary";
import { emptyClauseMessage } from "@/features/reports/comparison-report-preview";
import type { ReportPreviewComparison } from "@/types/reports";

type Props = {
  riskSummary: ReportPreviewComparison["risk_summary"];
  onOpenClause?: (clauseId: string) => void;
};

const LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export function ReportPreviewRiskSummary({ riskSummary, onOpenClause }: Props) {
  const byLevel = new Map(
    (riskSummary?.by_level ?? []).map((row) => [
      String(row.level ?? "").toUpperCase(),
      Number(row.count ?? 0),
    ]),
  );
  const items = riskSummary?.items ?? [];
  const hasCounts = LEVELS.some((level) => (byLevel.get(level) ?? 0) > 0);

  return (
    <section id="risks" aria-labelledby="report-risk-heading" className="scroll-mt-4">
      <h2 id="report-risk-heading" className="text-h3 text-primary">
        Tóm tắt rủi ro
      </h2>
      {!hasCounts && items.length === 0 ? (
        <p className="mt-2 text-body-sm text-secondary">{emptyClauseMessage("risks")}</p>
      ) : (
        <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {LEVELS.map((level) => (
            <li
              key={level}
              className="rounded-md border border-border-default bg-surface px-3 py-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <RiskBadge level={level} />
                <span className="text-h3 text-primary">{byLevel.get(level) ?? 0}</span>
              </div>
              <p className="mt-1 text-caption text-tertiary">{riskLevelHelp(level)}</p>
            </li>
          ))}
        </ul>
      )}
      {items.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1.5">
          {items.map((item, index) => {
            const clauseId = item.clause_id ?? "";
            return (
              <li key={`${clauseId}-${index}`}>
                <button
                  type="button"
                  disabled={!clauseId || !onOpenClause}
                  onClick={() => clauseId && onOpenClause?.(clauseId)}
                  className="flex w-full flex-col rounded-md border border-border-default px-3 py-2 text-left hover:bg-elevated disabled:cursor-default"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {item.risk_level ? <RiskBadge level={item.risk_level} /> : null}
                    {item.risk_category ? (
                      <span className="text-caption font-medium text-secondary">
                        {item.risk_category}
                      </span>
                    ) : null}
                    {clauseId ? (
                      <span className="text-caption text-tertiary">{clauseId}</span>
                    ) : null}
                  </div>
                  {item.reason ? (
                    <p className="mt-1 text-body-sm text-secondary">{item.reason}</p>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {hasCounts ? (
        <p className="sr-only">
          {LEVELS.map(
            (level) =>
              `${riskLevelLabel(level)}: ${byLevel.get(level) ?? 0}`,
          ).join(". ")}
        </p>
      ) : null}
    </section>
  );
}
