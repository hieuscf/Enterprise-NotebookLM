/**
 * =============================================================================
 * File: DocumentDetailView.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Document detail page — header + version history + inline "upload
 *          new version" (replace mode) (FR2 Part 2, TASKS.md 1.4).
 * Responsibilities:
 *   - Load GET .../documents/{documentId} once for title/file_type/created_at
 *   - Own useDocumentVersions (list + reload) and useDocumentUploadQueue in
 *     "replace" mode; wire both into DocumentVersionHistory / UploadJobCard
 *   - Own the toast queue for "Đặt làm bản hiện hành" / upload feedback
 * Dependencies:
 *   - hooks/useDocumentVersions, useDocumentUploadQueue, useToasts,
 *     useWorkspaceRole, useAuth; lib/api-client.getDocument
 *   - features/documents/DocumentVersionHistory, DocumentUploadDropzone,
 *     UploadJobCard, FileTypeIcon
 * Public Exports:
 *   - DocumentDetailView
 * Database/Table: documents, document_versions
 * Related Modules: app/workspaces/[id]/documents/[documentId]/page.tsx,
 *   features/summaries/SummarySection, features/extractions/ExtractionSection
 * Important Notes: A replacement version is already current_version_id in the
 *   backend as soon as the 202 response arrives (see upload_new_version) —
 *   reloading the version list alone is enough to reflect the new
 *   "Đang dùng" badge; no separate getDocument refetch is needed for that.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowLeft, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import { DocumentUploadDropzone } from "@/features/documents/DocumentUploadDropzone";
import { DocumentVersionHistory } from "@/features/documents/DocumentVersionHistory";
import { DocumentViewer } from "@/features/documents/viewer/DocumentViewer";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { UploadJobCard } from "@/features/documents/UploadJobCard";
import { ExtractionSection } from "@/features/extractions/ExtractionSection";
import { SummarySection } from "@/features/summaries/SummarySection";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useDocumentUploadQueue, type StagedFile } from "@/hooks/useDocumentUploadQueue";
import { useDocumentVersions } from "@/hooks/useDocumentVersions";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import { ApiClientError, getDocument } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { Document } from "@/types/documents";

type Props = {
  workspaceId: string;
  documentId: string;
  /** Deep-link from Search (?chunk=). */
  focusChunkId?: string | null;
  focusPage?: number | null;
};

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function DocumentDetailView({
  workspaceId,
  documentId,
  focusChunkId = null,
  focusPage = null,
}: Props) {
  const { user } = useAuth();
  const { isEditor } = useWorkspaceRole(workspaceId);
  const { toasts, pushSuccess, pushError, dismiss } = useToasts();

  const [doc, setDoc] = useState<Document | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [docLoading, setDocLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setDocLoading(true);
    getDocument(workspaceId, documentId)
      .then((data) => {
        if (active) setDoc(data);
      })
      .catch((err) => {
        if (!active) return;
        setDocError(
          err instanceof ApiClientError ? err.message : "Không tải được thông tin tài liệu.",
        );
      })
      .finally(() => {
        if (active) setDocLoading(false);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, documentId]);

  const {
    versions,
    loading: versionsLoading,
    error: versionsError,
    reload: reloadVersions,
  } = useDocumentVersions(workspaceId, documentId);

  const [showReplaceUpload, setShowReplaceUpload] = useState(false);
  const { jobs, addJobs, removeJob, cancelJob } = useDocumentUploadQueue(workspaceId, {
    onUploaded: () => {
      reloadVersions();
      pushSuccess("Đã tải lên version mới — pipeline đang xử lý.");
    },
    onFailed: (job) => pushError(job.errorMessage ?? "Tải lên version mới thất bại."),
  });

  function handleReplaceSubmit(staged: StagedFile[]) {
    addJobs(staged, { mode: "replace", documentId });
    setShowReplaceUpload(false);
  }

  return (
    <AppShell active="documents" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href={`/workspaces/${workspaceId}/documents`}
            className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Quay lại danh sách tài liệu
          </Link>
          {focusChunkId ? (
            <Link
              href={`/workspaces/${workspaceId}/search`}
              className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-accent-primary hover:underline"
            >
              Quay lại tìm kiếm
            </Link>
          ) : null}
        </div>

        {docError ? (
          <p
            role="alert"
            className="flex items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
            {docError}
          </p>
        ) : (
          <div className="flex items-start gap-3">
            {doc ? <FileTypeIcon fileType={doc.file_type} className="h-12 w-12" /> : null}
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-h1 text-primary">
                {docLoading ? "Đang tải…" : doc?.title ?? "Tài liệu"}
              </h1>
              {doc ? (
                <p className="mt-1 text-body-sm text-secondary">
                  {doc.file_type.toUpperCase()} · Tạo ngày {formatDate(doc.created_at)}
                </p>
              ) : null}
            </div>
          </div>
        )}

        <section className="flex flex-col gap-3" aria-label="Nội dung tài liệu">
          <h2 className="text-h3 text-primary">Nội dung</h2>
          <DocumentViewer
            workspaceId={workspaceId}
            documentId={documentId}
            focusChunkId={focusChunkId}
            focusPage={focusPage}
            onMissingChunk={() =>
              pushError("Không tìm thấy đoạn được tham chiếu.")
            }
          />
        </section>

        {!docError ? (
          <SummarySection
            workspaceId={workspaceId}
            documentId={documentId}
            currentVersionId={doc?.current_version_id ?? null}
            canEdit={isEditor}
            onCopied={() => pushSuccess("Đã sao chép tóm tắt.")}
            onCopyFailed={() => pushError("Không sao chép được tóm tắt.")}
            onCreateError={(message) => pushError(message)}
          />
        ) : null}

        {!docError ? (
          <ExtractionSection
            workspaceId={workspaceId}
            documentId={documentId}
            currentVersionId={doc?.current_version_id ?? null}
            canEdit={isEditor}
            onCopied={() => pushSuccess("Đã sao chép kết quả trích xuất.")}
            onCopyFailed={() => pushError("Không sao chép được kết quả trích xuất.")}
            onExportError={(message) => pushError(message)}
            onCreateError={(message) => pushError(message)}
          />
        ) : null}

        <div className="flex flex-col gap-3">
          {isEditor ? (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setShowReplaceUpload((v) => !v)}
                className={cn(
                  "inline-flex h-9 items-center gap-2 rounded-md border border-border-default px-3.5",
                  "text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary",
                )}
              >
                <UploadCloud className="h-4 w-4" aria-hidden />
                Tải lên version mới
              </button>
            </div>
          ) : null}

          {showReplaceUpload ? (
            <DocumentUploadDropzone mode="replace" onSubmit={handleReplaceSubmit} />
          ) : null}

          {jobs.length > 0 ? (
            <div className="flex flex-col gap-3">
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

          <DocumentVersionHistory
            workspaceId={workspaceId}
            documentId={documentId}
            versions={versions}
            loading={versionsLoading}
            error={versionsError}
            onReload={reloadVersions}
            pushSuccess={pushSuccess}
            pushError={pushError}
          />
        </div>
      </div>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AppShell>
  );
}
