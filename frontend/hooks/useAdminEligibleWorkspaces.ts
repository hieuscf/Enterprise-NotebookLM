/**
 * =============================================================================
 * File: useAdminEligibleWorkspaces.ts
 * Module/Service: Observability Module / Workspace Service (Web App)
 * Layer: UI
 * Purpose: Resolve workspaces for Platform Manage Admin Console pickers.
 * Responsibilities:
 *   - Gate on platform_role === manage (canAccessAdmin)
 *   - Load workspace directory via GET /workspaces (Manage sees all active)
 * Dependencies:
 *   - hooks/useAuth, lib/api-client.listWorkspaces, lib/rbac.canAccessAdmin
 * Public Exports:
 *   - useAdminEligibleWorkspaces
 * Database/Table: workspaces, users.platform_role
 * Related Modules: features/admin/AdminDashboardView, features/admin/WorkspaceRangeControls
 * Important Notes:
 *   - Backend require_platform_manage gates every /admin/workspaces/{id}/* call.
 *   - Workspace Admin membership does NOT grant Admin Console access.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/hooks/useAuth";
import { ApiClientError, listWorkspaces } from "@/lib/api-client";
import { canAccessAdmin } from "@/lib/rbac";

export type AdminWorkspaceOption = {
  id: string;
  name: string;
};

export function useAdminEligibleWorkspaces() {
  const { user, loading: authLoading } = useAuth();
  const [options, setOptions] = useState<AdminWorkspaceOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isManage = canAccessAdmin(user);

  const reload = useCallback(async () => {
    if (authLoading) return;
    if (!isManage) {
      setOptions([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaces(1, 100);
      setOptions(data.items.map((w) => ({ id: w.id, name: w.name })));
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
  }, [authLoading, isManage]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    options,
    loading: authLoading || loading,
    error,
    reload,
    /** @deprecated use canAccessAdmin(user) — kept for existing call sites */
    isSystemAdmin: isManage,
    isManage,
  };
}
