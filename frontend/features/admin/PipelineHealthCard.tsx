/**
 * =============================================================================
 * File: PipelineHealthCard.tsx
 * Module/Service: Document Ingestion Service / Observability (Web App)
 * Layer: UI
 * Purpose: Pipeline Health card (Admin Dashboard §11) — status rollup + per
 *          stage completion rate over the 6-step v3 pipeline.
 * Responsibilities:
 *   - Render status counts (Completed/Processing/Pending/Failed) derived from
 *     the recent pipeline_runs sample
 *   - Render per-stage completion bars using the shared v3 stage order
 * Dependencies:
 *   - features/admin/admin-format (derivePipelineHealth), lib/pipeline-stages
 * Public Exports:
 *   - PipelineHealthCard
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: features/admin/AdminDashboardView, hooks/useAdminPipelineRuns
 * Important Notes: Counts are derived from a bounded recent sample (no
 *   aggregate/count endpoint exists) — footnote makes this explicit rather
 *   than presenting it as a full workspace total.
 * =============================================================================
 */

"use client";

import { AdminCard } from "@/features/admin/AdminCard";
import {
  derivePipelineHealth,
  formatCompactNumber,
  formatPercent,
  PIPELINE_STATUS_BADGE_CLASS,
  PIPELINE_STATUS_LABEL_VI,
} from "@/features/admin/admin-format";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import { cn } from "@/lib/utils";
import type { PipelineRun, PipelineStatus } from "@/types/documents";

type Props = {
  runs: PipelineRun[];
  sampleCapped: boolean;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
};

const STATUS_ORDER: PipelineStatus[] = ["completed", "running", "failed", "pending"];

export function PipelineHealthCard({ runs, sampleCapped, loading, error, onRetry }: Props) {
  const summary = derivePipelineHealth(runs);
  const failedCount = summary.byStatus.failed;

  return (
    <AdminCard
      headingId="admin-pipeline-health"
      title="Pipeline Health"
      description="Trạng thái xử lý tài liệu qua 6 bước pipeline (v3)."
    >
      {loading ? (
        <SectionSkeleton rows={5} />
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : summary.total === 0 ? (
        <SectionEmpty
          title="Chưa có pipeline run nào."
          description="Dữ liệu sẽ xuất hiện sau khi có tài liệu được tải lên và xử lý."
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {STATUS_ORDER.map((status) => (
              <div key={status} className="flex flex-col gap-1">
                <span
                  className={cn(
                    "inline-flex w-fit items-center rounded-full px-2 py-0.5 text-caption font-semibold",
                    PIPELINE_STATUS_BADGE_CLASS[status],
                  )}
                >
                  {PIPELINE_STATUS_LABEL_VI[status]}
                </span>
                <span className="text-h2 font-semibold text-primary">
                  {formatCompactNumber(summary.byStatus[status])}
                </span>
              </div>
            ))}
          </div>

          <div>
            <p className="mb-2 text-caption font-semibold uppercase tracking-wide text-tertiary">
              Tỷ lệ hoàn tất theo bước
            </p>
            <ul className="flex flex-col gap-2">
              {summary.stageCompletion.map((stage) => (
                <li key={stage.stage} className="flex items-center gap-3">
                  <span className="w-40 shrink-0 truncate text-body-sm text-secondary">
                    {stage.label}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-elevated">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        stage.ratio === null
                          ? "bg-transparent"
                          : stage.ratio >= 0.95
                            ? "bg-success"
                            : stage.ratio >= 0.8
                              ? "bg-warning"
                              : "bg-danger",
                      )}
                      style={{ width: `${stage.ratio === null ? 0 : Math.max(stage.ratio * 100, 2)}%` }}
                    />
                  </div>
                  <span className="w-16 shrink-0 text-right text-body-sm font-medium text-primary">
                    {stage.ratio === null ? "—" : formatPercent(stage.ratio, 1)}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-caption text-tertiary">
            Tính trên {formatCompactNumber(summary.total)} pipeline run gần nhất
            {sampleCapped ? " (có thể còn nhiều hơn)" : ""}
            {failedCount > 0 ? ` · ${formatCompactNumber(failedCount)} lỗi` : ""}.
          </p>
        </div>
      )}
    </AdminCard>
  );
}
