/**
 * =============================================================================
 * File: useAdminUsers.ts
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Load the admin-visible user directory for `/admin/users` via
 *          GET /admin/users (memberships in admin workspaces + unassigned accounts).
 * Responsibilities:
 *   - Gate on admin-eligible workspaces (same UX as other admin pages)
 *   - Fetch GET /admin/users once; map to AdminUserRow
 *   - Expose reloadMembers for post-create / post-delete refresh
 * Dependencies:
 *   - hooks/useAdminEligibleWorkspaces, lib/api-client.listAdminUsers
 * Public Exports:
 *   - useAdminUsers, type AdminUserRow, type AdminUserMembership
 * Database/Table: users, workspace_members, roles, workspaces
 * Related Modules: features/admin/AdminUsersView
 * Important Notes:
 *   - Prefer single GET /admin/users over N× GET /workspaces/{id}/members.
 *   - Orphan (no membership) accounts appear so Create Account results show up.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import {
  useAdminEligibleWorkspaces,
  type AdminWorkspaceOption,
} from "@/hooks/useAdminEligibleWorkspaces";
import { ApiClientError, listAdminUsers } from "@/lib/api-client";
import type { WorkspaceRole } from "@/types/auth";

export type AdminUserMembership = {
  workspace_id: string;
  workspace_name: string;
  role: WorkspaceRole;
  joined_at: string;
};

export type AdminUserRow = {
  user_id: string;
  email: string;
  full_name: string;
  memberships: AdminUserMembership[];
};

export function useAdminUsers() {
  const {
    options,
    loading: workspacesLoading,
    error: workspacesError,
    reload: reloadWorkspaces,
    isSystemAdmin,
  } = useAdminEligibleWorkspaces();

  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const optionsKey = options.map((o) => o.id).join(",");

  const reload = useCallback(async () => {
    if (workspacesLoading) return;

    if (options.length === 0) {
      setUsers([]);
      setLoading(false);
      setError(workspacesError);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await listAdminUsers();
      setUsers(
        response.items.map((item) => ({
          user_id: item.user_id,
          email: item.email,
          full_name: item.full_name,
          memberships: item.memberships.map((m) => ({
            workspace_id: m.workspace_id,
            workspace_name: m.workspace_name,
            role: m.role,
            joined_at: m.joined_at,
          })),
        })),
      );
    } catch (err) {
      setUsers([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load users.",
      );
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspacesLoading, optionsKey, workspacesError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    users,
    workspaces: options as AdminWorkspaceOption[],
    loading: workspacesLoading || loading,
    error: error ?? workspacesError,
    reload: async () => {
      await reloadWorkspaces();
    },
    reloadMembers: reload,
    isSystemAdmin,
  };
}
