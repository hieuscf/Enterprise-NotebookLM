/**
 * =============================================================================
 * File: admin-users.ts
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Pure helpers for `/admin/users` filtering, role labels, and display
 *          aggregation (no API calls).
 * Responsibilities:
 *   - Filter AdminUserRow by search / workspace / role
 *   - Role label + badge class mapping (admin | editor | viewer)
 *   - Compact workspace name list for table cells
 * Dependencies:
 *   - hooks/useAdminUsers types, types/auth.WorkspaceRole
 * Public Exports:
 *   - ROLE_LABEL_EN, ROLE_BADGE_CLASS, filterAdminUsers, uniqueRoles,
 *     compactWorkspaceNames, earliestJoinedAt, initialsFromEmail
 * Database/Table: N/A
 * Related Modules: features/admin/AdminUsersTable, AdminUsersView
 * Important Notes: Role filter = user has ≥1 membership with that role.
 * =============================================================================
 */

import type { AdminUserMembership, AdminUserRow } from "@/hooks/useAdminUsers";
import type { WorkspaceRole } from "@/types/auth";

export const ROLE_LABEL_EN: Record<WorkspaceRole, string> = {
  admin: "Admin",
  editor: "Editor",
  viewer: "Viewer",
};

export const ROLE_BADGE_CLASS: Record<WorkspaceRole, string> = {
  admin: "bg-accent-primary-soft text-accent-primary",
  editor: "bg-accent-secondary-soft text-accent-secondary",
  viewer: "bg-elevated text-tertiary",
};

export type AdminUserFilters = {
  searchQuery: string;
  workspaceId: string; // "" = all
  role: WorkspaceRole | "";
};

export function initialsFromEmail(email: string): string {
  const local = email.split("@")[0]?.trim() ?? "";
  if (!local) return "?";
  const parts = local.split(/[._\-\s]+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

export function uniqueRoles(memberships: AdminUserMembership[]): WorkspaceRole[] {
  const order: WorkspaceRole[] = ["admin", "editor", "viewer"];
  const present = new Set(memberships.map((m) => m.role));
  return order.filter((r) => present.has(r));
}

export function compactWorkspaceNames(
  memberships: AdminUserMembership[],
  maxVisible = 2,
): { visible: string[]; overflow: number } {
  const names = memberships.map((m) => m.workspace_name);
  if (names.length <= maxVisible) {
    return { visible: names, overflow: 0 };
  }
  return {
    visible: names.slice(0, maxVisible),
    overflow: names.length - maxVisible,
  };
}

export function earliestJoinedAt(memberships: AdminUserMembership[]): string | null {
  if (memberships.length === 0) return null;
  let earliest = memberships[0].joined_at;
  for (const m of memberships) {
    if (m.joined_at < earliest) earliest = m.joined_at;
  }
  return earliest;
}

export function filterAdminUsers(
  users: AdminUserRow[],
  filters: AdminUserFilters,
): AdminUserRow[] {
  const q = filters.searchQuery.trim().toLowerCase();
  return users.filter((user) => {
    if (q) {
      const haystack = `${user.email} ${user.full_name}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    if (filters.workspaceId) {
      if (!user.memberships.some((m) => m.workspace_id === filters.workspaceId)) {
        return false;
      }
    }
    if (filters.role) {
      if (!user.memberships.some((m) => m.role === filters.role)) return false;
    }
    return true;
  });
}

export function paginateItems<T>(items: T[], page: number, pageSize: number): T[] {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
