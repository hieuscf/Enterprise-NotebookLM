/**
 * =============================================================================
 * File: UploadJobCard.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Render one upload job's current state — queued / uploading (with
 *          progress) / failed / processing (hands off to PipelineStatusTracker)
 *          (FR2 / UC2).
 * Responsibilities:
 *   - Progress bar during "uploading"; queue position hint during "queued"
 *   - Error message + dismiss during "failed"
 *   - Mount PipelineStatusTracker once the 202 DocumentVersion is available
 * Dependencies:
 *   - hooks/useDocumentUploadQueue (UploadJob type), lib/utils, lucide-react
 *   - features/documents/PipelineStatusTracker
 * Public Exports:
 *   - UploadJobCard
 * Database/Table: N/A
 * Related Modules: features/documents/DocumentUploadView
 * Important Notes: A "failed" job here means the upload request itself
 *   failed (network/400/413/415) — distinct from a pipeline stage failing
 *   after a successful upload, which PipelineStatusTracker handles.
 * =============================================================================
 */

"use client";

import { AlertCircle, Clock, X } from "lucide-react";

import { PipelineStatusTracker } from "@/features/documents/PipelineStatusTracker";
import type { UploadJob } from "@/hooks/useDocumentUploadQueue";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  job: UploadJob;
  onCancel: (clientId: string) => void;
  onDismiss: (clientId: string) => void;
};

export function UploadJobCard({ workspaceId, job, onCancel, onDismiss }: Props) {
  if (job.status === "processing" && job.version) {
    return (
      <PipelineStatusTracker
        workspaceId={workspaceId}
        documentId={job.version.document_id}
        versionId={job.version.id}
        fileName={job.title}
      />
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border p-4",
        job.status === "failed" ? "border-danger/30 bg-danger-soft" : "border-border-default bg-surface",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-body-sm font-medium text-primary">{job.title}</p>
        <button
          type="button"
          onClick={() => (job.status === "uploading" ? onCancel(job.clientId) : onDismiss(job.clientId))}
          aria-label={job.status === "uploading" ? "Hủy tải lên" : "Bỏ khỏi danh sách"}
          className="shrink-0 rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {job.status === "queued" ? (
        <div className="flex items-center gap-2 text-caption text-tertiary">
          <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden />
          Đang chờ trong hàng đợi…
        </div>
      ) : job.status === "uploading" ? (
        <div className="flex flex-col gap-1.5">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-elevated">
            <div
              className="h-full rounded-full bg-accent-primary transition-all"
              style={{ width: `${job.progress}%` }}
            />
          </div>
          <p className="text-caption text-tertiary">Đang tải lên… {job.progress}%</p>
        </div>
      ) : job.status === "failed" ? (
        <div className="flex items-center gap-1.5 text-caption text-danger">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {job.errorMessage ?? "Tải lên thất bại."}
        </div>
      ) : null}
    </div>
  );
}
