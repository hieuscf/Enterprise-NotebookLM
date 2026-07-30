/**
 * =============================================================================
 * File: DocumentUploadView.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Upload page — dropzone + this-session job list with live pipeline
 *          trackers (FR2 / UC2, TASKS.md 1.4 "UI Upload tài liệu").
 * Responsibilities:
 *   - Gate upload behind editor/admin role (backend still enforces RBAC)
 *   - Wire DocumentUploadDropzone → useDocumentUploadQueue → UploadJobCard[]
 *   - Surface upload failures as toasts (network/400/413/415)
 * Dependencies:
 *   - hooks/useDocumentUploadQueue, useToasts, useWorkspaceRole, useAuth
 *   - features/documents/DocumentUploadDropzone, UploadJobCard
 *   - lib/api-client.getWorkspace; components/ui/toast
 * Public Exports:
 *   - DocumentUploadView
 * Database/Table: N/A (delegates to documents/pipeline via the hooks above)
 * Related Modules: app/workspaces/[id]/upload/page.tsx
 * Important Notes: Jobs live in local state only — full document/version
 *   history is Part 2 (document list page), not built yet.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import { DocumentUploadDropzone } from "@/features/documents/DocumentUploadDropzone";
import { UploadJobCard } from "@/features/documents/UploadJobCard";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useDocumentUploadQueue, type StagedFile } from "@/hooks/useDocumentUploadQueue";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import { ApiClientError, getWorkspace } from "@/lib/api-client";
import type { Workspace } from "@/types/workspaces";

type Props = {
  workspaceId: string;
};

export function DocumentUploadView({ workspaceId }: Props) {
  const { user } = useAuth();
  const { isEditor, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const { toasts, pushError, dismiss } = useToasts();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getWorkspace(workspaceId)
      .then((data) => {
        if (active) setWorkspace(data);
      })
      .catch((err) => {
        if (!active) return;
        setWsError(
          err instanceof ApiClientError ? err.message : "Không tải được thông tin workspace.",
        );
      });
    return () => {
      active = false;
    };
  }, [workspaceId]);

  const { jobs, addJobs, removeJob, cancelJob } = useDocumentUploadQueue(workspaceId, {
    onFailed: (job) => pushError(`${job.title}: ${job.errorMessage ?? "Tải lên thất bại."}`),
  });

  const handleSubmit = useCallback(
    (staged: StagedFile[]) => addJobs(staged),
    [addJobs],
  );

  const headerLoading = roleLoading || (!workspace && !wsError);

  return (
    <AppShell active="upload" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-8">
        <Link
          href={`/workspaces/${workspaceId}`}
          className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Quay lại workspace
        </Link>

        <div>
          <p className="text-caption font-medium text-accent-primary">Tải lên tài liệu</p>
          <h1 className="mt-1 truncate text-h1 text-primary">
            {headerLoading ? "Đang tải…" : workspace?.name ?? "Workspace"}
          </h1>
          <p className="mt-1 text-body-sm text-secondary">
            Kéo-thả hoặc chọn file để bắt đầu xử lý pipeline 6 bước, từ trích xuất bố cục
            tới lập chỉ mục tìm kiếm.
          </p>
        </div>

        {wsError ? (
          <p
            role="alert"
            className="flex items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
            {wsError}
          </p>
        ) : null}

        <DocumentUploadDropzone
          disabled={!roleLoading && !isEditor}
          disabledReason="Cần quyền editor hoặc admin để tải lên tài liệu."
          onSubmit={handleSubmit}
        />

        {jobs.length > 0 ? (
          <div className="flex flex-col gap-3">
            <p className="text-caption font-medium uppercase tracking-wider text-tertiary">
              Phiên làm việc hiện tại ({jobs.length})
            </p>
            {jobs.map((job) => (
              <UploadJobCard
                key={job.clientId}
                workspaceId={workspaceId}
                job={job}
                onCancel={cancelJob}
                onDismiss={removeJob}
              />
            ))}
          </div>
        ) : null}
      </div>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AppShell>
  );
}
