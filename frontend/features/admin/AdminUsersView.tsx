/**
 * =============================================================================
 * File: AdminUsersView.tsx
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Enterprise User & Access Management Console at `/admin/users` —
 *          third Admin Console page beside dashboard and workspaces.
 * Responsibilities:
 *   - RBAC gate: require ≥1 workspace-admin membership (same UX as other admin pages)
 *   - List via GET /admin/users; client-side search / workspace / role filters
 *   - Create account (POST /admin/users); permanent delete (DELETE /admin/users/{id})
 *   - Manage access via PATCH /workspaces/{id}/members/{userId}
 * Dependencies:
 *   - features/admin/AdminShell, AdminUsersTable, ManageUserAccessDialog,
 *     CreateUserDialog; components/ui/confirm-dialog; hooks/useAuth, useAdminUsers,
 *     useToasts; lib/api-client
 * Public Exports:
 *   - AdminUsersView
 * Database/Table: users, workspace_members, roles, workspaces
 * Related Modules: app/admin/users/page.tsx, AdminSidebar.tsx
 * Important Notes:
 *   - Permanent delete is hard-delete (not status=disabled).
 *   - Self-delete blocked in UI + backend.
 * =============================================================================
 */

"use client";

import { Plus, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ToastStack } from "@/components/ui/toast";
import {
  filterAdminUsers,
  paginateItems,
} from "@/features/admin/admin-users";
import { AdminShell } from "@/features/admin/AdminShell";
import { AdminUsersTable } from "@/features/admin/AdminUsersTable";
import {
  CreateUserDialog,
  mapCreateUserError,
  type CreateUserFormValues,
} from "@/features/admin/CreateUserDialog";
import {
  ManageUserAccessDialog,
  mapAccessUpdateError,
} from "@/features/admin/ManageUserAccessDialog";
import type { AdminUserRow } from "@/hooks/useAdminUsers";
import { useAdminUsers } from "@/hooks/useAdminUsers";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import {
  ApiClientError,
  createAdminUser,
  deleteAdminUser,
  updateWorkspaceMemberRole,
} from "@/lib/api-client";
import type { WorkspaceRole } from "@/types/auth";

const PAGE_SIZE = 20;

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">You don&apos;t have permission to view user management.</h2>
      <p className="max-w-md text-body-sm text-secondary">
        User management is available to members with the <strong>admin</strong> role in at least
        one workspace. Contact your workspace administrator if you need access.
      </p>
    </div>
  );
}

function mapDeleteUserError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 401) return "Your session has expired. Please sign in again.";
    if (err.status === 403) {
      return "You don't have permission to delete this user account.";
    }
    if (err.code === "self_delete") {
      return "You cannot delete your own account.";
    }
    if (err.code === "last_admin") {
      return "This account cannot be deleted because it is the last administrator.";
    }
    if (err.status === 404) return "User not found.";
    if (err.status === 409) return err.message || fallback;
    if (err.status === 0 || err.code === "network_error") {
      return "Network error. Check your connection and try again.";
    }
    if (err.status >= 500) return "Something went wrong on the server. Please try again.";
    return err.message || fallback;
  }
  return fallback;
}

export function AdminUsersView() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const {
    users,
    workspaces,
    loading,
    error,
    reloadMembers,
    isSystemAdmin,
  } = useAdminUsers();
  const { toasts, dismiss, pushSuccess } = useToasts();

  const [searchQuery, setSearchQuery] = useState("");
  const [workspaceFilter, setWorkspaceFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState<WorkspaceRole | "">("");
  const [page, setPage] = useState(1);

  const [manageTarget, setManageTarget] = useState<AdminUserRow | null>(null);
  const [manageSubmitting, setManageSubmitting] = useState(false);
  const [manageError, setManageError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<AdminUserRow | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      filterAdminUsers(users, {
        searchQuery,
        workspaceId: workspaceFilter,
        role: roleFilter,
      }),
    [users, searchQuery, workspaceFilter, roleFilter],
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageItems = useMemo(
    () => paginateItems(filtered, page, PAGE_SIZE),
    [filtered, page],
  );

  const showUnauthorized = !authLoading && !loading && !isSystemAdmin;
  const canCreateUser = isSystemAdmin;
  const canDeleteUser = isSystemAdmin;

  function clearFilters() {
    setSearchQuery("");
    setWorkspaceFilter("");
    setRoleFilter("");
    setPage(1);
  }

  async function handleManageAccess(
    changes: { workspaceId: string; role: WorkspaceRole }[],
  ) {
    if (!manageTarget || changes.length === 0) return;
    setManageSubmitting(true);
    setManageError(null);
    try {
      for (const change of changes) {
        await updateWorkspaceMemberRole(change.workspaceId, manageTarget.user_id, {
          role: change.role,
        });
      }
      setManageTarget(null);
      pushSuccess("User access updated.");
      await reloadMembers();
    } catch (err) {
      setManageError(mapAccessUpdateError(err, "Unable to update user access. Please try again."));
    } finally {
      setManageSubmitting(false);
    }
  }

  async function handleCreate(values: CreateUserFormValues) {
    setCreateSubmitting(true);
    setCreateError(null);
    try {
      await createAdminUser({
        email: values.email,
        password: values.password,
        full_name: values.full_name,
      });
      setCreateOpen(false);
      setPage(1);
      pushSuccess("Account created successfully.");
      await reloadMembers();
    } catch (err) {
      setCreateError(mapCreateUserError(err, "Unable to create account. Please try again."));
    } finally {
      setCreateSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget || deleteSubmitting) return;
    setDeleteSubmitting(true);
    setDeleteError(null);
    try {
      await deleteAdminUser(deleteTarget.user_id);
      const remainingOnPage = pageItems.length;
      if (remainingOnPage <= 1 && page > 1) {
        setPage((p) => Math.max(1, p - 1));
      }
      setDeleteTarget(null);
      pushSuccess("Account deleted permanently.");
      await reloadMembers();
    } catch (err) {
      setDeleteError(mapDeleteUserError(err, "Unable to delete this account. Please try again."));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  const deleteDescription = deleteTarget
    ? [
        "You are about to permanently delete:",
        "",
        deleteTarget.full_name || deleteTarget.email,
        deleteTarget.email,
        "",
        "This action cannot be undone.",
        "The account and its associated access will be permanently removed.",
      ].join("\n")
    : "";

  return (
    <AdminShell active="users" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">FR12 · Access Control</p>
            <h1 className="mt-1 text-h1 text-primary">Users</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Manage users and workspace access.
            </p>
          </div>
          {!showUnauthorized ? (
            <button
              type="button"
              onClick={() => {
                setCreateError(null);
                setCreateOpen(true);
              }}
              disabled={!canCreateUser}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white hover:bg-accent-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-4 w-4" aria-hidden />
              Create account
            </button>
          ) : null}
        </div>

        {authLoading ? (
          <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : (
          <AdminUsersTable
            items={pageItems}
            total={filtered.length}
            page={page}
            pageSize={PAGE_SIZE}
            loading={loading}
            error={error}
            searchQuery={searchQuery}
            workspaceFilter={workspaceFilter}
            roleFilter={roleFilter}
            workspaceOptions={workspaces}
            currentUserId={user?.id ?? null}
            canDeleteUser={canDeleteUser}
            onSearchChange={(value) => {
              setSearchQuery(value);
              setPage(1);
            }}
            onWorkspaceFilterChange={(id) => {
              setWorkspaceFilter(id);
              setPage(1);
            }}
            onRoleFilterChange={(role) => {
              setRoleFilter(role);
              setPage(1);
            }}
            onClearFilters={clearFilters}
            onPageChange={setPage}
            onRetry={() => void reloadMembers()}
            onView={(row) => router.push(`/admin/users/${row.user_id}`)}
            onManageAccess={(row) => {
              setManageError(null);
              setManageTarget(row);
            }}
            onDeletePermanently={(row) => {
              setDeleteError(null);
              setDeleteTarget(row);
            }}
          />
        )}
      </div>

      <ManageUserAccessDialog
        open={manageTarget !== null}
        user={manageTarget}
        submitting={manageSubmitting}
        error={manageError}
        onClose={() => {
          if (!manageSubmitting) setManageTarget(null);
        }}
        onSubmit={(changes) => void handleManageAccess(changes)}
      />

      <CreateUserDialog
        open={createOpen}
        submitting={createSubmitting}
        error={createError}
        onClose={() => {
          if (!createSubmitting) setCreateOpen(false);
        }}
        onSubmit={(values) => void handleCreate(values)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete account permanently?"
        description={deleteDescription}
        confirmLabel="Delete permanently"
        cancelLabel="Cancel"
        confirming={deleteSubmitting}
        error={deleteError}
        variant="danger"
        onCancel={() => {
          if (!deleteSubmitting) setDeleteTarget(null);
        }}
        onConfirm={() => void handleDelete()}
      />

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AdminShell>
  );
}
