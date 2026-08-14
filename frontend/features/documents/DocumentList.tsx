/**
 * =============================================================================
 * File: DocumentList.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Premium document library — table/list hybrid for Workspace KB (FR2).
 * Responsibilities:
 *   - Filter by file_type; paginate; show status/size/pages from current version
 *   - Gate upload CTA via canUploadDocuments; empty / error / filter-empty states
 * Dependencies:
 *   - hooks/useDocuments, useDocumentCurrentVersions; AppShell; FileTypeIcon
 * Public Exports:
 *   - DocumentList
 * Database/Table: documents, document_versions
 * Related Modules: app/workspaces/[id]/documents/page.tsx
 * Important Notes: Status via N+1 getDocumentVersion until list embeds it.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { DocumentEmptyState } from "@/features/documents/DocumentEmptyState";
import { DocumentExtentLabel } from "@/features/documents/DocumentExtentLabel";
import { DocumentStatusIndicator } from "@/features/documents/DocumentStatusIndicator";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useDocumentCurrentVersions } from "@/hooks/useDocumentCurrentVersions";
import { useDocuments } from "@/hooks/useDocuments";
import { canUploadDocuments } from "@/lib/rbac";
import { formatBytes } from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { FileType } from "@/types/documents";

type Props = {
  workspaceId: string;
};

const PAGE_SIZE = 20;

const FILE_TYPE_TABS: { value: FileType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "DOCX" },
  { value: "xlsx", label: "XLSX" },
  { value: "pptx", label: "PPTX" },
  { value: "txt", label: "TXT" },
];

function formatRelativeOrDate(iso: string): string {
  try {
    const date = new Date(iso);
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startThat = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round(
      (startToday.getTime() - startThat.getTime()) / 86_400_000,
    );
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays > 1 && diffDays < 7) return `${diffDays} days ago`;
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(date);
  } catch {
    return iso;
  }
}

function RowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3.5">
      <div className="h-9 w-9 shrink-0 animate-pulse rounded-md bg-elevated" />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="h-4 w-2/5 max-w-xs animate-pulse rounded bg-elevated" />
        <div className="h-3 w-1/4 max-w-[8rem] animate-pulse rounded bg-elevated" />
      </div>
      <div className="hidden h-4 w-16 animate-pulse rounded bg-elevated sm:block" />
      <div className="h-4 w-20 animate-pulse rounded bg-elevated" />
    </div>
  );
}

export function DocumentList({ workspaceId }: Props) {
  const { user } = useAuth();
  const canUpload = canUploadDocuments(user, workspaceId);
  const [page, setPage] = useState(1);
  const [fileType, setFileType] = useState<FileType | null>(null);
  const [query, setQuery] = useState("");

  const { items, total, loading, error, reload } = useDocuments(workspaceId, {
    page,
    pageSize: PAGE_SIZE,
    fileType,
  });
  const versionMap = useDocumentCurrentVersions(workspaceId, items);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((d) => d.title.toLowerCase().includes(q));
  }, [items, query]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const noDocumentsAtAll = !loading && !error && fileType === null && total === 0;
  const noResultsForFilter =
    !loading && !error && fileType !== null && total === 0;

  return (
    <AppShell active="documents" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <p className="text-caption font-medium text-accent-primary">
              Knowledge Base
            </p>
            <h1 className="mt-1 text-h1 text-primary">Documents</h1>
            <p className="mt-1 max-w-xl text-body-sm text-secondary">
              Your Workspace knowledge base — searchable, citable, and connected
              to AI Chat and the Knowledge Graph.
            </p>
          </div>
          {canUpload ? (
            <Link
              href={`/workspaces/${workspaceId}/upload`}
              className={cn(
                "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white shadow-xs hover:bg-accent-primary-hover",
              )}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Upload document
            </Link>
          ) : null}
        </header>

        {!noDocumentsAtAll ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative max-w-sm flex-1">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-tertiary"
                aria-hidden
              />
              <label htmlFor="doc-list-search" className="sr-only">
                Search documents
              </label>
              <input
                id="doc-list-search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search documents…"
                className={cn(
                  "h-10 w-full rounded-md border border-border-default bg-surface pl-9 pr-3",
                  "text-body-sm text-primary outline-none",
                  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                )}
              />
            </div>
            <p className="text-caption text-tertiary">
              {loading ? "Loading…" : `${total} document${total === 1 ? "" : "s"}`}
              <span className="mx-1.5 text-border-strong">·</span>
              PDF · DOCX · XLSX · PPTX · TXT
            </p>
          </div>
        ) : null}

        {!noDocumentsAtAll ? (
          <div
            role="tablist"
            aria-label="Filter by file type"
            className="flex flex-wrap gap-1 border-b border-border-default pb-px"
          >
            {FILE_TYPE_TABS.map((tab) => {
              const active =
                (tab.value === "all" && fileType === null) ||
                tab.value === fileType;
              return (
                <button
                  key={tab.value}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => {
                    setFileType(tab.value === "all" ? null : tab.value);
                    setPage(1);
                  }}
                  className={cn(
                    "relative -mb-px px-3 py-2 text-body-sm font-medium transition-colors",
                    active
                      ? "border-b-2 border-accent-primary text-accent-primary"
                      : "text-secondary hover:text-primary",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex flex-col gap-2">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void reload()}
                className="w-fit font-medium underline"
              >
                Try again
              </button>
            </div>
          </div>
        ) : noDocumentsAtAll ? (
          <DocumentEmptyState workspaceId={workspaceId} canUpload={canUpload} />
        ) : (
          <>
            <div className="overflow-hidden rounded-md border border-border-default bg-surface">
              <div className="hidden grid-cols-[minmax(0,1fr)_7rem_6.5rem] gap-3 border-b border-border-default bg-elevated/40 px-4 py-2.5 text-caption font-medium tracking-wide text-tertiary uppercase md:grid">
                <span>Document</span>
                <span>Status</span>
                <span className="text-right">Updated</span>
              </div>

              <ul className="divide-y divide-border-default">
                {loading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <li key={i}>
                      <RowSkeleton />
                    </li>
                  ))
                ) : noResultsForFilter ? (
                  <li className="px-4 py-12 text-center text-body-sm text-secondary">
                    No{" "}
                    <span className="font-medium text-primary">
                      {fileType?.toUpperCase()}
                    </span>{" "}
                    documents in this Workspace.{" "}
                    <button
                      type="button"
                      onClick={() => {
                        setFileType(null);
                        setPage(1);
                      }}
                      className="font-medium text-accent-primary underline"
                    >
                      Clear filter
                    </button>
                  </li>
                ) : filteredItems.length === 0 ? (
                  <li className="px-4 py-12 text-center text-body-sm text-secondary">
                    No documents match “{query.trim()}”.
                  </li>
                ) : (
                  filteredItems.map((doc) => {
                    const versionState = versionMap[doc.id];
                    const version = versionState?.version;
                    return (
                      <li key={doc.id}>
                        <Link
                          href={`/workspaces/${workspaceId}/documents/${doc.id}`}
                          className="group grid grid-cols-1 gap-2 px-4 py-3.5 transition-colors hover:bg-elevated/50 md:grid-cols-[minmax(0,1fr)_7rem_6.5rem] md:items-center md:gap-3"
                        >
                          <div className="flex min-w-0 items-start gap-3">
                            <FileTypeIcon
                              fileType={doc.file_type}
                              className="mt-0.5 h-9 w-9"
                            />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-body-sm font-medium text-primary group-hover:text-accent-primary">
                                {doc.title}
                              </p>
                              <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-caption text-tertiary">
                                <span className="uppercase">{doc.file_type}</span>
                                {version ? (
                                  <>
                                    <span aria-hidden>·</span>
                                    <DocumentExtentLabel
                                      fileType={doc.file_type}
                                      pageCount={version.page_count}
                                    />
                                    {version.file_size_bytes != null ? (
                                      <>
                                        <span aria-hidden>·</span>
                                        <span>
                                          {formatBytes(version.file_size_bytes)}
                                        </span>
                                      </>
                                    ) : null}
                                  </>
                                ) : null}
                              </p>
                            </div>
                          </div>

                          <div className="pl-12 md:pl-0">
                            {versionState?.loading || !versionState ? (
                              <div className="h-4 w-16 animate-pulse rounded bg-elevated" />
                            ) : versionState.error || !version ? (
                              <span className="text-caption text-tertiary">—</span>
                            ) : (
                              <DocumentStatusIndicator status={version.status} />
                            )}
                          </div>

                          <p className="pl-12 text-caption text-secondary md:pl-0 md:text-right">
                            {formatRelativeOrDate(doc.updated_at || doc.created_at)}
                          </p>
                        </Link>
                      </li>
                    );
                  })
                )}
              </ul>
            </div>

            {!loading && !noResultsForFilter && totalPages > 1 ? (
              <div className="flex items-center justify-between">
                <p className="text-caption text-tertiary">
                  Page {page} / {totalPages}
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
                    Previous
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
                    Next
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
