/**
 * =============================================================================
 * File: ReportPreviewOverview.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Executive summary and compact statistics for CMP-25.
 * Responsibilities:
 *   - Render backend executive_summary / statistics without recounting
 * Dependencies:
 *   - comparison-report-preview executiveCounts
 * Public Exports:
 *   - ReportPreviewOverview, ReportPreviewStatistics
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Numbers come from the report payload, not clause arrays.
 * =============================================================================
 */

"use client";

import type { ExecutiveCounts } from "@/features/reports/comparison-report-preview";
import type { ReportPreviewDocument } from "@/types/reports";

type OverviewProps = {
  counts: ExecutiveCounts;
  documents: ReportPreviewDocument[];
};

export function ReportPreviewOverview({ counts, documents }: OverviewProps) {
  return (
    <section id="overview" aria-labelledby="report-overview-heading" className="scroll-mt-4">
      <h2 id="report-overview-heading" className="text-h3 text-primary">
        Tổng quan so sánh
      </h2>
      <p className="mt-1 text-body-sm text-secondary">
        {counts.total} điều khoản được so sánh
      </p>
      {documents.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1 text-body-sm text-secondary" id="documents">
          {documents.map((doc, index) => (
            <li key={`${doc.side ?? "doc"}-${doc.document_id ?? index}`}>
              <span className="font-medium text-primary">{doc.side ?? "Tài liệu"}</span>
              {doc.title ? <span className="ml-2">{doc.title}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      <ReportPreviewStatistics counts={counts} />
    </section>
  );
}

export function ReportPreviewStatistics({ counts }: { counts: ExecutiveCounts }) {
  const cards = [
    { label: "Điều khoản so sánh", value: counts.total, emphasize: false },
    { label: "Không đổi", value: counts.unchanged, emphasize: false },
    { label: "Đã sửa", value: counts.modified, emphasize: true },
    { label: "Thêm mới", value: counts.added, emphasize: false },
    { label: "Đã xoá", value: counts.removed, emphasize: false },
  ];

  return (
    <div
      id="statistics"
      className="mt-4 grid scroll-mt-4 grid-cols-2 gap-2 sm:grid-cols-5"
    >
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-md border border-border-default bg-surface px-3 py-2.5"
        >
          <p
            className={
              card.emphasize
                ? "text-h2 text-primary"
                : "text-h2 font-semibold text-secondary"
            }
          >
            {card.value}
          </p>
          <p className="mt-0.5 text-caption text-tertiary">{card.label}</p>
        </div>
      ))}
    </div>
  );
}
