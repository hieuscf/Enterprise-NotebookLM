/**
 * =============================================================================
 * File: admin.api.ts
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Typed calls to the existing Admin/Observability contract:
 *          GET /admin/workspaces/{id}/query-logs, /pipeline-runs, /cost-summary
 *          (backend/app/api/admin.py — admin-only, RBAC enforced server-side).
 * Responsibilities:
 *   - listWorkspaceQueryLogs — route_type filter + page/page_size
 *   - listWorkspacePipelineRuns — status filter + page/page_size
 *   - getWorkspaceCostSummary — from/to date range
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError)
 * Public Exports:
 *   - listWorkspaceQueryLogs, listWorkspacePipelineRuns, getWorkspaceCostSummary
 * Database/Table: query_logs, pipeline_runs, message_generations, agent_events
 * Related Modules: hooks/useAdmin*, features/admin/*
 * Important Notes:
 *   - Do NOT invent endpoints (no /admin/dashboard/stats, /admin/health, etc.) —
 *     only the three operations above exist server-side.
 *   - Admin-only: backend returns 403 for non-admin workspace members; the UI
 *     must not attempt to bypass this (see AdminDashboardView RBAC gate).
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type { CostSummary, QueryLogItem } from "@/types/admin";
import type { RouteType } from "@/types/chat";
import type { PipelineRun, PipelineStatus } from "@/types/documents";

export async function listWorkspaceQueryLogs(
  workspaceId: string,
  params?: { routeType?: RouteType | null; page?: number; pageSize?: number },
): Promise<QueryLogItem[]> {
  const qs = new URLSearchParams({
    page: String(params?.page ?? 1),
    page_size: String(params?.pageSize ?? 20),
  });
  if (params?.routeType) qs.set("route_type", params.routeType);
  const response = await apiFetch(
    `/admin/workspaces/${workspaceId}/query-logs?${qs.toString()}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as QueryLogItem[];
}

export async function listWorkspacePipelineRuns(
  workspaceId: string,
  params?: { status?: PipelineStatus | null; page?: number; pageSize?: number },
): Promise<PipelineRun[]> {
  const qs = new URLSearchParams({
    page: String(params?.page ?? 1),
    page_size: String(params?.pageSize ?? 20),
  });
  if (params?.status) qs.set("status", params.status);
  const response = await apiFetch(
    `/admin/workspaces/${workspaceId}/pipeline-runs?${qs.toString()}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as PipelineRun[];
}

export async function getWorkspaceCostSummary(
  workspaceId: string,
  params?: { from?: string | null; to?: string | null },
): Promise<CostSummary> {
  const qs = new URLSearchParams();
  if (params?.from) qs.set("from", params.from);
  if (params?.to) qs.set("to", params.to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const response = await apiFetch(
    `/admin/workspaces/${workspaceId}/cost-summary${suffix}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as CostSummary;
}
