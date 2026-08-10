/**
 * =============================================================================
 * File: AdminQueryLogsView.tsx
 * Module/Service: Observability / Query Logs Console (Web App) — FR13
 * Layer: UI
 * Purpose: Query Router Observability & Cost Audit console at `/admin/query-logs`.
 * Responsibilities:
 *   - Manage-only gate; sync workspace/route/pagination to URL
 *   - Compose overview, logs table, and detail drawer
 *   - Manual refresh with relative “Updated” label (no fake realtime)
 * Dependencies:
 *   - AdminShell, AdminQueryLogsOverview, AdminQueryLogsTable,
 *     AdminQueryLogDrawer, hooks/useAdminQueryLogsConsole
 * Public Exports:
 *   - AdminQueryLogsView
 * Database/Table: query_logs
 * Related Modules: app/admin/query-logs/page.tsx
 * Important Notes: Query logs are read-only audit data — not chat history,
 *   not search_history, not a full cost dashboard.
 * =============================================================================
 */

"use client";

import { RefreshCw, ShieldAlert } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { formatRelativeAgo } from "@/features/admin/admin-query-logs";
import { AdminQueryLogDrawer } from "@/features/admin/AdminQueryLogDrawer";
import { AdminQueryLogsOverview } from "@/features/admin/AdminQueryLogsOverview";
import { AdminQueryLogsTable } from "@/features/admin/AdminQueryLogsTable";
import { AdminShell } from "@/features/admin/AdminShell";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAdminQueryLogsConsole } from "@/hooks/useAdminQueryLogsConsole";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import type { QueryLogItem } from "@/types/admin";
import type { RouteType } from "@/types/chat";

const VALID_ROUTES = new Set<RouteType>([
  "cache_hit",
  "metadata",
  "factoid",
  "complex",
]);
const VALID_PAGE_SIZES = new Set([20, 50, 100]);

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">
        You don&apos;t have permission to view query logs.
      </h2>
      <p className="max-w-md text-body-sm text-secondary">
        Query Router observability requires Platform <strong>Manage</strong>.
      </p>
    </div>
  );
}

function parseRoute(raw: string | null): RouteType | "" {
  if (!raw) return "";
  return VALID_ROUTES.has(raw as RouteType) ? (raw as RouteType) : "";
}

export function AdminQueryLogsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const {
    options: workspaceOptions,
    isManage,
    loading: gateLoading,
  } = useAdminEligibleWorkspaces();

  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const pageSizeRaw = Number(searchParams.get("page_size") ?? "20") || 20;
  const pageSize = VALID_PAGE_SIZES.has(pageSizeRaw) ? pageSizeRaw : 20;
  const routeFilter = parseRoute(searchParams.get("route_type"));
  const workspaceParam = searchParams.get("workspace") ?? "";

  const [searchInput, setSearchInput] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedLog, setSelectedLog] = useState<QueryLogItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const selectedWorkspaceId = useMemo(() => {
    if (workspaceParam && workspaceOptions.some((w) => w.id === workspaceParam)) {
      return workspaceParam;
    }
    return workspaceOptions[0]?.id ?? "";
  }, [workspaceParam, workspaceOptions]);

  const workspaceName =
    workspaceOptions.find((w) => w.id === selectedWorkspaceId)?.name ?? "Workspace";

  const replaceParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      const qs = next.toString();
      router.replace(qs ? `/admin/query-logs?${qs}` : "/admin/query-logs", {
        scroll: false,
      });
    },
    [router, searchParams],
  );

  useEffect(() => {
    if (!selectedWorkspaceId) return;
    if (workspaceParam === selectedWorkspaceId) return;
    if (workspaceParam && workspaceOptions.some((w) => w.id === workspaceParam)) {
      return;
    }
    replaceParams({ workspace: selectedWorkspaceId });
  }, [selectedWorkspaceId, workspaceParam, workspaceOptions, replaceParams]);

  const consoleData = useAdminQueryLogsConsole({
    workspaceId: selectedWorkspaceId || null,
    routeType: routeFilter || null,
    page,
    pageSize,
  });

  useEffect(() => {
    const id = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selectedLog) return;
    const next = consoleData.logs.find((row) => row.id === selectedLog.id);
    if (next) setSelectedLog(next);
  }, [consoleData.logs, selectedLog]);

  const showUnauthorized = !authLoading && !gateLoading && !isManage;

  const updatedLabel = consoleData.lastUpdatedAt
    ? formatRelativeAgo(
        new Date(consoleData.lastUpdatedAt).toISOString(),
        new Date(nowTick),
      )
    : "—";

  function openLog(log: QueryLogItem) {
    setSelectedLog(log);
    setDrawerOpen(true);
  }

  return (
    <AdminShell active="query-logs" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-tertiary">
              Admin <span className="text-tertiary">/</span>{" "}
              <span className="text-accent-primary">Query Logs</span>
            </p>
            <h1 className="mt-1 text-h1 text-primary">Query Logs</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Audit query routing, LLM usage, and query latency.
            </p>
          </div>
          {!showUnauthorized ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-tertiary" aria-live="polite">
                Updated {updatedLabel}
              </span>
              <button
                type="button"
                onClick={() => void consoleData.reload()}
                disabled={consoleData.loading}
                aria-label="Refresh query logs"
                className={cn(
                  "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border-default bg-surface px-4",
                  "text-body-sm font-medium text-primary hover:bg-elevated disabled:opacity-50",
                )}
              >
                <RefreshCw
                  className={cn("h-4 w-4", consoleData.loading && "animate-spin")}
                  aria-hidden
                />
                Refresh
              </button>
            </div>
          ) : null}
        </div>

        {authLoading || gateLoading ? (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-24 animate-pulse rounded-lg border border-border-default bg-surface"
                />
              ))}
            </div>
            <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
            <div className="h-72 animate-pulse rounded-lg border border-border-default bg-surface" />
          </div>
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : workspaceOptions.length === 0 ? (
          <div className="rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
            <p className="text-body-sm font-medium text-secondary">
              No workspaces available
            </p>
            <p className="mt-1 text-caption text-tertiary">
              Create a workspace before auditing query routing.
            </p>
          </div>
        ) : (
          <>
            <AdminQueryLogsOverview
              logs={consoleData.overviewLogs}
              sampleCapped={consoleData.overviewSampleCapped}
              loading={
                consoleData.overviewLoading && consoleData.overviewLogs.length === 0
              }
              activeRoute={routeFilter || "all"}
              onRouteChange={(route) =>
                replaceParams({
                  route_type: route === "all" ? null : route,
                  page: "1",
                })
              }
            />

            <AdminQueryLogsTable
              logs={consoleData.logs}
              page={page}
              pageSize={pageSize}
              hasNextPage={consoleData.hasNextPage}
              loading={consoleData.loading && consoleData.logs.length === 0}
              error={consoleData.error}
              searchQuery={searchInput}
              workspaceId={selectedWorkspaceId}
              routeFilter={routeFilter}
              workspaceOptions={workspaceOptions}
              dateFrom={dateFrom}
              dateTo={dateTo}
              onSearchChange={setSearchInput}
              onWorkspaceChange={(id) =>
                replaceParams({ workspace: id || null, page: "1" })
              }
              onRouteFilterChange={(route) =>
                replaceParams({ route_type: route || null, page: "1" })
              }
              onDateFromChange={setDateFrom}
              onDateToChange={setDateTo}
              onPageChange={(p) => replaceParams({ page: String(p) })}
              onPageSizeChange={(size) =>
                replaceParams({ page_size: String(size), page: "1" })
              }
              onRetry={() => void consoleData.reload()}
              onViewDetails={openLog}
            />

            <AdminQueryLogDrawer
              log={selectedLog}
              workspaceId={selectedWorkspaceId}
              workspaceName={workspaceName}
              open={drawerOpen}
              onClose={() => setDrawerOpen(false)}
            />
          </>
        )}
      </div>
    </AdminShell>
  );
}
