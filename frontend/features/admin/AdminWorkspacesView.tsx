/**
 * =============================================================================
 * File: AdminWorkspacesView.tsx
 * Module/Service: Workspace Service (Web App) — FR1 Admin Console
 * Layer: UI
 * Purpose: Workspace Management Console at `/admin/workspaces` — second Admin
 *          Console page beside `/admin/dashboard`. Lists, creates, edits and
 *          deletes workspaces via the existing OpenAPI Workspace contract.
 * Responsibilities:
 *   - RBAC gate: page requires at least one workspace-admin membership
 *     (same UX gate as AdminDashboardView); Edit/Delete gated per-row via
 *     /auth/me memberships. Backend remains the real enforcer.
 *   - Server-side pagination (page / page_size); client-side search on the
 *     current page only (no OpenAPI search param — see table TODO).
 *   - Create / Edit via WorkspaceFormModal; Delete via ConfirmDialog; toasts
 * Dependencies:
 *   - features/admin/AdminShell, features/admin/*, features/workspaces/WorkspaceFormModal,
 *     components/ui/confirm-dialog, toast; hooks/useAuth, useWorkspaces,
 *     useAdminEligibleWorkspaces, useToasts; lib/api-client
 * Public Exports:
 *   - AdminWorkspacesView
 * Database/Table: workspaces, workspace_members
 * Related Modules: app/admin/workspaces/page.tsx, features/admin/AdminShell.tsx
 * Important Notes:
 *   - Never N+1 fetch members/documents/query-logs per row.
 *   - Create: any authenticated user may POST /workspaces (backend decision —
 *     OpenAPI summary says Admin but no global-admin role exists; creator
 *     becomes workspace admin). UI shows Create for users who pass the page gate.
 * =============================================================================
 */

"use client";

import { ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ToastStack } from "@/components/ui/toast";
import { AdminShell } from "@/features/admin/AdminShell";
import { AdminWorkspacesTable } from "@/features/admin/AdminWorkspacesTable";
import {
  WorkspaceFormModal,
  type WorkspaceFormValues,
} from "@/features/workspaces/WorkspaceFormModal";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import {
  ApiClientError,
  createWorkspace,
  deleteWorkspace,
  updateWorkspace,
} from "@/lib/api-client";
import type { Workspace } from "@/types/workspaces";

const PAGE_SIZE = 20;

function mapApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 401) {
      return "Your session has expired. Please sign in again.";
    }
    if (err.status === 403) {
      return "You do not have permission for this action (workspace admin required).";
    }
    if (err.status === 404) {
      return "Workspace not found.";
    }
    if (err.status === 409) {
      return err.message || "This workspace conflicts with an existing record.";
    }
    if (err.status === 422) {
      return err.message || "Please check the form and try again.";
    }
    return err.message || fallback;
  }
  return fallback;
}

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">Không có quyền truy cập</h2>
      <p className="max-w-md text-body-sm text-secondary">
        Workspace Management chỉ dành cho thành viên có vai trò <strong>admin</strong> trong ít
        nhất một workspace. Liên hệ quản trị viên workspace của bạn nếu bạn cần quyền này.
      </p>
    </div>
  );
}

export function AdminWorkspacesView() {
  const router = useRouter();
  const { user, loading: authLoading, reload: reloadAuth } = useAuth();
  const { loading: adminGateLoading, isSystemAdmin } = useAdminEligibleWorkspaces();
  const { toasts, dismiss, pushSuccess } = useToasts();

  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const { items, total, loading, error, reload } = useWorkspaces(page, PAGE_SIZE);

  const adminIdSet = useMemo(() => {
    const ids = new Set<string>();
    if (!user) return ids;
    for (const m of user.workspaces) {
      if (m.role === "admin") ids.add(m.workspace_id);
    }
    return ids;
  }, [user]);

  // Client-side filter on the current page only — see AdminWorkspacesTable TODO.
  const visibleItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (ws) =>
        ws.name.toLowerCase().includes(q) ||
        (ws.description ?? "").toLowerCase().includes(q),
    );
  }, [items, searchQuery]);

  const [createOpen, setCreateOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editTarget, setEditTarget] = useState<Workspace | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const showUnauthorized = !authLoading && !adminGateLoading && !isSystemAdmin;

  async function handleCreate(values: WorkspaceFormValues) {
    setCreateSubmitting(true);
    setCreateError(null);
    try {
      await createWorkspace({
        name: values.name,
        description: values.description || null,
      });
      await Promise.all([reload(), reloadAuth()]);
      setCreateOpen(false);
      pushSuccess("Workspace created.");
    } catch (err) {
      setCreateError(mapApiError(err, "Unable to create this workspace. Please try again."));
    } finally {
      setCreateSubmitting(false);
    }
  }

  async function handleEdit(values: WorkspaceFormValues) {
    if (!editTarget) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      await updateWorkspace(editTarget.id, {
        name: values.name,
        description: values.description || null,
      });
      await reload();
      setEditTarget(null);
      pushSuccess("Workspace updated.");
    } catch (err) {
      setEditError(mapApiError(err, "Unable to update this workspace. Please try again."));
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteSubmitting(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(deleteTarget.id);
      await Promise.all([reloadAuth(), reload()]);
      // If we deleted the last item on a page > 1, step back one page.
      if (items.length <= 1 && page > 1) {
        setPage((p) => Math.max(1, p - 1));
      }
      setDeleteTarget(null);
      pushSuccess("Workspace deleted.");
    } catch (err) {
      setDeleteError(mapApiError(err, "Unable to delete this workspace. Please try again."));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  return (
    <AdminShell active="workspaces" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">FR1 · Workspace Management</p>
            <h1 className="mt-1 text-h1 text-primary">Workspaces</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Manage enterprise workspaces, members and access control.
            </p>
          </div>
          {!showUnauthorized ? (
            <button
              type="button"
              onClick={() => {
                setCreateError(null);
                setCreateOpen(true);
              }}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white hover:bg-accent-primary-hover"
            >
              + Create Workspace
            </button>
          ) : null}
        </div>

        {authLoading || adminGateLoading ? (
          <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : (
          <AdminWorkspacesTable
            items={visibleItems}
            total={total}
            page={page}
            pageSize={PAGE_SIZE}
            loading={loading}
            error={error}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onPageChange={(next) => {
              setSearchQuery("");
              setPage(next);
            }}
            onRetry={() => void reload()}
            onCreate={() => {
              setCreateError(null);
              setCreateOpen(true);
            }}
            onView={(ws) => router.push(`/admin/workspaces/${ws.id}`)}
            onEdit={(ws) => {
              setEditError(null);
              setEditTarget(ws);
            }}
            onDelete={(ws) => {
              setDeleteError(null);
              setDeleteTarget(ws);
            }}
            canManage={(id) => adminIdSet.has(id)}
            canCreate
          />
        )}
      </div>

      <WorkspaceFormModal
        open={createOpen}
        mode="create"
        submitting={createSubmitting}
        error={createError}
        onClose={() => {
          if (!createSubmitting) setCreateOpen(false);
        }}
        onSubmit={handleCreate}
      />

      <WorkspaceFormModal
        open={editTarget !== null}
        mode="edit"
        initial={{
          name: editTarget?.name ?? "",
          description: editTarget?.description ?? "",
        }}
        submitting={editSubmitting}
        error={editError}
        onClose={() => {
          if (!editSubmitting) setEditTarget(null);
        }}
        onSubmit={handleEdit}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete Workspace?"
        description={`You are about to delete “${deleteTarget?.name ?? ""}”. This action cannot be undone.`}
        confirmLabel="Delete Workspace"
        confirming={deleteSubmitting}
        error={deleteError}
        onCancel={() => {
          if (!deleteSubmitting) setDeleteTarget(null);
        }}
        onConfirm={() => void handleDelete()}
      />

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AdminShell>
  );
}
