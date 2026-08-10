/**
 * =============================================================================
 * File: AdminDocumentsView.tsx
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Global Document Operations Console at `/admin/documents`.
 * Responsibilities:
 *   - Manage-only gate; sync filters/pagination to URL search params
 *   - Debounced server search; metrics + table; navigate to detail
 * Dependencies:
 *   - AdminShell, AdminDocumentsMetrics, AdminDocumentsTable
 *   - hooks/useAdminDocuments, useAdminEligibleWorkspaces, useAuth
 * Public Exports:
 *   - AdminDocumentsView
 * Database/Table: documents via GET /admin/documents
 * Related Modules: app/admin/documents/page.tsx
 * Important Notes: No Upload CTA — ingestion remains workspace-scoped.
 * =============================================================================
 */

"use client";

import { RefreshCw, ShieldAlert } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminDocumentsMetrics } from "@/features/admin/AdminDocumentsMetrics";
import { AdminDocumentsTable } from "@/features/admin/AdminDocumentsTable";
import { AdminShell } from "@/features/admin/AdminShell";
import { useAdminDocuments } from "@/hooks/useAdminDocuments";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAuth } from "@/hooks/useAuth";
import type { AdminDocumentListItem, AdminDocumentSort, AdminDocumentSortOrder } from "@/types/admin";
import type { DocumentVersionStatus, FileType } from "@/types/documents";

const VALID_STATUS = new Set<DocumentVersionStatus>(["processing", "ready", "failed"]);
const VALID_FILE_TYPE = new Set<FileType>(["pdf", "docx", "xlsx", "pptx", "txt"]);
const VALID_SORT = new Set<AdminDocumentSort>([
  "updated_at",
  "title",
  "size",
  "status",
  "name",
]);
const VALID_PAGE_SIZES = new Set([10, 20, 50, 100]);

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">You don&apos;t have permission to view documents.</h2>
      <p className="max-w-md text-body-sm text-secondary">
        Global document management requires Platform <strong>Manage</strong>. Workspace Admin
        manages documents inside each workspace.
      </p>
    </div>
  );
}

function parseStatus(raw: string | null): DocumentVersionStatus | "" {
  if (!raw) return "";
  return VALID_STATUS.has(raw as DocumentVersionStatus)
    ? (raw as DocumentVersionStatus)
    : "";
}

function parseFileType(raw: string | null): FileType | "" {
  if (!raw) return "";
  return VALID_FILE_TYPE.has(raw as FileType) ? (raw as FileType) : "";
}

function parseSort(raw: string | null): AdminDocumentSort {
  if (raw && VALID_SORT.has(raw as AdminDocumentSort)) {
    return raw as AdminDocumentSort;
  }
  return "updated_at";
}

function parseOrder(raw: string | null): AdminDocumentSortOrder {
  return raw === "asc" ? "asc" : "desc";
}

export function AdminDocumentsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const { options: workspaceOptions, isManage, loading: gateLoading } =
    useAdminEligibleWorkspaces();

  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const pageSizeRaw = Number(searchParams.get("page_size") ?? "20") || 20;
  const pageSize = VALID_PAGE_SIZES.has(pageSizeRaw) ? pageSizeRaw : 20;
  const workspaceFilter = searchParams.get("workspace") ?? "";
  const statusFilter = parseStatus(searchParams.get("status"));
  const fileTypeFilter = parseFileType(searchParams.get("file_type"));
  const sort = parseSort(searchParams.get("sort"));
  const order = parseOrder(searchParams.get("order"));
  const urlSearch = searchParams.get("q") ?? "";

  const [searchInput, setSearchInput] = useState(urlSearch);
  const [debouncedSearch, setDebouncedSearch] = useState(urlSearch);

  useEffect(() => {
    setSearchInput(urlSearch);
    setDebouncedSearch(urlSearch);
  }, [urlSearch]);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const replaceParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      const qs = next.toString();
      router.replace(qs ? `/admin/documents?${qs}` : "/admin/documents", { scroll: false });
    },
    [router, searchParams],
  );

  // Sync debounced search into URL (resets page).
  useEffect(() => {
    if (debouncedSearch === urlSearch) return;
    replaceParams({ q: debouncedSearch || null, page: "1" });
  }, [debouncedSearch, urlSearch, replaceParams]);

  const listParams = useMemo(
    () => ({
      page,
      pageSize,
      workspaceId: workspaceFilter || null,
      status: statusFilter || null,
      fileType: fileTypeFilter || null,
      search: debouncedSearch || null,
      sort,
      order,
    }),
    [
      page,
      pageSize,
      workspaceFilter,
      statusFilter,
      fileTypeFilter,
      debouncedSearch,
      sort,
      order,
    ],
  );

  const { items, summary, total, loading, error, reload, isManage: docsManage } =
    useAdminDocuments(listParams);

  const showUnauthorized = !authLoading && !gateLoading && !isManage;

  // Light polling while any visible row is processing.
  useEffect(() => {
    if (!docsManage || loading || error) return;
    const hasProcessing = items.some((d) => d.status === "processing");
    if (!hasProcessing) return;
    const id = window.setInterval(() => {
      void reload();
    }, 15_000);
    return () => window.clearInterval(id);
  }, [docsManage, loading, error, items, reload]);

  function clearFilters() {
    setSearchInput("");
    setDebouncedSearch("");
    router.replace("/admin/documents", { scroll: false });
  }

  function handleSortChange(field: AdminDocumentSort) {
    if (sort === field || (field === "title" && sort === "name")) {
      replaceParams({ order: order === "asc" ? "desc" : "asc", page: "1" });
      return;
    }
    replaceParams({
      sort: field,
      order: field === "title" || field === "name" ? "asc" : "desc",
      page: "1",
    });
  }

  function goDetail(doc: AdminDocumentListItem, hash?: string) {
    const suffix = hash ? `#${hash}` : "";
    router.push(`/admin/documents/${doc.id}${suffix}`);
  }

  return (
    <AdminShell active="documents" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">
              FR2 · Document Operations
            </p>
            <h1 className="mt-1 text-h1 text-primary">Documents</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Global document management across the enterprise
            </p>
          </div>
          {!showUnauthorized ? (
            <button
              type="button"
              onClick={() => void reload()}
              disabled={loading}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border-default bg-surface px-4 text-body-sm font-medium text-primary hover:bg-elevated disabled:opacity-50"
            >
              <RefreshCw
                className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
                aria-hidden
              />
              Refresh
            </button>
          ) : null}
        </div>

        {authLoading || gateLoading ? (
          <div className="flex flex-col gap-4">
            <div className="h-20 animate-pulse rounded-lg border border-border-default bg-surface" />
            <div className="h-64 animate-pulse rounded-lg border border-border-default bg-surface" />
          </div>
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : (
          <>
            <AdminDocumentsMetrics
              summary={summary}
              loading={loading}
              activeStatus={statusFilter}
              onStatusClick={(status) =>
                replaceParams({
                  status: status || null,
                  page: "1",
                })
              }
            />

            <AdminDocumentsTable
              items={items}
              total={total}
              page={page}
              pageSize={pageSize}
              loading={loading}
              error={error}
              searchQuery={searchInput}
              workspaceFilter={workspaceFilter}
              statusFilter={statusFilter}
              fileTypeFilter={fileTypeFilter}
              sort={sort}
              order={order}
              workspaceOptions={workspaceOptions}
              onSearchChange={setSearchInput}
              onWorkspaceFilterChange={(id) =>
                replaceParams({ workspace: id || null, page: "1" })
              }
              onStatusFilterChange={(status) =>
                replaceParams({ status: status || null, page: "1" })
              }
              onFileTypeFilterChange={(ft) =>
                replaceParams({ file_type: ft || null, page: "1" })
              }
              onSortChange={handleSortChange}
              onPageChange={(p) => replaceParams({ page: String(p) })}
              onPageSizeChange={(size) =>
                replaceParams({ page_size: String(size), page: "1" })
              }
              onClearFilters={clearFilters}
              onRetry={() => void reload()}
              onViewDetails={(doc) => goDetail(doc)}
              onViewVersions={(doc) => goDetail(doc, "versions")}
              onViewPipeline={(doc) => goDetail(doc, "pipeline")}
            />
          </>
        )}
      </div>
    </AdminShell>
  );
}
