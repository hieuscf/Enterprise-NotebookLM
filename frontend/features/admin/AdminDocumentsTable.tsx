/**
 * =============================================================================
 * File: AdminDocumentsTable.tsx
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Primary data table for `/admin/documents` — filters, sort, pagination.
 * Responsibilities:
 *   - Render Document / Workspace / Type / Version / Size / Pages / Status / Updated
 *   - Skeleton, error, empty, no-results states
 *   - Row menu: View details, View workspace, View versions, View pipeline
 * Dependencies:
 *   - AdminCard, AdminRowMenu, AdminSectionState, admin-documents, FileTypeIcon
 * Public Exports:
 *   - AdminDocumentsTable
 * Database/Table: documents via GET /admin/documents
 * Related Modules: features/admin/AdminDocumentsView
 * Important Notes: Server-side pagination only — never filters a full dataset.
 * =============================================================================
 */

"use client";

import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  FILE_TYPE_LABEL,
  VERSION_STATUS_CLASS,
  VERSION_STATUS_LABEL,
  VERSION_STATUS_MARKER,
  formatAdminFileSize,
  formatFullTimestamp,
  formatRelativeUpdated,
} from "@/features/admin/admin-documents";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminRowMenu, type AdminRowMenuItem } from "@/features/admin/AdminRowMenu";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import type { AdminWorkspaceOption } from "@/hooks/useAdminEligibleWorkspaces";
import { cn } from "@/lib/utils";
import type { AdminDocumentListItem, AdminDocumentSort, AdminDocumentSortOrder } from "@/types/admin";
import type { DocumentVersionStatus, FileType } from "@/types/documents";

type Props = {
  items: AdminDocumentListItem[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  workspaceFilter: string;
  statusFilter: DocumentVersionStatus | "";
  fileTypeFilter: FileType | "";
  sort: AdminDocumentSort;
  order: AdminDocumentSortOrder;
  workspaceOptions: AdminWorkspaceOption[];
  onSearchChange: (value: string) => void;
  onWorkspaceFilterChange: (workspaceId: string) => void;
  onStatusFilterChange: (status: DocumentVersionStatus | "") => void;
  onFileTypeFilterChange: (fileType: FileType | "") => void;
  onSortChange: (sort: AdminDocumentSort) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onClearFilters: () => void;
  onRetry: () => void;
  onViewDetails: (doc: AdminDocumentListItem) => void;
  onViewVersions: (doc: AdminDocumentListItem) => void;
  onViewPipeline: (doc: AdminDocumentListItem) => void;
};

function rangeLabel(page: number, pageSize: number, total: number): string {
  if (total === 0) return "0 of 0";
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `${from}–${to} of ${total.toLocaleString("en-US")}`;
}

function SortButton({
  label,
  field,
  sort,
  order,
  onSortChange,
}: {
  label: string;
  field: AdminDocumentSort;
  sort: AdminDocumentSort;
  order: AdminDocumentSortOrder;
  onSortChange: (sort: AdminDocumentSort) => void;
}) {
  const active = sort === field || (field === "title" && sort === "name");
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={() => onSortChange(field)}
      className={cn(
        "inline-flex items-center gap-1 font-medium",
        active ? "text-primary" : "text-tertiary hover:text-secondary",
      )}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <Icon className="h-3.5 w-3.5" aria-hidden />
    </button>
  );
}

function StatusCell({ status }: { status: DocumentVersionStatus | null }) {
  if (!status) {
    return <span className="text-tertiary">—</span>;
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-body-sm font-medium",
        VERSION_STATUS_CLASS[status],
      )}
      aria-label={`Status: ${VERSION_STATUS_LABEL[status]}`}
    >
      <span aria-hidden>{VERSION_STATUS_MARKER[status]}</span>
      {VERSION_STATUS_LABEL[status]}
    </span>
  );
}

export function AdminDocumentsTable({
  items,
  total,
  page,
  pageSize,
  loading,
  error,
  searchQuery,
  workspaceFilter,
  statusFilter,
  fileTypeFilter,
  sort,
  order,
  workspaceOptions,
  onSearchChange,
  onWorkspaceFilterChange,
  onStatusFilterChange,
  onFileTypeFilterChange,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onClearFilters,
  onRetry,
  onViewDetails,
  onViewVersions,
  onViewPipeline,
}: Props) {
  const router = useRouter();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const hasFilters =
    Boolean(searchQuery.trim()) ||
    Boolean(workspaceFilter) ||
    Boolean(statusFilter) ||
    Boolean(fileTypeFilter);
  const showEmpty = !loading && !error && total === 0 && !hasFilters;
  const showNoMatch = !loading && !error && items.length === 0 && hasFilters;

  function rowMenuItems(doc: AdminDocumentListItem): AdminRowMenuItem[] {
    return [
      {
        key: "details",
        label: "View details",
        onSelect: () => onViewDetails(doc),
      },
      {
        key: "workspace",
        label: "View workspace",
        onSelect: () => {
          router.push(`/admin/workspaces/${doc.workspace_id}`);
        },
      },
      {
        key: "versions",
        label: "View versions",
        onSelect: () => onViewVersions(doc),
      },
      {
        key: "pipeline",
        label: "View pipeline",
        onSelect: () => onViewPipeline(doc),
        disabled: !doc.current_version_id,
        title: !doc.current_version_id
          ? "No current version to inspect pipeline for."
          : undefined,
      },
    ];
  }

  return (
    <AdminCard
      headingId="admin-documents-table"
      title="Documents"
      description="Enterprise document inventory across all workspaces."
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center">
          <div className="relative w-full max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
              aria-hidden
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search documents..."
              aria-label="Search documents"
              className={cn(
                "h-9 w-full rounded-md border border-border-default bg-base pl-9 pr-3",
                "text-body-sm text-primary placeholder:text-tertiary",
                "outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            />
          </div>

          <label className="flex items-center gap-2 text-body-sm text-secondary">
            <span className="sr-only">Filter by workspace</span>
            <select
              value={workspaceFilter}
              onChange={(e) => onWorkspaceFilterChange(e.target.value)}
              aria-label="Filter by workspace"
              className={cn(
                "h-9 min-w-[10rem] cursor-pointer rounded-md border border-border-default bg-base px-2.5",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            >
              <option value="">All Workspaces</option>
              {workspaceOptions.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-body-sm text-secondary">
            <span className="sr-only">Filter by status</span>
            <select
              value={statusFilter}
              onChange={(e) =>
                onStatusFilterChange(e.target.value as DocumentVersionStatus | "")
              }
              aria-label="Filter by status"
              className={cn(
                "h-9 min-w-[8rem] cursor-pointer rounded-md border border-border-default bg-base px-2.5",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            >
              <option value="">All statuses</option>
              <option value="processing">Processing</option>
              <option value="ready">Ready</option>
              <option value="failed">Failed</option>
            </select>
          </label>

          <label className="flex items-center gap-2 text-body-sm text-secondary">
            <span className="sr-only">Filter by file type</span>
            <select
              value={fileTypeFilter}
              onChange={(e) => onFileTypeFilterChange(e.target.value as FileType | "")}
              aria-label="Filter by file type"
              className={cn(
                "h-9 min-w-[7rem] cursor-pointer rounded-md border border-border-default bg-base px-2.5",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            >
              <option value="">All types</option>
              {(Object.keys(FILE_TYPE_LABEL) as FileType[]).map((ft) => (
                <option key={ft} value={ft}>
                  {FILE_TYPE_LABEL[ft]}
                </option>
              ))}
            </select>
          </label>

          {hasFilters ? (
            <button
              type="button"
              onClick={onClearFilters}
              className="h-9 rounded-md px-2 text-body-sm font-medium text-secondary hover:text-primary"
            >
              Clear filters
            </button>
          ) : null}
        </div>

        {loading ? (
          <SectionSkeleton rows={6} />
        ) : error ? (
          <SectionError message={error} onRetry={onRetry} />
        ) : showEmpty ? (
          <SectionEmpty
            title="No documents yet"
            description="Documents uploaded to workspaces will appear here."
          />
        ) : showNoMatch ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <SectionEmpty
              title="No documents found"
              description="There are no documents matching the current filters."
            />
            <button
              type="button"
              onClick={onClearFilters}
              className="text-body-sm font-medium text-accent-primary hover:underline"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-md border border-border-default">
              <table className="w-full min-w-[64rem] border-collapse text-left text-body-sm">
                <thead className="sticky top-0 z-10 bg-elevated/95 backdrop-blur-sm">
                  <tr className="border-b border-border-default text-caption font-semibold uppercase tracking-wider text-tertiary">
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      <SortButton
                        label="Document"
                        field="title"
                        sort={sort}
                        order={order}
                        onSortChange={onSortChange}
                      />
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      Workspace
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      Type
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      Version
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      <SortButton
                        label="Size"
                        field="size"
                        sort={sort}
                        order={order}
                        onSortChange={onSortChange}
                      />
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      Pages
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      <SortButton
                        label="Status"
                        field="status"
                        sort={sort}
                        order={order}
                        onSortChange={onSortChange}
                      />
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">
                      <SortButton
                        label="Updated"
                        field="updated_at"
                        sort={sort}
                        order={order}
                        onSortChange={onSortChange}
                      />
                    </th>
                    <th scope="col" className="px-3 py-2.5 text-right font-semibold">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((doc) => {
                    const secondary = doc.filename || doc.id.slice(0, 8);
                    return (
                      <tr
                        key={doc.id}
                        className={cn(
                          "border-b border-border-default/70 last:border-0",
                          "hover:bg-elevated/60",
                          doc.status === "failed" && "bg-danger-soft/30",
                        )}
                      >
                        <td className="px-3 py-2.5">
                          <Link
                            href={`/admin/documents/${doc.id}`}
                            className="group flex min-w-0 items-start gap-2.5"
                          >
                            <FileTypeIcon fileType={doc.file_type} className="mt-0.5" />
                            <span className="min-w-0">
                              <span
                                className="block truncate font-medium text-primary group-hover:text-accent-primary"
                                title={doc.title}
                              >
                                {doc.title}
                              </span>
                              <span
                                className="block truncate text-caption text-tertiary"
                                title={secondary}
                              >
                                {secondary}
                              </span>
                            </span>
                          </Link>
                        </td>
                        <td className="px-3 py-2.5">
                          <Link
                            href={`/admin/workspaces/${doc.workspace_id}`}
                            className="text-primary hover:text-accent-primary"
                            title={doc.workspace_id}
                          >
                            {doc.workspace_name}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="inline-flex rounded border border-border-default bg-base px-1.5 py-0.5 text-caption font-semibold uppercase tracking-wide text-secondary">
                            {FILE_TYPE_LABEL[doc.file_type]}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 tabular-nums text-secondary">
                          {doc.version_number != null ? (
                            <button
                              type="button"
                              onClick={() => onViewVersions(doc)}
                              className="font-medium text-primary hover:text-accent-primary"
                              aria-label={`View version history for ${doc.title}`}
                            >
                              v{doc.version_number}
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3 py-2.5 tabular-nums text-secondary">
                          {formatAdminFileSize(doc.file_size_bytes)}
                        </td>
                        <td className="px-3 py-2.5 tabular-nums text-secondary">
                          {doc.page_count != null ? doc.page_count : "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <StatusCell status={doc.status} />
                        </td>
                        <td className="px-3 py-2.5 text-secondary">
                          <time
                            dateTime={doc.updated_at}
                            title={formatFullTimestamp(doc.updated_at)}
                          >
                            {formatRelativeUpdated(doc.updated_at)}
                          </time>
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <AdminRowMenu
                            label={`Actions for ${doc.title}`}
                            items={rowMenuItems(doc)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3 text-body-sm text-secondary">
                <span>{rangeLabel(page, pageSize, total)}</span>
                <label className="flex items-center gap-2">
                  <span className="text-tertiary">Rows</span>
                  <select
                    value={pageSize}
                    onChange={(e) => onPageSizeChange(Number(e.target.value))}
                    aria-label="Rows per page"
                    className={cn(
                      "h-8 cursor-pointer rounded-md border border-border-default bg-base px-2",
                      "text-body-sm text-primary outline-none",
                      "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                    )}
                  >
                    {[10, 20, 50, 100].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onPageChange(page - 1)}
                  disabled={page <= 1}
                  aria-label="Previous page"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-secondary hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                </button>
                <span className="min-w-[4.5rem] text-center text-body-sm text-secondary">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => onPageChange(page + 1)}
                  disabled={page >= totalPages}
                  aria-label="Next page"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-secondary hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={onRetry}
                  aria-label="Refresh documents"
                  className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-md text-secondary hover:bg-elevated"
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </AdminCard>
  );
}
