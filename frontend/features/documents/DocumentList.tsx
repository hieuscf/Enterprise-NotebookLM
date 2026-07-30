/**
 * =============================================================================
 * File: DocumentList.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Document list page — filter by file_type, paginate, link to detail
 *          (FR2 / UC2, TASKS.md 1.4 "UI danh sách tài liệu + lịch sử version").
 * Responsibilities:
 *   - Load GET /workspaces/{id}/documents (page/page_size/file_type)
 *   - Fill in each row's current-version status badge via
 *     useDocumentCurrentVersions (bounded concurrency, non-blocking)
 *   - Skeleton rows while loading, friendly error + retry, empty state
 * Dependencies:
 *   - hooks/useDocuments, useDocumentCurrentVersions; features/shell/AppShell
 *   - features/documents/FileTypeIcon, VersionStatusBadge, DocumentEmptyState
 * Public Exports:
 *   - DocumentList
 * Database/Table: documents, document_versions
 * Related Modules: app/workspaces/[id]/documents/page.tsx,
 *   app/workspaces/[id]/documents/[documentId]/page.tsx (detail)
 * Important Notes: See useDocumentCurrentVersions for the N+1 mitigation note.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowRight, ChevronLeft, ChevronRight, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { DocumentEmptyState } from "@/features/documents/DocumentEmptyState";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { VersionStatusBadge } from "@/features/documents/VersionStatusBadge";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useDocumentCurrentVersions } from "@/hooks/useDocumentCurrentVersions";
import { useDocuments } from "@/hooks/useDocuments";
import { cn } from "@/lib/utils";
import type { FileType } from "@/types/documents";

type Props = {
  workspaceId: string;
};

const PAGE_SIZE = 20;

const FILE_TYPE_OPTIONS: { value: FileType | "all"; label: string }[] = [
  { value: "all", label: "Tất cả định dạng" },
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "DOCX" },
  { value: "xlsx", label: "XLSX" },
  { value: "pptx", label: "PPTX" },
  { value: "txt", label: "TXT" },
];

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function DocumentRowSkeleton() {
  return (
    <li className="flex items-center gap-3 px-4 py-3.5">
      <div className="h-9 w-9 shrink-0 animate-pulse rounded-md bg-elevated" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-2/5 animate-pulse rounded bg-elevated" />
        <div className="h-3 w-1/5 animate-pulse rounded bg-elevated" />
      </div>
      <div className="h-6 w-20 shrink-0 animate-pulse rounded-full bg-elevated" />
    </li>
  );
}

export function DocumentList({ workspaceId }: Props) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [fileType, setFileType] = useState<FileType | null>(null);

  const { items, total, loading, error, reload } = useDocuments(workspaceId, {
    page,
    pageSize: PAGE_SIZE,
    fileType,
  });
  const versionMap = useDocumentCurrentVersions(workspaceId, items);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const noDocumentsAtAll = !loading && !error && fileType === null && total === 0;
  const noResultsForFilter = !loading && !error && fileType !== null && total === 0;

  return (
    <AppShell active="documents" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">FR2 · Knowledge Base</p>
            <h1 className="mt-1 text-h1 text-primary">Tài liệu</h1>
            <p className="mt-1 text-body-sm text-secondary">
              {loading ? "Đang tải…" : `${total} tài liệu trong workspace này.`}
            </p>
          </div>
          <Link
            href={`/workspaces/${workspaceId}/upload`}
            className={cn(
              "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4",
              "text-body-sm font-medium text-white shadow-sm hover:bg-accent-primary-hover",
            )}
          >
            <UploadCloud className="h-4 w-4" aria-hidden />
            Tải lên tài liệu
          </Link>
        </div>

        {!noDocumentsAtAll ? (
          <div className="flex items-center gap-2">
            <label htmlFor="file-type-filter" className="text-body-sm text-secondary">
              Định dạng
            </label>
            <select
              id="file-type-filter"
              value={fileType ?? "all"}
              onChange={(e) => {
                const value = e.target.value;
                setFileType(value === "all" ? null : (value as FileType));
                setPage(1);
              }}
              className={cn(
                "h-9 rounded-md border border-border-default bg-surface px-2.5",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            >
              {FILE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex flex-col gap-2">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void reload()}
                className="w-fit text-body-sm font-medium underline"
              >
                Thử lại
              </button>
            </div>
          </div>
        ) : noDocumentsAtAll ? (
          <DocumentEmptyState workspaceId={workspaceId} />
        ) : (
          <>
            <ul className="divide-y divide-border-default rounded-lg border border-border-default bg-surface">
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => <DocumentRowSkeleton key={i} />)
              ) : noResultsForFilter ? (
                <li className="px-4 py-10 text-center text-body-sm text-secondary">
                  Không có tài liệu định dạng{" "}
                  <span className="font-medium text-primary">
                    {fileType?.toUpperCase()}
                  </span>{" "}
                  trong workspace này.{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setFileType(null);
                      setPage(1);
                    }}
                    className="font-medium text-accent-primary underline"
                  >
                    Xoá bộ lọc
                  </button>
                </li>
              ) : (
                items.map((doc) => {
                  const versionState = versionMap[doc.id];
                  return (
                    <li key={doc.id}>
                      <Link
                        href={`/workspaces/${workspaceId}/documents/${doc.id}`}
                        className="group flex items-center gap-3 px-4 py-3.5 transition-colors hover:bg-elevated/60"
                      >
                        <FileTypeIcon fileType={doc.file_type} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-body-sm font-medium text-primary group-hover:text-accent-primary">
                            {doc.title}
                          </p>
                          <p className="mt-0.5 text-caption text-tertiary">
                            {doc.file_type.toUpperCase()} · {formatDate(doc.created_at)}
                          </p>
                        </div>
                        {versionState?.loading || !versionState ? (
                          <div className="h-6 w-20 shrink-0 animate-pulse rounded-full bg-elevated" />
                        ) : versionState.error ? (
                          <span className="shrink-0 text-caption text-tertiary">—</span>
                        ) : versionState.version ? (
                          <VersionStatusBadge status={versionState.version.status} />
                        ) : (
                          <span className="shrink-0 text-caption text-tertiary">Chưa có version</span>
                        )}
                        <ArrowRight
                          className="h-4 w-4 shrink-0 text-tertiary opacity-0 transition-all group-hover:translate-x-0.5 group-hover:text-accent-primary group-hover:opacity-100"
                          aria-hidden
                        />
                      </Link>
                    </li>
                  );
                })
              )}
            </ul>

            {!loading && !noResultsForFilter && totalPages > 1 ? (
              <div className="flex items-center justify-between">
                <p className="text-caption text-tertiary">
                  Trang {page}/{totalPages}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className={cn(
                      "flex h-9 items-center gap-1 rounded-md border border-border-default px-3",
                      "text-body-sm font-medium text-secondary hover:bg-elevated",
                      "disabled:cursor-not-allowed disabled:opacity-50",
                    )}
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden />
                    Trước
                  </button>
                  <button
                    type="button"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className={cn(
                      "flex h-9 items-center gap-1 rounded-md border border-border-default px-3",
                      "text-body-sm font-medium text-secondary hover:bg-elevated",
                      "disabled:cursor-not-allowed disabled:opacity-50",
                    )}
                  >
                    Sau
                    <ChevronRight className="h-4 w-4" aria-hidden />
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </AppShell>
  );
}
