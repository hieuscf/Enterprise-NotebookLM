/**
 * =============================================================================
 * File: AdminHeaderControls.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Admin Dashboard page-level controls (Admin Dashboard §6) —
 *          workspace selector (multi-tenant, RBAC-scoped), date range, and a
 *          manual refresh action shared by every cost-driven card.
 * Responsibilities:
 *   - Render <select> of workspaces the user administers (never "All
 *     Workspaces" — this RBAC model has no cross-tenant admin role)
 *   - Render 7/30/90-day range control
 *   - Render Refresh button reflecting the combined loading state
 * Dependencies:
 *   - hooks/useAdminEligibleWorkspaces (AdminWorkspaceOption), lib/utils
 * Public Exports:
 *   - AdminHeaderControls
 * Database/Table: N/A
 * Related Modules: features/admin/AdminDashboardView
 * Important Notes: Workspace choice never bypasses RBAC — the backend still
 *   403s any workspace the user is not "admin" in; this list is only ever
 *   built from the user's own admin memberships (see useAdminEligibleWorkspaces).
 * =============================================================================
 */

"use client";

import { RefreshCw } from "lucide-react";

import type { AdminWorkspaceOption } from "@/hooks/useAdminEligibleWorkspaces";
import type { CostRangeDays } from "@/hooks/useAdminCostSummary";
import { cn } from "@/lib/utils";

const RANGE_OPTIONS: { value: CostRangeDays; label: string }[] = [
  { value: 7, label: "7 ngày gần nhất" },
  { value: 30, label: "30 ngày gần nhất" },
  { value: 90, label: "90 ngày gần nhất" },
];

type Props = {
  workspaces: AdminWorkspaceOption[];
  selectedWorkspaceId: string;
  onWorkspaceChange: (id: string) => void;
  rangeDays: CostRangeDays;
  onRangeChange: (days: CostRangeDays) => void;
  refreshing: boolean;
  onRefresh: () => void;
};

export function AdminHeaderControls({
  workspaces,
  selectedWorkspaceId,
  onWorkspaceChange,
  rangeDays,
  onRangeChange,
  refreshing,
  onRefresh,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        aria-label="Chọn workspace"
        value={selectedWorkspaceId}
        onChange={(e) => onWorkspaceChange(e.target.value)}
        className={cn(
          "h-10 rounded-md border border-border-default bg-surface px-2.5",
          "text-body-sm text-primary outline-none",
          "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
        )}
      >
        {workspaces.map((ws) => (
          <option key={ws.id} value={ws.id}>
            {ws.name}
          </option>
        ))}
      </select>

      <select
        aria-label="Khoảng thời gian"
        value={rangeDays}
        onChange={(e) => onRangeChange(Number(e.target.value) as CostRangeDays)}
        className={cn(
          "h-10 rounded-md border border-border-default bg-surface px-2.5",
          "text-body-sm text-primary outline-none",
          "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
        )}
      >
        {RANGE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        className={cn(
          "inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border-default px-3",
          "text-body-sm font-medium text-secondary hover:bg-elevated",
          "disabled:opacity-50",
        )}
      >
        <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} aria-hidden />
        Làm mới
      </button>
    </div>
  );
}
