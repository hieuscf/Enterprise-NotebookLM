/**
 * =============================================================================
 * File: RecentPipelineTable.tsx
 * Module/Service: Document Ingestion Service / Observability (Web App)
 * Layer: UI
 * Purpose: Recent Pipeline Activity table (Admin Dashboard §13) — latest
 *          pipeline_runs for the selected workspace.
 * Responsibilities:
 *   - Render Document Version / Status / Duration / Started columns
 * Dependencies:
 *   - features/admin/admin-format, features/admin/AdminSectionState
 * Public Exports:
 *   - RecentPipelineTable
 * Database/Table: pipeline_runs
 * Related Modules: features/admin/AdminDashboardView, hooks/useAdminPipelineRuns
 * Important Notes: PipelineRunResponse only exposes document_version_id (no
 *   document title/document_id join) — rows show a short version id instead
 *   of inventing a document name. No row navigation: there is no admin
 *   pipeline-run detail route in the app yet (would be a fake link).
 * =============================================================================
 */

"use client";

import { AdminCard } from "@/features/admin/AdminCard";
import {
  PIPELINE_STATUS_BADGE_CLASS,
  PIPELINE_STATUS_LABEL_VI,
  formatDateTimeShort,
  pipelineDurationLabel,
  shortId,
} from "@/features/admin/admin-format";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import { cn } from "@/lib/utils";
import type { PipelineRun } from "@/types/documents";

type Props = {
  runs: PipelineRun[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
};

export function RecentPipelineTable({ runs, loading, error, onRetry }: Props) {
  const recent = runs.slice(0, 8);

  return (
    <AdminCard
      headingId="admin-recent-pipeline"
      title="Recent Pipeline Runs"
      description="Các lượt xử lý tài liệu gần nhất qua pipeline."
    >
      {loading ? (
        <SectionSkeleton rows={5} />
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : recent.length === 0 ? (
        <SectionEmpty
          title="No pipeline runs found."
          description="Chưa có lượt xử lý tài liệu nào trong workspace này."
        />
      ) : (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                <th className="px-1 py-2 font-medium">Document Version</th>
                <th className="px-1 py-2 font-medium">Status</th>
                <th className="px-1 py-2 text-right font-medium">Duration</th>
                <th className="px-1 py-2 text-right font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((run) => (
                <tr key={run.id} className="border-b border-border-default last:border-0">
                  <td
                    className="px-1 py-2 font-mono text-caption text-secondary"
                    title={run.document_version_id}
                  >
                    #{shortId(run.document_version_id)}
                  </td>
                  <td className="px-1 py-2">
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-caption font-semibold",
                        PIPELINE_STATUS_BADGE_CLASS[run.status],
                      )}
                    >
                      {PIPELINE_STATUS_LABEL_VI[run.status]}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-1 py-2 text-right text-primary">
                    {pipelineDurationLabel(run)}
                  </td>
                  <td className="whitespace-nowrap px-1 py-2 text-right text-tertiary">
                    {run.started_at ? formatDateTimeShort(run.started_at) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AdminCard>
  );
}
