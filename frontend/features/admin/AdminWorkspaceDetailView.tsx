/**
 * =============================================================================
 * File: AdminWorkspaceDetailView.tsx
 * Module/Service: Workspace Service (Web App) — FR1 Admin Console
 * Layer: UI
 * Purpose: Thin skeleton for `/admin/workspaces/[workspaceId]` so list
 *          navigation does not 404. Full Overview / Members / Documents /
 *          Activity / Pipeline / Usage / Permissions console is out of scope
 *          for the list-page task — this view only loads basic Workspace
 *          fields and deep-links into existing workspace routes.
 * Responsibilities:
 *   - GET /workspaces/{id}; show name, description, timestamps
 *   - Link to existing member / document / chat routes under /workspaces/{id}
 *   - Admin-gated Edit / Delete (reuse WorkspaceFormModal + ConfirmDialog)
 * Dependencies:
 *   - hooks/useAuth, useWorkspaceRole; lib/api-client; features/admin/AdminShell;
 *     WorkspaceFormModal; ConfirmDialog; ToastStack; admin-format
 * Public Exports:
 *   - AdminWorkspaceDetailView
 * Database/Table: workspaces
 * Related Modules: app/admin/workspaces/[workspaceId]/page.tsx
 * Important Notes: Does not call /members solely for a count (avoids N+1
 *   pattern on list; detail will own member management later).
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowLeft,
  FileText,
  Loader2,
  MessageSquare,
  Pencil,
  Trash2,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ToastStack } from "@/components/ui/toast";
import { formatDateTimeShort } from "@/features/admin/admin-format";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminShell } from "@/features/admin/AdminShell";
import {
  WorkspaceFormModal,
  type WorkspaceFormValues,
} from "@/features/workspaces/WorkspaceFormModal";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import {
  ApiClientError,
  deleteWorkspace,
  getWorkspace,
  updateWorkspace,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { Workspace } from "@/types/workspaces";

type Props = {
  workspaceId: string;
};

function mapApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 403) {
      return "You do not have permission for this action (workspace admin required).";
    }
    if (err.status === 404) return "Workspace not found.";
    return err.message || fallback;
  }
  return fallback;
}

export function AdminWorkspaceDetailView({ workspaceId }: Props) {
  const router = useRouter();
  const { user, reload: reloadAuth } = useAuth();
  const { isAdmin, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const { toasts, dismiss, pushSuccess } = useToasts();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editOpen, setEditOpen] = useState(false);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setWorkspace(await getWorkspace(workspaceId));
    } catch (err) {
      setWorkspace(null);
      setLoadError(mapApiError(err, "Unable to load this workspace."));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleEdit(values: WorkspaceFormValues) {
    setEditSubmitting(true);
    setEditError(null);
    try {
      const updated = await updateWorkspace(workspaceId, {
        name: values.name,
        description: values.description || null,
      });
      setWorkspace(updated);
      setEditOpen(false);
      pushSuccess("Workspace updated.");
    } catch (err) {
      setEditError(mapApiError(err, "Unable to update this workspace. Please try again."));
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleDelete() {
    setDeleteSubmitting(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(workspaceId);
      await reloadAuth();
      setDeleteOpen(false);
      pushSuccess("Workspace deleted.");
      router.replace("/admin/workspaces");
    } catch (err) {
      setDeleteError(mapApiError(err, "Unable to delete this workspace. Please try again."));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  return (
    <AdminShell active="workspaces" user={user}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <Link
          href="/admin/workspaces"
          className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to Workspaces
        </Link>

        {loading || roleLoading ? (
          <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface px-4 py-10 text-body-sm text-tertiary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Loading workspace…
          </div>
        ) : loadError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex flex-col gap-2">
              <span>{loadError}</span>
              <button
                type="button"
                onClick={() => void load()}
                className="w-fit text-body-sm font-medium underline"
              >
                Retry
              </button>
            </div>
          </div>
        ) : workspace ? (
          <>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-caption font-medium text-accent-primary">
                  FR1 · Workspace detail
                </p>
                <h1 className="mt-1 break-words text-h1 text-primary">{workspace.name}</h1>
                <p className="mt-2 max-w-2xl text-body-sm text-secondary">
                  {workspace.description?.trim()
                    ? workspace.description
                    : "No description."}
                </p>
              </div>
              {isAdmin ? (
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setEditError(null);
                      setEditOpen(true);
                    }}
                    className={cn(
                      "inline-flex h-10 items-center gap-2 rounded-md border border-border-default bg-surface px-3",
                      "text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary",
                    )}
                  >
                    <Pencil className="h-4 w-4" aria-hidden />
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                      setDeleteOpen(true);
                    }}
                    className={cn(
                      "inline-flex h-10 items-center gap-2 rounded-md border border-border-default bg-danger-soft px-3",
                      "text-body-sm font-medium text-danger hover:opacity-90",
                    )}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                    Delete
                  </button>
                </div>
              ) : null}
            </div>

            <AdminCard
              headingId="admin-ws-overview"
              title="Overview"
              description="Basic workspace metadata from GET /workspaces/{id}."
            >
              <dl className="grid gap-4 text-body-sm sm:grid-cols-2">
                <div>
                  <dt className="text-tertiary">Created</dt>
                  <dd className="mt-0.5 text-primary">
                    {formatDateTimeShort(workspace.created_at)}
                  </dd>
                </div>
                <div>
                  <dt className="text-tertiary">Updated</dt>
                  <dd className="mt-0.5 text-primary">
                    {formatDateTimeShort(workspace.updated_at)}
                  </dd>
                </div>
              </dl>
            </AdminCard>

            <AdminCard
              headingId="admin-ws-sections"
              title="Manage"
              description="Deep-links into existing workspace modules. A full admin detail console (Activity, Pipeline, Usage, Permissions) will land in a later task."
            >
              <ul className="flex flex-col gap-2">
                <li>
                  <Link
                    href={`/workspaces/${workspaceId}/members`}
                    className="flex items-center gap-3 rounded-md border border-border-default px-3 py-2.5 text-body-sm hover:bg-elevated"
                  >
                    <Users className="h-4 w-4 text-accent-primary" aria-hidden />
                    <span className="font-medium text-primary">Members</span>
                    <span className="text-tertiary">— roles & access (UC10)</span>
                  </Link>
                </li>
                <li>
                  <Link
                    href={`/workspaces/${workspaceId}/documents`}
                    className="flex items-center gap-3 rounded-md border border-border-default px-3 py-2.5 text-body-sm hover:bg-elevated"
                  >
                    <FileText className="h-4 w-4 text-accent-primary" aria-hidden />
                    <span className="font-medium text-primary">Documents</span>
                    <span className="text-tertiary">— knowledge base</span>
                  </Link>
                </li>
                <li>
                  <Link
                    href={`/workspaces/${workspaceId}/chat`}
                    className="flex items-center gap-3 rounded-md border border-border-default px-3 py-2.5 text-body-sm hover:bg-elevated"
                  >
                    <MessageSquare className="h-4 w-4 text-accent-primary" aria-hidden />
                    <span className="font-medium text-primary">Chat</span>
                    <span className="text-tertiary">— AI conversations</span>
                  </Link>
                </li>
              </ul>
            </AdminCard>
          </>
        ) : null}
      </div>

      <WorkspaceFormModal
        open={editOpen}
        mode="edit"
        initial={{
          name: workspace?.name ?? "",
          description: workspace?.description ?? "",
        }}
        submitting={editSubmitting}
        error={editError}
        onClose={() => {
          if (!editSubmitting) setEditOpen(false);
        }}
        onSubmit={handleEdit}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Delete Workspace?"
        description={`You are about to delete “${workspace?.name ?? ""}”. This action cannot be undone.`}
        confirmLabel="Delete Workspace"
        confirming={deleteSubmitting}
        error={deleteError}
        onCancel={() => {
          if (!deleteSubmitting) setDeleteOpen(false);
        }}
        onConfirm={() => void handleDelete()}
      />

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AdminShell>
  );
}
