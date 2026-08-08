/**
 * =============================================================================
 * File: AdminWorkspacesTable.tsx
 * Module/Service: Workspace Service (Web App) — FR1 Admin Console
 * Layer: UI
 * Purpose: Compact workspace list table for `/admin/workspaces`, visually
 *          aligned with Admin Dashboard tables (RecentQueriesTable pattern).
 * Responsibilities:
 *   - Render Workspace / Description / Created / Updated / Actions columns
 *   - Skeleton, error+retry, empty, and paginated list states
 *   - Row name links to `/admin/workspaces/[workspaceId]`; action menu for
 *     View / Edit / Delete (Edit/Delete only when parent marks canManage)
 * Dependencies:
 *   - features/admin/AdminCard, AdminSectionState, AdminRowMenu, admin-format
 * Public Exports:
 *   - AdminWorkspacesTable
 * Database/Table: workspaces
 * Related Modules: features/admin/AdminWorkspacesView.tsx
 * Important Notes:
 *   - No member-count column — list API has no aggregate; fetching
 *     /members per row would be an N+1 (explicitly forbidden for this page).
 *   - Schema fields only: id, name, description, created_at, updated_at.
 * =============================================================================
 */

"use client";

import { ChevronLeft, ChevronRight, FolderKanban, Plus, Search } from "lucide-react";
import Link from "next/link";

import { formatDateTimeShort } from "@/features/admin/admin-format";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminRowMenu } from "@/features/admin/AdminRowMenu";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import { cn } from "@/lib/utils";
import type { Workspace } from "@/types/workspaces";

type Props = {
  items: Workspace[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onRetry: () => void;
  onCreate: () => void;
  onView: (workspace: Workspace) => void;
  onEdit: (workspace: Workspace) => void;
  onDelete: (workspace: Workspace) => void;
  /** True when the signed-in user is admin of that workspace (FR12 UI gate). */
  canManage: (workspaceId: string) => boolean;
  canCreate: boolean;
};

function rangeLabel(page: number, pageSize: number, total: number): string {
  if (total === 0) return "Showing 0 of 0";
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `Showing ${from}–${to} of ${total}`;
}

export function AdminWorkspacesTable({
  items,
  total,
  page,
  pageSize,
  loading,
  error,
  searchQuery,
  onSearchChange,
  onPageChange,
  onRetry,
  onCreate,
  onView,
  onEdit,
  onDelete,
  canManage,
  canCreate,
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const showEmpty = !loading && !error && total === 0 && !searchQuery.trim();
  const showNoSearchMatch =
    !loading && !error && items.length === 0 && Boolean(searchQuery.trim());

  return (
    <AdminCard
      headingId="admin-workspaces-table"
      title="Workspace list"
      description="Workspaces you can access. Edit and delete require workspace admin."
    >
      {!showEmpty ? (
        <div className="relative w-full max-w-sm">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
            aria-hidden
          />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search workspaces..."
            aria-label="Search workspaces"
            className={cn(
              "h-9 w-full rounded-md border border-border-default bg-base pl-9 pr-3",
              "text-body-sm text-primary placeholder:text-tertiary",
              "outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
            )}
          />
          {/*
            TODO(limitation): OpenAPI GET /workspaces only exposes page + page_size —
            no ?q= / ?search=. Client-side filter applies to the current page only.
            Do not invent server query params until the contract adds them.
          */}
        </div>
      ) : null}

      {loading ? (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                <th className="px-1 py-2 font-medium">Workspace</th>
                <th className="px-1 py-2 font-medium">Description</th>
                <th className="px-1 py-2 font-medium">Created</th>
                <th className="px-1 py-2 font-medium">Updated</th>
                <th className="px-1 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={5} className="px-1 py-3">
                  <SectionSkeleton rows={5} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : showEmpty ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent-primary-soft">
            <FolderKanban className="h-6 w-6 text-accent-primary" aria-hidden />
          </span>
          <SectionEmpty
            title="No workspaces yet."
            description="Create your first workspace to start organizing documents, users and knowledge."
          />
          {canCreate ? (
            <button
              type="button"
              onClick={onCreate}
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white hover:bg-accent-primary-hover",
              )}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Create Workspace
            </button>
          ) : null}
        </div>
      ) : showNoSearchMatch ? (
        <SectionEmpty
          title="No matching workspaces on this page."
          description={`No results for “${searchQuery.trim()}”. Search only filters the current page until the API supports server-side search.`}
        />
      ) : (
        <>
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-body-sm">
              <thead>
                <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                  <th className="px-1 py-2 font-medium">Workspace</th>
                  <th className="px-1 py-2 font-medium">Description</th>
                  <th className="px-1 py-2 font-medium">Created</th>
                  <th className="px-1 py-2 font-medium">Updated</th>
                  <th className="px-1 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((ws) => {
                  const manage = canManage(ws.id);
                  return (
                    <tr key={ws.id} className="border-b border-border-default last:border-0">
                      <td className="max-w-[200px] px-1 py-2.5">
                        <Link
                          href={`/admin/workspaces/${ws.id}`}
                          className="font-medium text-primary hover:text-accent-primary focus-visible:outline-none focus-visible:underline"
                        >
                          {ws.name}
                        </Link>
                      </td>
                      <td className="max-w-[280px] truncate px-1 py-2.5 text-secondary">
                        {ws.description?.trim() ? ws.description : "—"}
                      </td>
                      <td className="whitespace-nowrap px-1 py-2.5 text-tertiary">
                        {formatDateTimeShort(ws.created_at)}
                      </td>
                      <td className="whitespace-nowrap px-1 py-2.5 text-tertiary">
                        {formatDateTimeShort(ws.updated_at)}
                      </td>
                      <td className="px-1 py-2.5 text-right">
                        <AdminRowMenu
                          label={`Actions for ${ws.name}`}
                          items={[
                            {
                              key: "view",
                              label: "View",
                              onSelect: () => onView(ws),
                            },
                            ...(manage
                              ? [
                                  {
                                    key: "edit",
                                    label: "Edit",
                                    onSelect: () => onEdit(ws),
                                  },
                                  {
                                    key: "delete",
                                    label: "Delete",
                                    destructive: true,
                                    onSelect: () => onDelete(ws),
                                  },
                                ]
                              : []),
                          ]}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-caption text-tertiary">{rangeLabel(page, pageSize, total)}</p>
            {totalPages > 1 ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => onPageChange(Math.max(1, page - 1))}
                  className={cn(
                    "flex h-9 items-center gap-1 rounded-md border border-border-default px-3",
                    "text-body-sm font-medium text-secondary hover:bg-elevated",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                  )}
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                  Previous
                </button>
                <span className="text-caption text-tertiary">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => onPageChange(Math.min(totalPages, page + 1))}
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
            ) : null}
          </div>
        </>
      )}
    </AdminCard>
  );
}
