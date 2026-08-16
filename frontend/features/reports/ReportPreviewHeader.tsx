/**
 * =============================================================================
 * File: ReportPreviewHeader.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Header for TASK-CMP-25 Comparison Report Preview.
 * Responsibilities:
 *   - Show title, document names, status, generated time, export
 * Dependencies:
 *   - report-format, ReportPreviewExportMenu
 * Public Exports:
 *   - ReportPreviewHeader
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Omit missing metadata. Do not invent document names.
 * =============================================================================
 */

"use client";

import Link from "next/link";

import { ReportPreviewExportMenu } from "@/features/reports/ReportPreviewExportMenu";
import {
  formatReportDateTime,
  reportStatusLabel,
} from "@/features/reports/report-format";
import { cn } from "@/lib/utils";
import type { Report, ReportPreviewComparison } from "@/types/reports";

type Props = {
  report: Report;
  comparison: ReportPreviewComparison | null;
  comparisonHref: string | null;
  exporting: boolean;
  onExport: () => void;
};

export function ReportPreviewHeader({
  report,
  comparison,
  comparisonHref,
  exporting,
  onExport,
}: Props) {
  const documents = comparison?.documents ?? [];
  const named = documents.filter((item) => item.title);
  const generatedAt =
    comparison?.metadata?.generated_at ?? report.created_at;

  return (
    <header className="flex flex-col gap-4 border-b border-border-default pb-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <p className="text-caption font-medium text-accent-primary">
          Báo cáo so sánh hợp đồng
        </p>
        <h1 className="mt-1 text-h1 text-primary">{report.title}</h1>
        {named.length >= 2 ? (
          <p className="mt-2 text-body-sm text-secondary">
            <span className="font-medium text-primary">{named[0]?.title}</span>
            <span className="mx-2 text-tertiary">so với</span>
            <span className="font-medium text-primary">{named[1]?.title}</span>
          </p>
        ) : named.length === 1 ? (
          <p className="mt-2 text-body-sm text-secondary">{named[0]?.title}</p>
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-caption text-tertiary">
          <span
            className={cn(
              "rounded-full px-2 py-0.5 font-semibold",
              report.status === "ready" && "bg-success/10 text-success",
              report.status === "pending" && "bg-warning/10 text-warning",
              report.status === "failed" && "bg-danger-soft text-danger",
            )}
          >
            {reportStatusLabel(report.status)}
          </span>
          {generatedAt ? <span>Tạo {formatReportDateTime(generatedAt)}</span> : null}
          {comparisonHref ? (
            <Link
              href={comparisonHref}
              className="text-accent-primary hover:underline"
            >
              Mở so sánh nguồn
            </Link>
          ) : null}
        </div>
      </div>
      <ReportPreviewExportMenu
        format={report.export_format}
        enabled={report.status === "ready"}
        exporting={exporting}
        onExport={onExport}
      />
    </header>
  );
}
