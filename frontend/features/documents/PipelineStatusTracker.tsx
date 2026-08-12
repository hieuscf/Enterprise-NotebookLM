/**
 * =============================================================================
 * File: PipelineStatusTracker.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: 6-step stepper showing pipeline_run progress for one document
 *          version, polled via usePipelineStatus (FR2 / FR13).
 * Responsibilities:
 *   - Render document_understanding → indexing with per-step status icon
 *   - Show duration_ms ("2.4s") for completed steps, error_message for failed
 *   - Show "Sẵn sàng" badge + fire onReady() exactly once when all completed
 *   - Show "Không thể cập nhật trạng thái" + manual retry on connection loss
 * Dependencies:
 *   - hooks/usePipelineStatus, lib/pipeline-stages, lib/document-events
 * Public Exports:
 *   - PipelineStatusTracker
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: hooks/usePipelineStatus, features/documents/UploadJobCard
 * Important Notes: "Thử lại" on a failed stage is disabled — there is no
 *   retry endpoint in the current OpenAPI contract (TODO: wire up once BE
 *   adds POST .../pipeline-status/retry or similar).
 * =============================================================================
 */

"use client";

import { RotateCcw, WifiOff } from "lucide-react";
import { useEffect, useRef } from "react";

import { usePipelineStatus } from "@/hooks/usePipelineStatus";
import { notifyDocumentReady } from "@/lib/document-events";
import {
  PIPELINE_STAGE_ORDER,
  STAGE_ICON,
  STAGE_LABEL_VI,
  STATUS_ICON,
  STATUS_LABEL_VI,
} from "@/lib/pipeline-stages";
import { cn } from "@/lib/utils";
import type { PipelineStageLog, PipelineStageNameV3, PipelineStatus } from "@/types/documents";

type Props = {
  workspaceId: string;
  documentId: string;
  versionId: string;
  fileName: string;
  onReady?: () => void;
};

function formatDuration(ms: number | null): string | null {
  if (ms === null) return null;
  return `${(ms / 1000).toFixed(1)}s`;
}

const CIRCLE_CLASS: Record<PipelineStatus, string> = {
  pending: "border-border-default bg-elevated text-tertiary",
  running: "border-accent-primary bg-accent-primary-soft text-accent-primary",
  completed: "border-success/50 bg-success/10 text-success",
  failed: "border-danger/50 bg-danger-soft text-danger",
};

const LABEL_CLASS: Record<PipelineStatus, string> = {
  pending: "text-tertiary",
  running: "text-accent-primary",
  completed: "text-primary",
  failed: "text-danger",
};

function findStageLog(
  stages: PipelineStageLog[],
  stage: PipelineStageNameV3,
): PipelineStageLog | undefined {
  return stages.find((s) => s.stage === stage);
}

export function PipelineStatusTracker({
  workspaceId,
  documentId,
  versionId,
  fileName,
  onReady,
}: Props) {
  const { run, loading, connectionLost, retry } = usePipelineStatus(
    workspaceId,
    documentId,
    versionId,
  );

  const stages = run?.stages ?? [];
  const allCompleted =
    run?.status === "completed" ||
    PIPELINE_STAGE_ORDER.every((stage) => findStageLog(stages, stage)?.status === "completed");
  const failedStage = stages.find((s) => s.status === "failed");

  const readyFiredRef = useRef(false);
  useEffect(() => {
    if (allCompleted && !readyFiredRef.current) {
      readyFiredRef.current = true;
      notifyDocumentReady(documentId);
      onReady?.();
    }
  }, [allCompleted, documentId, onReady]);

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border-default bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-body-sm font-medium text-primary">{fileName}</p>
        {allCompleted ? (
          <span className="shrink-0 rounded-full bg-success/10 px-2.5 py-1 text-caption font-semibold text-success">
            Đã xử lý tài liệu.
          </span>
        ) : failedStage ? (
          <span className="shrink-0 rounded-full bg-danger-soft px-2.5 py-1 text-caption font-semibold text-danger">
            Không thể xử lý tài liệu.
          </span>
        ) : (
          <span className="shrink-0 rounded-full bg-accent-primary-soft px-2.5 py-1 text-caption font-semibold text-accent-primary">
            Đang xử lý tài liệu...
          </span>
        )}
      </div>

      {loading && !run ? (
        <p className="text-body-sm text-tertiary">Đang tải trạng thái pipeline…</p>
      ) : connectionLost ? (
        <div className="flex items-center justify-between gap-3 rounded-md bg-danger-soft px-3 py-2">
          <div className="flex items-center gap-2 text-body-sm text-danger">
            <WifiOff className="h-4 w-4 shrink-0" aria-hidden />
            Không thể cập nhật trạng thái.
          </div>
          <button
            type="button"
            onClick={retry}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-danger/30 px-2.5 py-1 text-caption font-medium text-danger hover:bg-danger/10"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Thử lại
          </button>
        </div>
      ) : (
        <ol className="flex flex-col gap-3 md:flex-row md:items-start md:gap-0">
          {PIPELINE_STAGE_ORDER.map((stage, idx) => {
            const log = findStageLog(stages, stage);
            const status: PipelineStatus = log?.status ?? "pending";
            const StageIcon = STAGE_ICON[stage];
            const StatusIcon = STATUS_ICON[status];
            const duration = formatDuration(log?.duration_ms ?? null);
            const isLast = idx === PIPELINE_STAGE_ORDER.length - 1;

            return (
              <li key={stage} className="flex items-start gap-3 md:flex-1 md:flex-col md:items-center md:gap-2">
                <div className="flex w-full items-center md:justify-center">
                  <div
                    className={cn(
                      "hidden h-px flex-1 md:block",
                      idx === 0 ? "opacity-0" : "bg-border-default",
                    )}
                  />
                  <span
                    className={cn(
                      "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2",
                      CIRCLE_CLASS[status],
                    )}
                    title={STATUS_LABEL_VI[status]}
                  >
                    <StatusIcon
                      className={cn("h-4 w-4", status === "running" && "animate-spin")}
                      aria-hidden
                    />
                  </span>
                  <div
                    className={cn(
                      "hidden h-px flex-1 md:block",
                      isLast ? "opacity-0" : "bg-border-default",
                    )}
                  />
                </div>

                <div className="min-w-0 md:text-center">
                  <div className="flex items-center gap-1.5 md:flex-col md:gap-0.5">
                    <StageIcon className="h-3.5 w-3.5 shrink-0 text-tertiary md:hidden" aria-hidden />
                    <p className={cn("text-caption font-medium leading-tight", LABEL_CLASS[status])}>
                      {STAGE_LABEL_VI[stage]}
                    </p>
                  </div>
                  {status === "completed" && duration ? (
                    <p className="text-caption text-tertiary">{duration}</p>
                  ) : null}
                  {status === "failed" && log?.error_message ? (
                    <p className="max-w-[14rem] text-caption text-danger">{log.error_message}</p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {failedStage ? (
        <div className="flex items-center justify-between gap-3 border-t border-border-default pt-3">
          <p className="text-caption text-tertiary">
            Bước &ldquo;{STAGE_LABEL_VI[failedStage.stage as PipelineStageNameV3] ?? failedStage.stage}&rdquo; gặp lỗi.
          </p>
          {/* TODO(FR2): bật nút này khi backend có endpoint retry pipeline-status. */}
          <button
            type="button"
            disabled
            title="Chưa hỗ trợ ở backend — cần endpoint retry pipeline."
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-border-default px-2.5 py-1 text-caption font-medium text-tertiary opacity-60"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Thử lại
          </button>
        </div>
      ) : null}
    </div>
  );
}
