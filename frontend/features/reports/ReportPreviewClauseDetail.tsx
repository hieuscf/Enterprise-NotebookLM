/**
 * =============================================================================
 * File: ReportPreviewClauseDetail.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Detailed V1/V2 clause inspector for CMP-25 preview.
 * Responsibilities:
 *   - Show original texts, backend exact diffs, risk, explanation, evidence
 * Dependencies:
 *   - comparison-badges, ReportPreviewEvidence
 * Public Exports:
 *   - ReportPreviewClauseDetail
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview, ClauseComparisonView (shared badges)
 * Important Notes: Do not run a frontend diff. Render backend exact_differences
 *   as labeled pairs. Legal text is untrusted text, never HTML.
 * =============================================================================
 */

"use client";

import { X } from "lucide-react";

import { RiskBadge, StatusBadge } from "@/features/comparisons/comparison-badges";
import { displayClauseId } from "@/features/comparisons/comparison-summary";
import { ReportPreviewEvidence } from "@/features/reports/ReportPreviewEvidence";
import type { ReportPreviewDetailedClause } from "@/types/reports";

type Props = {
  workspaceId: string;
  clause: ReportPreviewDetailedClause;
  onClose: () => void;
};

function LegalText({
  label,
  text,
  emptyNote,
}: {
  label: string;
  text: string | null | undefined;
  emptyNote?: string | null;
}) {
  return (
    <div className="min-w-0">
      <h3 className="text-caption font-semibold uppercase tracking-wide text-tertiary">
        {label}
      </h3>
      {text ? (
        <p className="mt-2 whitespace-pre-wrap break-words text-body-sm leading-relaxed text-primary">
          {text}
        </p>
      ) : (
        <p className="mt-2 text-body-sm text-secondary">
          {emptyNote || "Không có nội dung nguồn cho phiên bản này."}
        </p>
      )}
    </div>
  );
}

export function ReportPreviewClauseDetail({ workspaceId, clause, onClose }: Props) {
  const heading = clause.display_id || displayClauseId(clause.clause_id);
  const diffs = clause.exact_differences ?? [];
  const titleId = "report-clause-detail-title";

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      className="flex h-full min-h-0 flex-col border-t border-border-default bg-surface lg:border-l lg:border-t-0"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border-default px-4 py-3">
        <div className="min-w-0">
          <h2 id={titleId} className="text-h3 text-primary">
            {heading}
          </h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {clause.status ? <StatusBadge status={clause.status} /> : null}
            {clause.risk_level ? <RiskBadge level={clause.risk_level} /> : null}
            {clause.risk_category ? (
              <span className="text-caption text-tertiary">{clause.risk_category}</span>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Đóng chi tiết điều khoản"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-tertiary hover:bg-elevated hover:text-primary"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="grid gap-4 md:grid-cols-2">
          <LegalText
            label="Phiên bản 1"
            text={clause.v1_text}
            emptyNote={
              String(clause.status ?? "").toUpperCase() === "ADDED"
                ? clause.absence_note
                : null
            }
          />
          <LegalText
            label="Phiên bản 2"
            text={clause.v2_text}
            emptyNote={
              String(clause.status ?? "").toUpperCase() === "REMOVED"
                ? clause.absence_note
                : null
            }
          />
        </div>

        <section className="mt-5" aria-labelledby="report-exact-changes">
          <h3 id="report-exact-changes" className="text-body-sm font-semibold text-primary">
            Thay đổi chính xác
          </h3>
          {diffs.length === 0 ? (
            <p className="mt-1 text-body-sm text-secondary">
              Báo cáo không cung cấp siêu dữ liệu khác biệt từng đoạn.
            </p>
          ) : (
            <ul className="mt-2 flex flex-col gap-2">
              {diffs.map((diff, index) => (
                <li
                  key={`${diff.label ?? "diff"}-${index}`}
                  className="rounded-md border border-border-default px-3 py-2"
                >
                  <p className="text-caption font-semibold text-secondary">
                    {diff.label || "Giá trị"}
                  </p>
                  <p className="mt-1 text-body-sm text-primary">
                    <span className="text-tertiary">V1: </span>
                    {diff.old || "—"}
                  </p>
                  <p className="text-body-sm text-primary">
                    <span className="text-tertiary">V2: </span>
                    {diff.new || "—"}
                  </p>
                  {diff.delta || diff.percent ? (
                    <p className="mt-1 text-caption text-tertiary">
                      {[diff.delta, diff.percent].filter(Boolean).join(" · ")}
                    </p>
                  ) : null}
                  {diff.context ? (
                    <p className="mt-1 text-caption text-secondary">{diff.context}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        {clause.explanation ? (
          <section className="mt-5" aria-labelledby="report-explanation">
            <h3 id="report-explanation" className="text-body-sm font-semibold text-primary">
              Giải thích rủi ro
            </h3>
            <p className="mt-1 whitespace-pre-wrap text-body-sm text-secondary">
              {clause.explanation}
            </p>
          </section>
        ) : null}

        {clause.recommendation ? (
          <section className="mt-4" aria-labelledby="report-recommendation">
            <h3 id="report-recommendation" className="text-body-sm font-semibold text-primary">
              Khuyến nghị
            </h3>
            <p className="mt-1 whitespace-pre-wrap text-body-sm text-secondary">
              {clause.recommendation}
            </p>
          </section>
        ) : null}

        {clause.absence_note ? (
          <p className="mt-4 text-body-sm text-secondary">{clause.absence_note}</p>
        ) : null}

        <div className="mt-5">
          <ReportPreviewEvidence
            workspaceId={workspaceId}
            evidence={clause.evidence ?? []}
          />
        </div>
      </div>
    </aside>
  );
}
