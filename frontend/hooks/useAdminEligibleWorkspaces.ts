/**
 * =============================================================================
 * File: useAdminEligibleWorkspaces.ts
 * Module/Service: Observability Module / Workspace Service (Web App)
 * Layer: UI
 * Purpose: Resolve which workspaces the signed-in user may view on the Admin
 *          Dashboard — only workspaces where their role is "admin" (FR12).
 * Responsibilities:
 *   - Read memberships from /auth/me (role source of truth, per useAuth)
 *   - Resolve display names via GET /workspaces (already-authorized list)
 *   - Never widen access beyond the user's own admin memberships — there is
 *     no cross-tenant "All Workspaces" concept in this RBAC model
 * Dependencies:
 *   - hooks/useAuth, lib/api-client.listWorkspaces
 * Public Exports:
 *   - useAdminEligibleWorkspaces
 * Database/Table: workspace_members (role), workspaces
 * Related Modules: features/admin/AdminDashboardView, features/admin/WorkspaceRangeControls
 * Important Notes: Backend remains the real gate (require_workspace_admin_rl on
 *   every /admin/workspaces/{id}/* call) — this hook only drives the picker UI.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/hooks/useAuth";
import { ApiClientError, listWorkspaces } from "@/lib/api-client";

export type AdminWorkspaceOption = {
  id: string;
  name: string;
};

export function useAdminEligibleWorkspaces() {
  const { user, loading: authLoading } = useAuth();
  const [options, setOptions] = useState<AdminWorkspaceOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const adminWorkspaceIds = user
    ? user.workspaces.filter((w) => w.role === "admin").map((w) => w.workspace_id)
    : [];
  const adminIdsKey = adminWorkspaceIds.join(",");

  const reload = useCallback(async () => {
    if (authLoading) return;
    if (adminWorkspaceIds.length === 0) {
      setOptions([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const idSet = new Set(adminWorkspaceIds);
      const data = await listWorkspaces(1, 100);
      const resolved = data.items
        .filter((w) => idSet.has(w.id))
        .map((w) => ({ id: w.id, name: w.name }));
      // Keep any admin membership whose workspace wasn't in the first page —
      // still selectable, labelled by id, rather than silently dropped.
      for (const id of adminWorkspaceIds) {
        if (!resolved.some((w) => w.id === id)) {
          resolved.push({ id, name: `Workspace ${id.slice(0, 8)}` });
        }
      }
      setOptions(resolved);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách workspace.",
      );
      setOptions([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, adminIdsKey]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    options,
    loading: authLoading || loading,
    error,
    reload,
    isSystemAdmin: adminWorkspaceIds.length > 0,
  };
}
