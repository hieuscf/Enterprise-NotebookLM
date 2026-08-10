/**
 * =============================================================================
 * File: AdminQueryLogsTable.tsx
 * Module/Service: Observability / Query Logs Console (Web App) — FR13
 * Layer: UI
 * Purpose: Primary query_logs table — filters, desktop table, mobile cards.
 * Responsibilities:
 *   - Search (current page only), workspace / route_type filters, pagination
 *   - Surface LLM invariant warnings without mutating audit rows
 * Dependencies:
 *   - AdminCard, AdminRowMenu, AdminSectionState, admin-query-logs
 * Public Exports:
 *   - AdminQueryLogsTable
 * Database/Table: query_logs via GET /admin/workspaces/{id}/query-logs
 * Related Modules: AdminQueryLogsView
 * Important Notes: route_type filter is server-side; search filters the loaded
 *   page. Date UI is local-only — API has no date params. Read-only audit log.
 * =============================================================================
 */

"use client";

import { AlertTriangle, ChevronLeft, ChevronRight, Search } from "lucide-react";

import {
  formatFullTs,
  formatLatency,
  formatRelativeAgo,
  hasRoutingInvariantViolation,
  LATENCY_WARN_MS,
  llmCallsHint,
  matchesQueryLogSearch,
  ROUTE_BADGE_CLASS,
  ROUTE_LABEL,
  ROUTE_MARKER,
  ROUTE_ORDER,
  shortId,
  truncateQueryText,
} from "@/features/admin/admin-query-logs";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminRowMenu } from "@/features/admin/AdminRowMenu";
import { SectionEmpty, SectionError } from "@/features/admin/AdminSectionState";
import type { AdminWorkspaceOption } from "@/hooks/useAdminEligibleWorkspaces";
import { cn } from "@/lib/utils";
import type { QueryLogItem } from "@/types/admin";
import type { RouteType } from "@/types/chat";

type RouteFilter = RouteType | "";

type Props = {
  logs: QueryLogItem[];
  page: number;
  pageSize: number;
  hasNextPage: boolean;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  workspaceId: string;
  routeFilter: RouteFilter;
  workspaceOptions: AdminWorkspaceOption[];
  /** Date inputs are presentation-only until the API supports them. */
  dateFrom: string;
  dateTo: string;
  onSearchChange: (value: string) => void;
  onWorkspaceChange: (workspaceId: string) => void;
  onRouteFilterChange: (route: RouteFilter) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onRetry: () => void;
  onViewDetails: (log: QueryLogItem) => void;
};

function RouteBadge({ route }: { route: RouteType }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-semibold",
        ROUTE_BADGE_CLASS[route],
      )}
    >
      <span aria-hidden>{ROUTE_MARKER[route]}</span>
      {ROUTE_LABEL[route]}
    </span>
  );
}

function LlmCell({ log }: { log: QueryLogItem }) {
  const unexpected = hasRoutingInvariantViolation(log);
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="font-mono text-primary">{log.llm_calls_count}</span>
      <span
        className={cn(
          "text-caption",
          unexpected ? "font-medium text-warning" : "text-tertiary",
        )}
      >
        {unexpected ? "Unexpected" : llmCallsHint(log)}
      </span>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="flex flex-col gap-2" role="status" aria-label="Loading query logs">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-12 animate-pulse rounded-md bg-elevated" />
      ))}
    </div>
  );
}

export function AdminQueryLogsTable({
  logs,
  page,
  pageSize,
  hasNextPage,
  loading,
  error,
  searchQuery,
  workspaceId,
  routeFilter,
  workspaceOptions,
  dateFrom,
  dateTo,
  onSearchChange,
  onWorkspaceChange,
  onRouteFilterChange,
  onDateFromChange,
  onDateToChange,
  onPageChange,
  onPageSizeChange,
  onRetry,
  onViewDetails,
}: Props) {
  const filtered = searchQuery.trim()
    ? logs.filter((row) => matchesQueryLogSearch(row, searchQuery))
    : logs;

  const rangeStart = logs.length === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = (page - 1) * pageSize + logs.length;

  return (
    <AdminCard
      headingId="query-logs-table-heading"
      title="Query Logs"
      description="Request-level Query Router audit for the selected workspace."
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
          <label className="relative min-w-0 flex-1 basis-[14rem]">
            <span className="sr-only">Search query text</span>
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
              aria-hidden
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search query text…"
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
            aria-label="Route type"
            value={routeFilter}
            onChange={(e) => onRouteFilterChange(e.target.value as RouteFilter)}
            className="h-10 rounded-md border border-border-default bg-base px-2.5 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
          >
            <option value="">All</option>
            {ROUTE_ORDER.map((route) => (
              <option key={route} value={route}>
                {ROUTE_LABEL[route]}
              </option>
            ))}
          </select>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-caption text-tertiary">
              <span className="sr-only">From date</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => onDateFromChange(e.target.value)}
                aria-label="From date"
                className="h-10 rounded-md border border-border-default bg-base px-2 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
              />
            </label>
            <span className="text-caption text-tertiary" aria-hidden>
              –
            </span>
            <label className="flex items-center gap-1.5 text-caption text-tertiary">
              <span className="sr-only">To date</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => onDateToChange(e.target.value)}
                aria-label="To date"
                className="h-10 rounded-md border border-border-default bg-base px-2 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
              />
            </label>
          </div>
        </div>
        {searchQuery.trim() || dateFrom || dateTo ? (
          <p className="text-caption text-tertiary">
            {searchQuery.trim()
              ? "Search filters the current page only (server search is not available)."
              : null}
            {searchQuery.trim() && (dateFrom || dateTo) ? " · " : null}
            {dateFrom || dateTo
              ? "Date range is UI-only — the query-logs API does not accept date parameters yet."
              : null}
          </p>
        ) : null}

        {loading ? (
          <TableSkeleton />
        ) : error ? (
          <SectionError
            message="Unable to load query logs. We couldn't retrieve query routing data."
            onRetry={onRetry}
            retryLabel="Try again"
          />
        ) : logs.length === 0 ? (
          <SectionEmpty
            title="No query logs"
            description="Query routing activity will appear here when users start interacting with AI Chat."
          />
        ) : filtered.length === 0 ? (
          <SectionEmpty
            title="No matching logs"
            description="Try a different search term or clear filters."
          />
        ) : (
          <>
            {/* Desktop table */}
            <div className="-mx-1 hidden overflow-x-auto md:block">
              <table className="w-full min-w-[920px] border-collapse text-body-sm">
                <thead>
                  <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                    <th className="px-2 py-2 font-medium">Query</th>
                    <th className="px-2 py-2 font-medium">Route</th>
                    <th className="px-2 py-2 text-right font-medium">LLM</th>
                    <th className="hidden px-2 py-2 font-medium lg:table-cell">Model</th>
                    <th className="px-2 py-2 text-right font-medium">Latency</th>
                    <th className="hidden px-2 py-2 font-medium lg:table-cell">User</th>
                    <th className="px-2 py-2 text-right font-medium">Created</th>
                    <th className="px-2 py-2 text-right font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((log) => {
                    const unexpected = hasRoutingInvariantViolation(log);
                    const latencyHigh =
                      log.latency_ms != null && log.latency_ms >= LATENCY_WARN_MS;
                    return (
                      <tr
                        key={log.id}
                        className="cursor-pointer border-b border-border-default last:border-0 hover:bg-elevated/40"
                        onClick={() => onViewDetails(log)}
                      >
                        <td className="max-w-[280px] px-2 py-3">
                          <div className="flex min-w-0 items-start gap-1.5">
                            {unexpected ? (
                              <AlertTriangle
                                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning"
                                aria-label="Routing invariant violation"
                              />
                            ) : null}
                            <span
                              className="truncate text-primary"
                              title={log.query_text}
                            >
                              {truncateQueryText(log.query_text)}
                            </span>
                          </div>
                        </td>
                        <td className="px-2 py-3">
                          <RouteBadge route={log.route_type} />
                        </td>
                        <td className="px-2 py-3 text-right">
                          <LlmCell log={log} />
                        </td>
                        <td className="hidden px-2 py-3 font-mono text-secondary lg:table-cell">
                          {log.model_used ?? "—"}
                        </td>
                        <td
                          className={cn(
                            "whitespace-nowrap px-2 py-3 text-right font-mono",
                            latencyHigh ? "text-warning" : "text-primary",
                          )}
                        >
                          {formatLatency(log.latency_ms)}
                        </td>
                        <td className="hidden px-2 py-3 font-mono text-tertiary lg:table-cell">
                          {shortId(log.user_id)}…
                        </td>
                        <td
                          className="whitespace-nowrap px-2 py-3 text-right text-tertiary"
                          title={formatFullTs(log.created_at)}
                        >
                          {formatRelativeAgo(log.created_at)}
                        </td>
                        <td
                          className="px-2 py-3 text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <AdminRowMenu
                            label={`Actions for query ${shortId(log.id)}`}
                            items={[
                              {
                                key: "details",
                                label: "View details",
                                onSelect: () => onViewDetails(log),
                              },
                            ]}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="flex flex-col gap-2 md:hidden">
              {filtered.map((log) => {
                const unexpected = hasRoutingInvariantViolation(log);
                return (
                  <li key={log.id}>
                    <button
                      type="button"
                      onClick={() => onViewDetails(log)}
                      className="flex w-full flex-col gap-2 rounded-lg border border-border-default px-3 py-3 text-left hover:bg-elevated/40"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <RouteBadge route={log.route_type} />
                        <span className="font-mono text-caption text-tertiary">
                          {formatRelativeAgo(log.created_at)}
                        </span>
                      </div>
                      <p className="line-clamp-2 text-body-sm text-primary">
                        {truncateQueryText(log.query_text, 96)}
                      </p>
                      <div className="flex flex-wrap items-center gap-3 font-mono text-caption text-secondary">
                        <span>
                          {log.llm_calls_count === 0
                            ? "No LLM"
                            : `${log.llm_calls_count} LLM call${log.llm_calls_count === 1 ? "" : "s"}`}
                        </span>
                        <span>{formatLatency(log.latency_ms)}</span>
                        {unexpected ? (
                          <span className="inline-flex items-center gap-1 text-warning">
                            <AlertTriangle className="h-3 w-3" aria-hidden />
                            Unexpected
                          </span>
                        ) : null}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-default pt-3">
              <div className="flex items-center gap-2 text-caption text-tertiary">
                <span>
                  {logs.length === 0
                    ? "0 of —"
                    : `${rangeStart}–${rangeEnd}${hasNextPage ? "+" : ""}`}
                </span>
                <label className="flex items-center gap-1.5">
                  <span>Rows per page</span>
                  <select
                    aria-label="Rows per page"
                    value={pageSize}
                    onChange={(e) => onPageSizeChange(Number(e.target.value))}
                    className="h-8 rounded border border-border-default bg-base px-1.5 text-caption text-primary"
                  >
                    {[20, 50, 100].map((n) => (
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
      </div>
    </AdminCard>
  );
}
