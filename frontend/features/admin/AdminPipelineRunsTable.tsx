/**
 * =============================================================================
 * File: AdminPipelineRunsTable.tsx
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Primary pipeline runs table — filters, desktop table, mobile cards.
 * Responsibilities:
 *   - Search (current page), workspace/status filters, pagination
 *   - Stage progress strip; duration / relative timestamps; row actions
 * Dependencies:
 *   - AdminCard, AdminRowMenu, AdminSectionState, admin-pipeline
 * Public Exports:
 *   - AdminPipelineRunsTable
 * Database/Table: pipeline_runs via GET /admin/workspaces/{id}/pipeline-runs
 * Related Modules: AdminPipelineView
 * Important Notes: Status filter is server-side; search filters the loaded page.
 * =============================================================================
 */

"use client";

import {
  ChevronLeft,
  ChevronRight,
  Search,
} from "lucide-react";
import Link from "next/link";

import {
  currentStageOf,
  documentLabel,
  fileTypeBadge,
  formatFullTs,
  formatRelativeAgo,
  matchesPipelineSearch,
  PIPELINE_STATUS_BADGE_CLASS,
  PIPELINE_STATUS_LABEL,
  pipelineRunDurationLabel,
  stageProgressForRun,
  versionLabel,
} from "@/features/admin/admin-pipeline";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminRowMenu, type AdminRowMenuItem } from "@/features/admin/AdminRowMenu";
import { SectionEmpty, SectionError } from "@/features/admin/AdminSectionState";
import type { AdminWorkspaceOption } from "@/hooks/useAdminEligibleWorkspaces";
import { cn } from "@/lib/utils";
import type { PipelineRun, PipelineStatus } from "@/types/documents";

type StatusFilter = PipelineStatus | "";

type Props = {
  runs: PipelineRun[];
  page: number;
  pageSize: number;
  hasNextPage: boolean;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  workspaceId: string;
  workspaceName: string;
  statusFilter: StatusFilter;
  workspaceOptions: AdminWorkspaceOption[];
  onSearchChange: (value: string) => void;
  onWorkspaceChange: (workspaceId: string) => void;
  onStatusFilterChange: (status: StatusFilter) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onRetry: () => void;
  onViewDetails: (run: PipelineRun) => void;
  onViewError: (run: PipelineRun) => void;
};

function StageProgress({ run }: { run: PipelineRun }) {
  const items = stageProgressForRun(run);
  return (
    <ol
      className="flex flex-wrap items-center gap-x-1 gap-y-0.5"
      aria-label="Pipeline stage progress"
    >
      {items.map((item, i) => (
        <li key={item.stage} className="flex items-center gap-1">
          {i > 0 ? <span className="text-tertiary" aria-hidden>→</span> : null}
          <span
            className={cn(
              "font-mono text-caption",
              item.marker === "completed" && "text-success",
              item.marker === "running" && "font-semibold text-info",
              item.marker === "failed" && "font-semibold text-danger",
              (item.marker === "pending" || item.marker === "skipped") && "text-tertiary",
            )}
            title={`${item.label}: ${item.marker}`}
          >
            {item.marker === "completed" ? "✓ " : null}
            {item.marker === "running" ? "● " : null}
            {item.marker === "failed" ? "✕ " : null}
            {item.marker === "pending" || item.marker === "skipped" ? "○ " : null}
            {item.shortLabel}
          </span>
        </li>
      ))}
    </ol>
  );
}

function TableSkeleton() {
  return (
    <div className="flex flex-col gap-2" role="status" aria-label="Loading pipeline runs">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-12 animate-pulse rounded-md bg-elevated" />
      ))}
    </div>
  );
}

export function AdminPipelineRunsTable({
  runs,
  page,
  pageSize,
  hasNextPage,
  loading,
  error,
  searchQuery,
  workspaceId,
  workspaceName,
  statusFilter,
  workspaceOptions,
  onSearchChange,
  onWorkspaceChange,
  onStatusFilterChange,
  onPageChange,
  onPageSizeChange,
  onRetry,
  onViewDetails,
  onViewError,
}: Props) {
  const filtered = searchQuery.trim()
    ? runs.filter((r) => matchesPipelineSearch(r, searchQuery))
    : runs;

  function menuItems(run: PipelineRun): AdminRowMenuItem[] {
    const items: AdminRowMenuItem[] = [
      {
        key: "details",
        label: "View details",
        onSelect: () => onViewDetails(run),
      },
    ];
    if (run.status === "failed") {
      items.push({
        key: "error",
        label: "View error",
        onSelect: () => onViewError(run),
        destructive: true,
      });
    }
    return items;
  }

  return (
    <AdminCard
      headingId="pipeline-runs-heading"
      title="Pipeline Runs"
      description="Document processing runs for the selected workspace."
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search pipeline runs</span>
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
              aria-hidden
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search document name or run ID…"
              className={cn(
                "h-10 w-full rounded-md border border-border-default bg-base pl-9 pr-3",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            />
          </label>
          <select
            aria-label="Workspace"
            value={workspaceId}
            onChange={(e) => onWorkspaceChange(e.target.value)}
            className="h-10 rounded-md border border-border-default bg-base px-2.5 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
          >
            {workspaceOptions.map((ws) => (
              <option key={ws.id} value={ws.id}>
                {ws.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Status"
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value as StatusFilter)}
            className="h-10 rounded-md border border-border-default bg-base px-2.5 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        {searchQuery.trim() ? (
          <p className="text-caption text-tertiary">
            Search filters the current page only (server search is not available).
          </p>
        ) : null}

        {loading ? (
          <TableSkeleton />
        ) : error ? (
          <SectionError
            message="Unable to load pipeline runs. We couldn't retrieve pipeline processing data."
            onRetry={onRetry}
            retryLabel="Try again"
          />
        ) : runs.length === 0 ? (
          <SectionEmpty
            title="No pipeline runs yet"
            description="Document processing activity will appear here once documents are uploaded and processing begins."
          />
        ) : filtered.length === 0 ? (
          <SectionEmpty
            title="No matching runs"
            description="Try a different search term or clear filters."
          />
        ) : (
          <>
            {/* Desktop table */}
            <div className="-mx-1 hidden overflow-x-auto md:block">
              <table className="w-full min-w-[880px] border-collapse text-body-sm">
                <thead>
                  <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                    <th className="px-2 py-2 font-medium">Document</th>
                    <th className="px-2 py-2 font-medium">Workspace</th>
                    <th className="px-2 py-2 font-medium">Status</th>
                    <th className="px-2 py-2 font-medium">Pipeline</th>
                    <th className="px-2 py-2 text-right font-medium">Duration</th>
                    <th className="hidden px-2 py-2 text-right font-medium lg:table-cell">
                      Started
                    </th>
                    <th className="hidden px-2 py-2 text-right font-medium xl:table-cell">
                      Completed
                    </th>
                    <th className="px-2 py-2 text-right font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((run) => {
                    const ft = fileTypeBadge(run);
                    const current = currentStageOf(run);
                    return (
                      <tr
                        key={run.id}
                        className="cursor-pointer border-b border-border-default last:border-0 hover:bg-elevated/40"
                        onClick={() => onViewDetails(run)}
                      >
                        <td className="px-2 py-3">
                          <div className="flex min-w-0 flex-col gap-0.5">
                            <span className="truncate font-medium text-primary">
                              {documentLabel(run)}
                            </span>
                            <span className="flex items-center gap-1.5 text-caption text-tertiary">
                              <span className="font-mono">{versionLabel(run)}</span>
                              {ft ? (
                                <span className="rounded border border-border-default px-1 font-mono uppercase">
                                  {ft}
                                </span>
                              ) : null}
                            </span>
                          </div>
                        </td>
                        <td className="px-2 py-3 text-secondary">{workspaceName}</td>
                        <td className="px-2 py-3">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-semibold",
                              PIPELINE_STATUS_BADGE_CLASS[run.status],
                            )}
                          >
                            <span aria-hidden>
                              {run.status === "completed"
                                ? "✓"
                                : run.status === "running"
                                  ? "●"
                                  : run.status === "failed"
                                    ? "!"
                                    : "○"}
                            </span>
                            {PIPELINE_STATUS_LABEL[run.status]}
                          </span>
                          {current && run.status === "running" ? (
                            <p className="mt-0.5 text-caption text-tertiary">
                              {current.shortLabel}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-2 py-3">
                          <StageProgress run={run} />
                        </td>
                        <td className="whitespace-nowrap px-2 py-3 text-right font-mono text-primary">
                          {pipelineRunDurationLabel(run)}
                        </td>
                        <td
                          className="hidden whitespace-nowrap px-2 py-3 text-right text-tertiary lg:table-cell"
                          title={formatFullTs(run.started_at)}
                        >
                          {formatRelativeAgo(run.started_at)}
                        </td>
                        <td
                          className="hidden whitespace-nowrap px-2 py-3 text-right text-tertiary xl:table-cell"
                          title={formatFullTs(run.completed_at)}
                        >
                          {run.completed_at ? formatRelativeAgo(run.completed_at) : "—"}
                        </td>
                        <td
                          className="px-2 py-3 text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <AdminRowMenu
                            label={`Actions for ${documentLabel(run)}`}
                            items={menuItems(run)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile stacked list */}
            <ul className="flex flex-col gap-2 md:hidden">
              {filtered.map((run) => {
                const ft = fileTypeBadge(run);
                return (
                  <li key={run.id}>
                    <button
                      type="button"
                      onClick={() => onViewDetails(run)}
                      className="flex w-full flex-col gap-2 rounded-lg border border-border-default px-3 py-3 text-left hover:bg-elevated/40"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-primary">
                            {documentLabel(run)}
                          </p>
                          <p className="text-caption text-tertiary">
                            {versionLabel(run)}
                            {ft ? ` · ${ft.toUpperCase()}` : ""} · {workspaceName}
                          </p>
                        </div>
                        <span
                          className={cn(
                            "shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold",
                            PIPELINE_STATUS_BADGE_CLASS[run.status],
                          )}
                        >
                          {PIPELINE_STATUS_LABEL[run.status]}
                        </span>
                      </div>
                      <StageProgress run={run} />
                      <div className="flex justify-between font-mono text-caption text-tertiary">
                        <span>{pipelineRunDurationLabel(run)}</span>
                        <span>{formatRelativeAgo(run.started_at)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-default pt-3">
              <div className="flex items-center gap-2 text-caption text-tertiary">
                <span>
                  Page {page}
                  {hasNextPage ? "+" : ""}
                </span>
                <select
                  aria-label="Page size"
                  value={pageSize}
                  onChange={(e) => onPageSizeChange(Number(e.target.value))}
                  className="h-8 rounded border border-border-default bg-base px-1.5 text-caption text-primary"
                >
                  {[10, 20, 50, 100].map((n) => (
                    <option key={n} value={n}>
                      {n} / page
                    </option>
                  ))}
                </select>
                {runs.length === 0 && !loading ? (
                  <Link
                    href="/admin/documents"
                    className="text-accent-primary hover:underline"
                  >
                    View documents
                  </Link>
                ) : null}
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label="Previous page"
                  disabled={page <= 1 || loading}
                  onClick={() => onPageChange(page - 1)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border-default text-secondary hover:bg-elevated disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label="Next page"
                  disabled={!hasNextPage || loading}
                  onClick={() => onPageChange(page + 1)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border-default text-secondary hover:bg-elevated disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </button>
              </div>
            </div>
          </>
        )}

        {!loading && !error && runs.length === 0 ? (
          <div className="flex justify-center">
            <Link
              href="/admin/documents"
              className="inline-flex h-9 items-center rounded-md border border-border-default px-3 text-body-sm font-medium text-primary hover:bg-elevated"
            >
              View documents
            </Link>
          </div>
        ) : null}
      </div>
    </AdminCard>
  );
}
