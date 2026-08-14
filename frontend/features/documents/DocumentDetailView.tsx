/**
 * =============================================================================
 * File: DocumentDetailView.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Premium document reader shell — compact context bar + viewer canvas.
 * Responsibilities:
 *   - Load document meta; wire versions, upload-replace, delete, AI tool links
 *   - Keep document canvas as visual focus (versions in drawer)
 * Dependencies:
 *   - DocumentViewer, DocumentActionsMenu, VersionHistoryDrawer, ConfirmDialog
 * Public Exports:
 *   - DocumentDetailView
 * Database/Table: documents, document_versions
 * Related Modules: app/workspaces/[id]/documents/[documentId]/page.tsx
 * Important Notes: DELETE uses OpenAPI contract; backend remains RBAC authority.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowLeft, Network, ScrollText, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ToastStack } from "@/components/ui/toast";
import { loadCitationFocus } from "@/features/chat/citation/citation-session";
import { DocumentActionsMenu } from "@/features/documents/DocumentActionsMenu";
import { DocumentExtentLabel } from "@/features/documents/DocumentExtentLabel";
import { DocumentStatusIndicator } from "@/features/documents/DocumentStatusIndicator";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { UploadJobCard } from "@/features/documents/UploadJobCard";
import { UploadVersionDialog } from "@/features/documents/UploadVersionDialog";
import { VersionHistoryDrawer } from "@/features/documents/VersionHistoryDrawer";
import { DocumentViewer } from "@/features/documents/viewer/DocumentViewer";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useDocumentUploadQueue, type StagedFile } from "@/hooks/useDocumentUploadQueue";
import { useDocumentVersions } from "@/hooks/useDocumentVersions";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import {
  ApiClientError,
  deleteDocument,
  documentContentUrl,
  getDocument,
} from "@/lib/api-client";
import { canDeleteDocuments, canUploadDocuments } from "@/lib/rbac";
import { formatBytes } from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { Document, DocumentVersion } from "@/types/documents";

type Props = {
  workspaceId: string;
  documentId: string;
  focusChunkId?: string | null;
  focusPage?: number | null;
  focusCitationId?: string | null;
  focusVersionId?: string | null;
  initialView?: "knowledge" | "original";
};

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function DocumentDetailView({
  workspaceId,
  documentId,
  focusChunkId = null,
  focusPage = null,
  focusCitationId = null,
  focusVersionId = null,
  initialView = "knowledge",
}: Props) {
  const router = useRouter();
  const { user } = useAuth();
  const { isEditor } = useWorkspaceRole(workspaceId);
  const canUpload = canUploadDocuments(user, workspaceId) || isEditor;
  const canDelete = canDeleteDocuments(user, workspaceId);
  const { toasts, pushSuccess, pushError, dismiss } = useToasts();

  const [doc, setDoc] = useState<Document | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [docLoading, setDocLoading] = useState(true);
  const [focusSnippet, setFocusSnippet] = useState<string | null>(null);
  const [focusLocator, setFocusLocator] = useState<
    import("@/types/canonical").CitationLocator | null
  >(null);
  const [resolvedPage, setResolvedPage] = useState<number | null>(focusPage);
  const [resolvedChunkId, setResolvedChunkId] = useState<string | null>(
    focusChunkId,
  );
  const [resolvedVersionId, setResolvedVersionId] = useState<string | null>(
    focusVersionId,
  );

  const [uploadOpen, setUploadOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    setResolvedChunkId(focusChunkId);
    setResolvedVersionId(focusVersionId);
    if (!focusCitationId) {
      setFocusSnippet(null);
      setFocusLocator(null);
      setResolvedPage(focusPage);
      return;
    }
    const payload = loadCitationFocus(workspaceId, focusCitationId);
    setFocusSnippet(payload?.textSnippet ?? null);
    setFocusLocator(payload?.locator ?? null);
    setResolvedPage(
      focusPage ??
        (payload?.page != null && payload.page > 0 ? payload.page : null),
    );
    if (!focusChunkId && payload?.chunkId) {
      setResolvedChunkId(payload.chunkId);
    }
    if (!focusVersionId && payload?.versionId) {
      setResolvedVersionId(payload.versionId);
    }
  }, [workspaceId, focusCitationId, focusPage, focusChunkId, focusVersionId]);

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
          err instanceof ApiClientError
            ? err.message
            : "Unable to load document.",
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

  const currentVersion: DocumentVersion | null = useMemo(
    () => versions.find((v) => v.is_current) ?? versions[0] ?? null,
    [versions],
  );

  const { jobs, addJobs, removeJob, cancelJob } = useDocumentUploadQueue(
    workspaceId,
    {
      onUploaded: () => {
        reloadVersions();
        pushSuccess("New version uploaded — processing pipeline started.");
      },
      onFailed: (job) =>
        pushError(job.errorMessage ?? "Failed to upload new version."),
    },
  );

  const downloadUrl = documentContentUrl(workspaceId, documentId, {
    download: true,
  });

  function handleReplaceSubmit(staged: StagedFile[]) {
    addJobs(staged, { mode: "replace", documentId });
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteDocument(workspaceId, documentId);
      pushSuccess("Document deleted.");
      router.replace(`/workspaces/${workspaceId}/documents`);
      router.refresh();
    } catch (err) {
      setDeleteError(
        err instanceof ApiClientError
          ? err.status === 403
            ? "You do not have permission to delete this document."
            : err.message
          : "Unable to delete document.",
      );
    } finally {
      setDeleting(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      pushSuccess("Document link copied.");
    } catch {
      pushError("Unable to copy link.");
    }
  }

  return (
    <AppShell active="documents" user={user} workspaceId={workspaceId}>
      <div className="flex h-[calc(100vh-4rem)] min-h-0 flex-col">
        {/* Compact document context bar */}
        <div className="shrink-0 border-b border-border-default bg-surface px-4 py-3 sm:px-6">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Link
                href={`/workspaces/${workspaceId}/documents`}
                className="inline-flex items-center gap-1.5 text-caption font-medium text-secondary hover:text-accent-primary"
              >
                <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
                Documents
              </Link>
              {focusChunkId ? (
                <Link
                  href={`/workspaces/${workspaceId}/search`}
                  className="text-caption font-medium text-accent-primary hover:underline"
                >
                  Back to search
                </Link>
              ) : null}
              {focusCitationId ? (
                <Link
                  href={`/workspaces/${workspaceId}/chat`}
                  className="text-caption font-medium text-accent-primary hover:underline"
                >
                  Back to chat
                </Link>
              ) : null}
            </div>

            {docError ? (
              <p
                role="alert"
                className="flex items-center gap-2 text-body-sm text-danger"
              >
                <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
                {docError}
              </p>
            ) : (
              <div className="flex items-start gap-3">
                {doc ? (
                  <FileTypeIcon fileType={doc.file_type} className="h-10 w-10" />
                ) : (
                  <div className="h-10 w-10 animate-pulse rounded-md bg-elevated" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h1 className="truncate text-h3 font-semibold text-primary sm:text-h2">
                        {docLoading ? "Loading…" : doc?.title ?? "Document"}
                      </h1>
                      {doc ? (
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-caption text-tertiary">
                          <span className="uppercase">{doc.file_type}</span>
                          <span aria-hidden>·</span>
                          <span>{formatDate(doc.updated_at || doc.created_at)}</span>
                          {currentVersion ? (
                            <>
                              <span aria-hidden>·</span>
                              <DocumentExtentLabel
                                fileType={doc.file_type}
                                pageCount={currentVersion.page_count}
                              />
                              {currentVersion.file_size_bytes != null ? (
                                <>
                                  <span aria-hidden>·</span>
                                  <span>
                                    {formatBytes(currentVersion.file_size_bytes)}
                                  </span>
                                </>
                              ) : null}
                              <span aria-hidden>·</span>
                              <span>v{currentVersion.version_number}</span>
                            </>
                          ) : null}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {currentVersion ? (
                        <DocumentStatusIndicator status={currentVersion.status} />
                      ) : null}
                      <DocumentActionsMenu
                        canUploadVersion={canUpload}
                        canDelete={canDelete}
                        onOpenOriginal={() =>
                          window.open(downloadUrl, "_blank", "noopener,noreferrer")
                        }
                        onDownload={() =>
                          window.open(downloadUrl, "_blank", "noopener,noreferrer")
                        }
                        onPrint={() => window.print()}
                        onUploadVersion={() => setUploadOpen(true)}
                        onVersionHistory={() => setHistoryOpen(true)}
                        onCopyLink={() => void copyLink()}
                        onDelete={() => {
                          setDeleteError(null);
                          setDeleteOpen(true);
                        }}
                      />
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Link
                      href={`/workspaces/${workspaceId}/summaries?documentId=${documentId}`}
                      className={cn(
                        "inline-flex h-7 items-center gap-1.5 rounded-md border border-border-default px-2.5",
                        "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                      )}
                    >
                      <ScrollText className="h-3 w-3" aria-hidden />
                      Summarize
                    </Link>
                    <Link
                      href={`/workspaces/${workspaceId}/extractions?documentId=${documentId}`}
                      className={cn(
                        "inline-flex h-7 items-center gap-1.5 rounded-md border border-border-default px-2.5",
                        "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                      )}
                    >
                      <Wand2 className="h-3 w-3" aria-hidden />
                      Extract
                    </Link>
                    <Link
                      href={`/workspaces/${workspaceId}/graph`}
                      className={cn(
                        "inline-flex h-7 items-center gap-1.5 rounded-md border border-border-default px-2.5",
                        "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                      )}
                    >
                      <Network className="h-3 w-3" aria-hidden />
                      Explore graph
                    </Link>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {jobs.length > 0 ? (
          <div className="shrink-0 space-y-2 border-b border-border-default bg-elevated/30 px-4 py-3 sm:px-6">
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

        {/* Reader canvas — fills remaining height */}
        <div className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col overflow-hidden px-2 py-3 sm:px-4 sm:py-4 lg:px-6">
          {!docError ? (
            <DocumentViewer
              workspaceId={workspaceId}
              documentId={documentId}
              document={doc}
              currentVersion={currentVersion}
              focusChunkId={resolvedChunkId}
              focusPage={resolvedPage}
              focusCitationId={focusCitationId}
              focusSnippet={focusSnippet}
              focusVersionId={resolvedVersionId}
              focusLocator={focusLocator}
              initialView={initialView}
              onOpenVersionHistory={() => setHistoryOpen(true)}
              onMissingChunk={() => pushError("Referenced passage not found.")}
              onHighlightFailed={() =>
                pushError(
                  focusSnippet
                    ? "Opened the source — exact text highlight was unavailable."
                    : "Could not locate highlight in the document.",
                )
              }
            />
          ) : null}
        </div>
      </div>

      <UploadVersionDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSubmit={handleReplaceSubmit}
      />

      <VersionHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        workspaceId={workspaceId}
        documentId={documentId}
        versions={versions}
        loading={versionsLoading}
        error={versionsError}
        onReload={reloadVersions}
        pushSuccess={pushSuccess}
        pushError={pushError}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Delete document?"
        description="This permanently removes the document and all of its versions from this Workspace."
        confirmLabel="Delete document"
        confirming={deleting}
        error={deleteError}
        onCancel={() => {
          if (!deleting) setDeleteOpen(false);
        }}
        onConfirm={() => void handleDelete()}
      />

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AppShell>
  );
}
