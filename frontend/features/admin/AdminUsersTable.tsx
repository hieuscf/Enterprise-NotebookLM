/**
 * =============================================================================
 * File: AdminUsersTable.tsx
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Users table for `/admin/users` — search, workspace/role filters,
 *          client-side pagination over the admin-visible user directory.
 * Responsibilities:
 *   - Render User / Workspaces / Roles / Joined / Actions
 *   - Skeleton, error, empty, filtered-empty states
 *   - Row menu: View + Manage access + Delete permanently
 * Dependencies:
 *   - features/admin/AdminCard, AdminSectionState, AdminRowMenu, admin-format,
 *     admin-users; hooks/useAdminUsers
 * Public Exports:
 *   - AdminUsersTable
 * Database/Table: users, workspace_members (via GET /admin/users)
 * Related Modules: features/admin/AdminUsersView
 * Important Notes:
 *   - No Status column — OpenAPI AdminUserListItem does not expose status.
 *   - Self-delete: Delete permanently disabled with tooltip.
 * =============================================================================
 */

"use client";

import { ChevronLeft, ChevronRight, Search, Users } from "lucide-react";
import Link from "next/link";

import { formatDateTimeShort } from "@/features/admin/admin-format";
import {
  compactWorkspaceNames,
  earliestJoinedAt,
  initialsFromEmail,
  ROLE_BADGE_CLASS,
  ROLE_LABEL_EN,
  uniqueRoles,
} from "@/features/admin/admin-users";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminRowMenu, type AdminRowMenuItem } from "@/features/admin/AdminRowMenu";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import type { AdminUserRow } from "@/hooks/useAdminUsers";
import type { AdminWorkspaceOption } from "@/hooks/useAdminEligibleWorkspaces";
import { cn } from "@/lib/utils";
import type { WorkspaceRole } from "@/types/auth";

type Props = {
  items: AdminUserRow[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  workspaceFilter: string;
  roleFilter: WorkspaceRole | "";
  workspaceOptions: AdminWorkspaceOption[];
  currentUserId: string | null;
  canDeleteUser: boolean;
  onSearchChange: (value: string) => void;
  onWorkspaceFilterChange: (workspaceId: string) => void;
  onRoleFilterChange: (role: WorkspaceRole | "") => void;
  onClearFilters: () => void;
  onPageChange: (page: number) => void;
  onRetry: () => void;
  onView: (user: AdminUserRow) => void;
  onManageAccess: (user: AdminUserRow) => void;
  onDeletePermanently: (user: AdminUserRow) => void;
};

function rangeLabel(page: number, pageSize: number, total: number): string {
  if (total === 0) return "Showing 0 of 0";
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `Showing ${from}–${to} of ${total}`;
}

function initialsForUser(user: AdminUserRow): string {
  const fromName = user.full_name.trim();
  if (fromName) {
    const parts = fromName.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
    }
    return fromName.slice(0, 2).toUpperCase();
  }
  return initialsFromEmail(user.email);
}

export function AdminUsersTable({
  items,
  total,
  page,
  pageSize,
  loading,
  error,
  searchQuery,
  workspaceFilter,
  roleFilter,
  workspaceOptions,
  currentUserId,
  canDeleteUser,
  onSearchChange,
  onWorkspaceFilterChange,
  onRoleFilterChange,
  onClearFilters,
  onPageChange,
  onRetry,
  onView,
  onManageAccess,
  onDeletePermanently,
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const hasFilters =
    Boolean(searchQuery.trim()) || Boolean(workspaceFilter) || Boolean(roleFilter);
  const showEmpty = !loading && !error && total === 0 && !hasFilters;
  const showNoMatch = !loading && !error && items.length === 0 && hasFilters;

  function rowMenuItems(user: AdminUserRow): AdminRowMenuItem[] {
    const isSelf = Boolean(currentUserId && currentUserId === user.user_id);
    const menu: AdminRowMenuItem[] = [
      {
        key: "view",
        label: "View",
        onSelect: () => onView(user),
      },
      {
        key: "manage",
        label: "Manage access",
        onSelect: () => onManageAccess(user),
        disabled: user.memberships.length === 0,
        title:
          user.memberships.length === 0
            ? "This user has no workspace memberships yet."
            : undefined,
      },
    ];
    if (canDeleteUser) {
      menu.push({
        key: "delete",
        label: "Delete permanently",
        destructive: true,
        disabled: isSelf,
        title: isSelf ? "You cannot delete your own account." : undefined,
        onSelect: () => onDeletePermanently(user),
      });
    }
    return menu;
  }

  return (
    <AdminCard
      headingId="admin-users-table"
      title="User list"
      description="Users in workspaces you administer, plus unassigned accounts."
    >
      {!showEmpty ? (
        <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center">
          <div className="relative w-full max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
              aria-hidden
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search users..."
              aria-label="Search users"
              className={cn(
                "h-9 w-full rounded-md border border-border-default bg-base pl-9 pr-3",
                "text-body-sm text-primary placeholder:text-tertiary",
                "outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            />
          </div>
          <label className="flex items-center gap-2 text-body-sm text-secondary">
            <span className="sr-only">Filter by workspace</span>
            <select
              value={workspaceFilter}
              onChange={(e) => onWorkspaceFilterChange(e.target.value)}
              aria-label="Filter by workspace"
              className={cn(
                "h-9 min-w-[10rem] cursor-pointer rounded-md border border-border-default bg-base px-2.5",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            >
              <option value="">All workspaces</option>
              {workspaceOptions.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-body-sm text-secondary">
            <span className="sr-only">Filter by role</span>
            <select
              value={roleFilter}
              onChange={(e) => onRoleFilterChange(e.target.value as WorkspaceRole | "")}
              aria-label="Filter by role"
              className={cn(
                "h-9 min-w-[8rem] cursor-pointer rounded-md border border-border-default bg-base px-2.5",
                "text-body-sm text-primary outline-none",
                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              )}
            >
              <option value="">All roles</option>
              <option value="admin">Admin</option>
              <option value="editor">Editor</option>
              <option value="viewer">Viewer</option>
            </select>
          </label>
          {hasFilters ? (
            <button
              type="button"
              onClick={onClearFilters}
              className="h-9 text-body-sm font-medium text-accent-primary hover:underline"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      ) : null}

      {loading ? (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                <th className="px-1 py-2 font-medium">User</th>
                <th className="px-1 py-2 font-medium">Workspaces</th>
                <th className="px-1 py-2 font-medium">Roles</th>
                <th className="px-1 py-2 font-medium">Joined</th>
                <th className="px-1 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={5} className="px-1 py-3">
                  <SectionSkeleton rows={5} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : showEmpty ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent-primary-soft">
            <Users className="h-6 w-6 text-accent-primary" aria-hidden />
          </span>
          <SectionEmpty
            title="No users found."
            description="Create an account or add members to workspaces you administer."
          />
        </div>
      ) : showNoMatch ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <SectionEmpty
            title="No users match your filters."
            description="Try a different search, workspace, or role."
          />
          <button
            type="button"
            onClick={onClearFilters}
            className="text-body-sm font-medium text-accent-primary hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-body-sm">
              <thead>
                <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                  <th className="px-1 py-2 font-medium">User</th>
                  <th className="px-1 py-2 font-medium">Workspaces</th>
                  <th className="px-1 py-2 font-medium">Roles</th>
                  <th className="px-1 py-2 font-medium">Joined</th>
                  <th className="px-1 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((user) => {
                  const { overflow } = compactWorkspaceNames(user.memberships);
                  const visibleMemberships = user.memberships.slice(0, 2);
                  const roles = uniqueRoles(user.memberships);
                  const joined = earliestJoinedAt(user.memberships);
                  return (
                    <tr key={user.user_id} className="border-b border-border-default last:border-0">
                      <td className="max-w-[240px] px-1 py-2.5">
                        <Link
                          href={`/admin/users/${user.user_id}`}
                          className="flex min-w-0 items-center gap-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30"
                        >
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-tertiary-soft text-caption font-semibold text-accent-tertiary">
                            {initialsForUser(user)}
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate font-medium text-primary hover:text-accent-primary">
                              {user.full_name || user.email}
                            </span>
                            <span className="block truncate text-caption text-tertiary">
                              {user.email}
                            </span>
                          </span>
                        </Link>
                      </td>
                      <td className="max-w-[220px] px-1 py-2.5 text-secondary">
                        {user.memberships.length === 0 ? (
                          <span className="text-caption text-tertiary">Unassigned</span>
                        ) : (
                          <div className="flex flex-col gap-0.5">
                            {visibleMemberships.map((m) => (
                              <Link
                                key={`${user.user_id}-${m.workspace_id}`}
                                href={`/admin/workspaces/${m.workspace_id}`}
                                className="truncate hover:text-accent-primary"
                              >
                                {m.workspace_name}
                              </Link>
                            ))}
                            {overflow > 0 ? (
                              <span className="text-caption text-tertiary">+{overflow} more</span>
                            ) : null}
                          </div>
                        )}
                      </td>
                      <td className="px-1 py-2.5">
                        {roles.length === 0 ? (
                          <span className="text-caption text-tertiary">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {roles.map((role) => (
                              <span
                                key={role}
                                className={cn(
                                  "inline-flex rounded-full px-2 py-0.5 text-caption font-medium",
                                  ROLE_BADGE_CLASS[role],
                                )}
                              >
                                {ROLE_LABEL_EN[role]}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-1 py-2.5 text-tertiary">
                        {joined ? formatDateTimeShort(joined) : "—"}
                      </td>
                      <td className="px-1 py-2.5 text-right">
                        <AdminRowMenu
                          label={`Actions for ${user.email}`}
                          items={rowMenuItems(user)}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-caption text-tertiary">{rangeLabel(page, pageSize, total)}</p>
            {totalPages > 1 ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => onPageChange(Math.max(1, page - 1))}
                  className={cn(
                    "flex h-9 items-center gap-1 rounded-md border border-border-default px-3",
                    "text-body-sm font-medium text-secondary hover:bg-elevated",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                  )}
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                  Previous
                </button>
                <span className="text-caption text-tertiary">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => onPageChange(Math.min(totalPages, page + 1))}
                  className={cn(
                    "flex h-9 items-center gap-1 rounded-md border border-border-default px-3",
                    "text-body-sm font-medium text-secondary hover:bg-elevated",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                  )}
                >
                  Next
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </button>
              </div>
            ) : null}
          </div>
        </>
      )}
    </AdminCard>
  );
}
