/**
 * =============================================================================
 * File: AdminDashboardView.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Admin Control Center — `/admin/dashboard` (Admin Dashboard task).
 *          Composes KPI, System Health, Query Routing, Pipeline Health,
 *          Usage & Cost, Recent Query Activity and Recent Pipeline Activity
 *          using the dedicated AdminShell, design tokens and the real
 *          Admin/Observability contract (query-logs, pipeline-runs,
 *          cost-summary) — no new backend endpoints, no fake data.
 * Responsibilities:
 *   - RBAC gate: only render admin data for workspaces where the signed-in
 *     user's role is "admin" (per /auth/me memberships); block real page
 *     content (not just hide a menu item) when the user has none
 *   - Own workspace selector + date-range state; fan out independent,
 *     parallel fetches per section so one failing section never blanks others
 * Dependencies:
 *   - features/admin/AdminShell, hooks/useAuth, hooks/useAdminEligibleWorkspaces,
 *     hooks/useAdminCostSummary, hooks/useAdminQueryLogs,
 *     hooks/useAdminPipelineRuns, hooks/useWorkspaceMembers, hooks/useDocuments
 * Public Exports:
 *   - AdminDashboardView
 * Database/Table: workspaces, workspace_members, documents, query_logs,
 *   pipeline_runs, message_generations, agent_events
 * Related Modules: app/admin/dashboard/page.tsx, features/admin/AdminShell.tsx
 * Important Notes: Never bypass RBAC client-side — the backend still 403s any
 *   workspace the caller is not "admin" in on every /admin/workspaces/{id}/*
 *   call; this view only decides what to *show*, not what the API allows.
 * =============================================================================
 */

"use client";

import { ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminHeaderControls } from "@/features/admin/AdminHeaderControls";
import { AdminKpiCards } from "@/features/admin/AdminKpiCards";
import { AdminShell } from "@/features/admin/AdminShell";
import { PipelineHealthCard } from "@/features/admin/PipelineHealthCard";
import { QueryRoutingCard } from "@/features/admin/QueryRoutingCard";
import { RecentPipelineTable } from "@/features/admin/RecentPipelineTable";
import { RecentQueriesTable } from "@/features/admin/RecentQueriesTable";
import type { HealthStatus } from "@/features/admin/SystemHealthCard";
import { SystemHealthCard } from "@/features/admin/SystemHealthCard";
import { UsageCostCard } from "@/features/admin/UsageCostCard";
import { useAdminCostSummary, type CostRangeDays } from "@/hooks/useAdminCostSummary";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAdminPipelineRuns } from "@/hooks/useAdminPipelineRuns";
import { useAdminQueryLogs } from "@/hooks/useAdminQueryLogs";
import { useAuth } from "@/hooks/useAuth";
import { useDocuments } from "@/hooks/useDocuments";
import { useWorkspaceMembers } from "@/hooks/useWorkspaceMembers";

function UnauthorizedState() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
          <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
        </span>
        <h1 className="text-h2 text-primary">Không có quyền truy cập</h1>
        <p className="max-w-md text-body-sm text-secondary">
          Admin Dashboard chỉ dành cho tài khoản Platform <strong>Manage</strong>. Workspace
          Admin không được truy cập <code className="text-caption">/admin</code>.
        </p>
      </div>
    </div>
  );
}

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function AdminDashboardView() {
  const { user, loading: authLoading } = useAuth();
  const {
    options: workspaceOptions,
    loading: workspacesLoading,
    isSystemAdmin,
  } = useAdminEligibleWorkspaces();

  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("");
  const [rangeDays, setRangeDays] = useState<CostRangeDays>(7);

  useEffect(() => {
    if (workspaceOptions.length === 0) {
      setSelectedWorkspaceId("");
      return;
    }
    if (!workspaceOptions.some((w) => w.id === selectedWorkspaceId)) {
      setSelectedWorkspaceId(workspaceOptions[0].id);
    }
  }, [workspaceOptions, selectedWorkspaceId]);

  const workspaceId = selectedWorkspaceId || null;

  const cost = useAdminCostSummary(workspaceId, rangeDays);
  const members = useWorkspaceMembers(workspaceId);
  const documents = useDocuments(workspaceId ?? "", { page: 1, pageSize: 1, fileType: null });
  const queryLogs = useAdminQueryLogs(workspaceId, 8);
  const pipelineRuns = useAdminPipelineRuns(workspaceId);

  const totalQueriesCurrent = cost.current
    ? cost.current.by_route_type.reduce((sum, r) => sum + r.count, 0)
    : null;
  const totalQueriesPrevious = cost.previous
    ? cost.previous.by_route_type.reduce((sum, r) => sum + r.count, 0)
    : null;

  const anyLoading =
    cost.loading || members.loading || documents.loading || queryLogs.loading || pipelineRuns.loading;
  const anyError = Boolean(
    cost.error || members.error || documents.error || queryLogs.error || pipelineRuns.error,
  );
  const apiStatus: HealthStatus = anyLoading && !workspaceId ? "unknown" : anyError ? "degraded" : "healthy";

  function refreshAll() {
    void cost.reload();
    void members.reload();
    void documents.reload();
    void queryLogs.reload();
    void pipelineRuns.reload();
  }

  const showUnauthorized = !authLoading && !workspacesLoading && !isSystemAdmin;

  return (
    <AdminShell active="dashboard" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">FR13 · Observability</p>
            <h1 className="mt-1 text-h1 text-primary">Admin Dashboard</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Theo dõi tình trạng hệ thống, xử lý tri thức, định tuyến AI và mức sử dụng.
            </p>
          </div>
          {!showUnauthorized && workspaceOptions.length > 0 ? (
            <AdminHeaderControls
              workspaces={workspaceOptions}
              selectedWorkspaceId={selectedWorkspaceId}
              onWorkspaceChange={setSelectedWorkspaceId}
              rangeDays={rangeDays}
              onRangeChange={setRangeDays}
              refreshing={anyLoading}
              onRefresh={refreshAll}
            />
          ) : null}
        </div>

        {authLoading || workspacesLoading ? (
          <div className="h-24 animate-pulse rounded-lg border border-border-default bg-surface" />
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : (
          <>
            <AdminKpiCards
              workspaces={{ value: workspaceOptions.length, loading: false, error: null }}
              users={{ value: members.members.length, loading: members.loading, error: members.error }}
              documents={{ value: documents.total, loading: documents.loading, error: documents.error }}
              queries={{ value: totalQueriesCurrent, loading: cost.loading, error: cost.error }}
              queriesDeltaPrev={totalQueriesPrevious}
              llmCalls={{
                value: cost.current?.total_llm_calls ?? null,
                loading: cost.loading,
                error: cost.error,
              }}
              llmCallsDeltaPrev={cost.previous?.total_llm_calls ?? null}
              cost={{
                value: cost.current?.total_cost_usd ?? null,
                loading: cost.loading,
                error: cost.error,
              }}
              costDeltaPrev={cost.previous?.total_cost_usd ?? null}
            />

            <div className="grid gap-4 lg:grid-cols-2">
              <SystemHealthCard apiStatus={apiStatus} />
              <QueryRoutingCard
                cost={cost.current}
                loading={cost.loading}
                error={cost.error}
                onRetry={cost.reload}
                onViewQueryLogs={() => scrollToSection("admin-recent-queries")}
              />
            </div>

            <PipelineHealthCard
              runs={pipelineRuns.runs}
              sampleCapped={pipelineRuns.sampleCapped}
              loading={pipelineRuns.loading}
              error={pipelineRuns.error}
              onRetry={pipelineRuns.reload}
            />

            <UsageCostCard
              cost={cost.current}
              loading={cost.loading}
              error={cost.error}
              onRetry={cost.reload}
              rangeDays={rangeDays}
            />

            <div className="grid gap-4 lg:grid-cols-2">
              <RecentQueriesTable
                items={queryLogs.items}
                loading={queryLogs.loading}
                error={queryLogs.error}
                onRetry={queryLogs.reload}
              />
              <RecentPipelineTable
                runs={pipelineRuns.runs}
                loading={pipelineRuns.loading}
                error={pipelineRuns.error}
                onRetry={pipelineRuns.reload}
              />
            </div>
          </>
        )}
      </div>
    </AdminShell>
  );
}
