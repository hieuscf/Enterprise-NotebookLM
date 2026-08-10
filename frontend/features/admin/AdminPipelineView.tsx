/**
 * =============================================================================
 * File: AdminPipelineView.tsx
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Pipeline Observability Console at `/admin/pipeline`.
 * Responsibilities:
 *   - Manage-only gate; sync workspace/status/pagination to URL
 *   - Compose overview, runs table, and detail drawer
 *   - Auto-refresh indicator (UI-only poll; no websocket)
 * Dependencies:
 *   - AdminShell, AdminPipelineOverview, AdminPipelineRunsTable,
 *     AdminPipelineRunDrawer, hooks/useAdminPipelineConsole
 * Public Exports:
 *   - AdminPipelineView
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: app/admin/pipeline/page.tsx
 * Important Notes: Stages follow schema v3 (preview + understanding → indexing).
 * =============================================================================
 */

"use client";

import { RefreshCw, ShieldAlert } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminPipelineOverview } from "@/features/admin/AdminPipelineOverview";
import { AdminPipelineRunDrawer } from "@/features/admin/AdminPipelineRunDrawer";
import { AdminPipelineRunsTable } from "@/features/admin/AdminPipelineRunsTable";
import { formatRelativeAgo } from "@/features/admin/admin-pipeline";
import { AdminShell } from "@/features/admin/AdminShell";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAdminPipelineConsole } from "@/hooks/useAdminPipelineConsole";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import type { PipelineRun, PipelineStatus } from "@/types/documents";

const VALID_STATUS = new Set<PipelineStatus>([
  "pending",
  "running",
  "completed",
  "failed",
]);
const VALID_PAGE_SIZES = new Set([10, 20, 50, 100]);
const AUTO_REFRESH_MS = 10_000;

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">
        You don&apos;t have permission to view pipeline observability.
      </h2>
      <p className="max-w-md text-body-sm text-secondary">
        Pipeline monitoring requires Platform <strong>Manage</strong>.
      </p>
    </div>
  );
}

function parseStatus(raw: string | null): PipelineStatus | "" {
  if (!raw) return "";
  return VALID_STATUS.has(raw as PipelineStatus) ? (raw as PipelineStatus) : "";
}

export function AdminPipelineView() {
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
  const statusFilter = parseStatus(searchParams.get("status"));
  const workspaceParam = searchParams.get("workspace") ?? "";

  const [searchInput, setSearchInput] = useState("");
  const [selectedRun, setSelectedRun] = useState<PipelineRun | null>(null);
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
      router.replace(qs ? `/admin/pipeline?${qs}` : "/admin/pipeline", { scroll: false });
    },
    [router, searchParams],
  );

  // Persist default workspace into URL once options load.
  useEffect(() => {
    if (!selectedWorkspaceId) return;
    if (workspaceParam === selectedWorkspaceId) return;
    if (workspaceParam && workspaceOptions.some((w) => w.id === workspaceParam)) return;
    replaceParams({ workspace: selectedWorkspaceId });
  }, [selectedWorkspaceId, workspaceParam, workspaceOptions, replaceParams]);

  const consoleData = useAdminPipelineConsole({
    workspaceId: selectedWorkspaceId || null,
    status: statusFilter || null,
    page,
    pageSize,
    autoRefreshMs: AUTO_REFRESH_MS,
  });

  // Keep relative timestamps fresh.
  useEffect(() => {
    const id = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  // Keep drawer run in sync with refreshed list.
  useEffect(() => {
    if (!selectedRun) return;
    const next = consoleData.runs.find((r) => r.id === selectedRun.id);
    if (next) setSelectedRun(next);
  }, [consoleData.runs, selectedRun]);

  const showUnauthorized = !authLoading && !gateLoading && !isManage;

  const updatedLabel = consoleData.lastUpdatedAt
    ? formatRelativeAgo(new Date(consoleData.lastUpdatedAt).toISOString(), new Date(nowTick))
    : "—";

  function openRun(run: PipelineRun) {
    setSelectedRun(run);
    setDrawerOpen(true);
  }

  return (
    <AdminShell active="pipeline" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-tertiary">
              Admin <span className="text-tertiary">/</span>{" "}
              <span className="text-accent-primary">Pipeline</span>
            </p>
            <h1 className="mt-1 text-h1 text-primary">Pipeline</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Monitor document processing, indexing, and pipeline health.
            </p>
          </div>
          {!showUnauthorized ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-tertiary" aria-live="polite">
                Auto-refresh {AUTO_REFRESH_MS / 1000}s · Updated {updatedLabel}
              </span>
              <button
                type="button"
                onClick={() => void consoleData.reload()}
                disabled={consoleData.loading}
                aria-label="Refresh pipeline runs"
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
            <div className="h-10 animate-pulse rounded-lg border border-border-default bg-surface" />
            <div className="h-24 animate-pulse rounded-lg border border-border-default bg-surface" />
            <div className="h-72 animate-pulse rounded-lg border border-border-default bg-surface" />
          </div>
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : workspaceOptions.length === 0 ? (
          <div className="rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
            <p className="text-body-sm font-medium text-secondary">No workspaces available</p>
            <p className="mt-1 text-caption text-tertiary">
              Create a workspace before monitoring pipeline runs.
            </p>
          </div>
        ) : (
          <>
            <AdminPipelineOverview
              runs={consoleData.overviewRuns}
              sampleCapped={consoleData.overviewSampleCapped}
              loading={consoleData.overviewLoading && consoleData.overviewRuns.length === 0}
              activeStatus={statusFilter || "all"}
              onStatusChange={(status) =>
                replaceParams({
                  status: status === "all" ? null : status,
                  page: "1",
                })
              }
            />

            <AdminPipelineRunsTable
              runs={consoleData.runs}
              page={page}
              pageSize={pageSize}
              hasNextPage={consoleData.hasNextPage}
              loading={consoleData.loading && consoleData.runs.length === 0}
              error={consoleData.error}
              searchQuery={searchInput}
              workspaceId={selectedWorkspaceId}
              workspaceName={workspaceName}
              statusFilter={statusFilter}
              workspaceOptions={workspaceOptions}
              onSearchChange={setSearchInput}
              onWorkspaceChange={(id) =>
                replaceParams({ workspace: id || null, page: "1" })
              }
              onStatusFilterChange={(status) =>
                replaceParams({ status: status || null, page: "1" })
              }
              onPageChange={(p) => replaceParams({ page: String(p) })}
              onPageSizeChange={(size) =>
                replaceParams({ page_size: String(size), page: "1" })
              }
              onRetry={() => void consoleData.reload()}
              onViewDetails={openRun}
              onViewError={openRun}
            />

            <AdminPipelineRunDrawer
              run={selectedRun}
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
