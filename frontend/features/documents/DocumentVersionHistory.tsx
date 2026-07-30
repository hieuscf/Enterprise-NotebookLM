/**
 * =============================================================================
 * File: DocumentVersionHistory.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Version history list for one document — status, current badge,
 *          set-current/rollback, and live/failed pipeline linkage (FR2 Part 2).
 * Responsibilities:
 *   - Render versions newest-first: version_number, created_at, uploaded_by,
 *     file_size_bytes, VersionStatusBadge, "Đang dùng" badge for is_current
 *   - "Đặt làm bản hiện hành" only for non-current versions with status=ready
 *     (backend already enforces this — 400 version_not_ready otherwise)
 *   - Confirm dialog (variant="primary") explaining the Chat/Search impact
 *   - For processing/failed versions, expand a PipelineStatusTracker inline
 * Dependencies:
 *   - components/ui/confirm-dialog; features/documents/PipelineStatusTracker,
 *     VersionStatusBadge; lib/api-client.setCurrentVersion; lib/upload-constraints
 * Public Exports:
 *   - DocumentVersionHistory
 * Database/Table: document_versions
 * Related Modules: features/documents/DocumentDetailView
 * Important Notes: Skeleton rows while loading — no full-screen spinner.
 * =============================================================================
 */

"use client";

import { ChevronDown, Clock, User } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PipelineStatusTracker } from "@/features/documents/PipelineStatusTracker";
import { VersionStatusBadge } from "@/features/documents/VersionStatusBadge";
import { ApiClientError, setCurrentVersion } from "@/lib/api-client";
import { formatBytes } from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { DocumentVersion } from "@/types/documents";

type Props = {
  workspaceId: string;
  documentId: string;
  versions: DocumentVersion[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  onSetCurrentSuccess?: () => void;
  pushSuccess: (message: string) => void;
  pushError: (message: string) => void;
};

function formatDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(
      new Date(iso),
    );
  } catch {
    return iso;
  }
}

function mapSetCurrentError(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.code === "version_not_ready") {
      return "Version này chưa sẵn sàng — chỉ có thể đặt làm bản hiện hành khi trạng thái là 'Sẵn sàng'.";
    }
    if (err.code === "not_found") return "Không tìm thấy version này.";
    if (err.status === 403) return "Bạn không đủ quyền thực hiện thao tác này (cần role editor).";
    return err.message;
  }
  return "Không đặt được bản hiện hành. Thử lại sau.";
}

function VersionRowSkeleton() {
  return (
    <li className="flex items-center gap-3 px-4 py-3.5">
      <div className="h-4 w-10 animate-pulse rounded bg-elevated" />
      <div className="flex-1 space-y-2">
        <div className="h-3.5 w-1/3 animate-pulse rounded bg-elevated" />
        <div className="h-3 w-1/4 animate-pulse rounded bg-elevated" />
      </div>
      <div className="h-6 w-20 animate-pulse rounded-full bg-elevated" />
    </li>
  );
}

export function DocumentVersionHistory({
  workspaceId,
  documentId,
  versions,
  loading,
  error,
  onReload,
  onSetCurrentSuccess,
  pushSuccess,
  pushError,
}: Props) {
  const [confirmTarget, setConfirmTarget] = useState<DocumentVersion | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function handleConfirmSetCurrent() {
    if (!confirmTarget) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      await setCurrentVersion(workspaceId, documentId, confirmTarget.id);
      pushSuccess(`Đã đặt v${confirmTarget.version_number} làm bản hiện hành.`);
      setConfirmTarget(null);
      onReload();
      onSetCurrentSuccess?.();
    } catch (err) {
      const message = mapSetCurrentError(err);
      setConfirmError(message);
      pushError(message);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption font-medium uppercase tracking-wider text-tertiary">
        Lịch sử version ({versions.length})
      </p>

      {error ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
        >
          {error}
          <button type="button" onClick={onReload} className="font-medium underline">
            Thử lại
          </button>
        </div>
      ) : (
        <ul className="divide-y divide-border-default rounded-lg border border-border-default bg-surface">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => <VersionRowSkeleton key={i} />)
          ) : versions.length === 0 ? (
            <li className="px-4 py-8 text-center text-body-sm text-secondary">
              Chưa có version nào.
            </li>
          ) : (
            versions.map((version) => {
              const canSetCurrent = !version.is_current && version.status === "ready";
              const canExpandPipeline = version.status === "processing" || version.status === "failed";
              const isExpanded = expandedId === version.id;

              return (
                <li key={version.id} className="flex flex-col gap-2 px-4 py-3.5">
                  <div className="flex items-center gap-3">
                    <span className="w-10 shrink-0 text-body-sm font-semibold text-primary">
                      v{version.version_number}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-caption text-tertiary">
                        <Clock className="h-3 w-3 shrink-0" aria-hidden />
                        {formatDateTime(version.created_at)}
                        <span aria-hidden>·</span>
                        <User className="h-3 w-3 shrink-0" aria-hidden />
                        <span title={version.uploaded_by}>{version.uploaded_by.slice(0, 8)}</span>
                        <span aria-hidden>·</span>
                        {formatBytes(version.file_size_bytes)}
                      </div>
                    </div>

                    {version.is_current ? (
                      <span className="shrink-0 rounded-full bg-accent-primary-soft px-2.5 py-1 text-caption font-semibold text-accent-primary">
                        Đang dùng
                      </span>
                    ) : null}
                    <VersionStatusBadge status={version.status} />

                    {canSetCurrent ? (
                      <button
                        type="button"
                        onClick={() => {
                          setConfirmError(null);
                          setConfirmTarget(version);
                        }}
                        className="shrink-0 rounded-md border border-border-default px-2.5 py-1.5 text-caption font-medium text-secondary hover:bg-elevated hover:text-primary"
                      >
                        Đặt làm bản hiện hành
                      </button>
                    ) : !version.is_current ? (
                      <button
                        type="button"
                        disabled
                        title="Chỉ có thể đặt làm bản hiện hành khi version đã ở trạng thái 'Sẵn sàng'."
                        className="shrink-0 rounded-md border border-border-default px-2.5 py-1.5 text-caption font-medium text-tertiary opacity-60"
                      >
                        Đặt làm bản hiện hành
                      </button>
                    ) : null}

                    {canExpandPipeline ? (
                      <button
                        type="button"
                        onClick={() => setExpandedId(isExpanded ? null : version.id)}
                        aria-label={isExpanded ? "Ẩn tiến trình pipeline" : "Xem tiến trình pipeline"}
                        className="shrink-0 rounded-md p-1.5 text-tertiary hover:bg-elevated hover:text-primary"
                      >
                        <ChevronDown
                          className={cn("h-4 w-4 transition-transform", isExpanded && "rotate-180")}
                          aria-hidden
                        />
                      </button>
                    ) : null}
                  </div>

                  {isExpanded && canExpandPipeline ? (
                    <PipelineStatusTracker
                      workspaceId={workspaceId}
                      documentId={documentId}
                      versionId={version.id}
                      fileName={`v${version.version_number}`}
                    />
                  ) : null}
                </li>
              );
            })
          )}
        </ul>
      )}

      <ConfirmDialog
        open={confirmTarget !== null}
        variant="primary"
        title={`Đặt v${confirmTarget?.version_number ?? ""} làm bản hiện hành?`}
        description="Các câu trả lời Chat và tìm kiếm sau này sẽ dùng nội dung của version này thay cho bản đang dùng hiện tại."
        confirmLabel="Đặt làm bản hiện hành"
        confirming={confirming}
        error={confirmError}
        onConfirm={handleConfirmSetCurrent}
        onCancel={() => {
          if (!confirming) setConfirmTarget(null);
        }}
      />
    </div>
  );
}
