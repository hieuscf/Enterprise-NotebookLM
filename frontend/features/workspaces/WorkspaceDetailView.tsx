/**
 * =============================================================================
 * File: WorkspaceDetailView.tsx
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Workspace detail — view + admin edit/delete with confirm (FR1).
 * Responsibilities:
 *   - Load GET /workspaces/{id}; gate edit/delete via useWorkspaceRole
 *   - Handle 403 from API even when UI gates miss a mid-session role change
 * Dependencies:
 *   - hooks/useWorkspaceRole, useAuth; lib/api-client; ConfirmDialog, FormModal;
 *     features/shell/AppShell
 * Public Exports:
 *   - WorkspaceDetailView
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/page.tsx, app/workspaces/[id]/members/page.tsx
 * Important Notes: Soft-delete — row remains in DB; list hides it after reload.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Loader2,
  Pencil,
  Trash2,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/features/shell/AppShell";
import { ConfirmDialog } from "@/features/workspaces/ConfirmDialog";
import {
  WorkspaceFormModal,
  type WorkspaceFormValues,
} from "@/features/workspaces/WorkspaceFormModal";
import { useAuth } from "@/hooks/useAuth";
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

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function mapApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 403) {
      return "Bạn không đủ quyền thực hiện thao tác này (cần role admin).";
    }
    return err.message;
  }
  return fallback;
}

export function WorkspaceDetailView({ workspaceId }: Props) {
  const router = useRouter();
  const { user, reload: reloadAuth } = useAuth();
  const { isAdmin, loading: roleLoading, role } = useWorkspaceRole(workspaceId);

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
      const data = await getWorkspace(workspaceId);
      setWorkspace(data);
    } catch (err) {
      setWorkspace(null);
      setLoadError(mapApiError(err, "Không tải được workspace."));
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
    } catch (err) {
      setEditError(mapApiError(err, "Không cập nhật được workspace."));
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
      router.replace("/workspaces");
      router.refresh();
    } catch (err) {
      setDeleteError(mapApiError(err, "Không xoá được workspace."));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  return (
    <AppShell active="workspaces" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <Link
          href="/workspaces"
          className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Quay lại danh sách
        </Link>

        {loading || roleLoading ? (
          <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface px-4 py-10 text-body-sm text-tertiary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Đang tải chi tiết workspace…
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
                Thử lại
              </button>
            </div>
          </div>
        ) : workspace ? (
          <section className="rounded-lg border border-border-default bg-surface p-6 shadow-xs sm:p-8">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-caption font-medium text-accent-primary">
                  Workspace
                  {role ? (
                    <>
                      {" "}
                      · role{" "}
                      <span className="uppercase tracking-wide">{role}</span>
                    </>
                  ) : null}
                </p>
                <h1 className="mt-1 break-words text-h1 text-primary">
                  {workspace.name}
                </h1>
                <p className="mt-3 max-w-2xl text-body text-secondary">
                  {workspace.description?.trim()
                    ? workspace.description
                    : "Chưa có mô tả cho workspace này."}
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
                    Sửa
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
                    Xoá
                  </button>
                </div>
              ) : null}
            </div>

            <dl className="mt-8 grid gap-4 border-t border-border-default pt-6 text-body-sm sm:grid-cols-2">
              <div>
                <dt className="text-tertiary">Tạo lúc</dt>
                <dd className="mt-0.5 text-primary">
                  {formatDate(workspace.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-tertiary">Cập nhật lúc</dt>
                <dd className="mt-0.5 text-primary">
                  {formatDate(workspace.updated_at)}
                </dd>
              </div>
            </dl>

            <Link
              href={`/workspaces/${workspaceId}/members`}
              className={cn(
                "mt-8 flex items-center justify-between gap-3 rounded-md border border-border-default",
                "bg-elevated/60 px-4 py-3 transition-colors hover:bg-elevated",
              )}
            >
              <div className="flex items-start gap-3">
                <Users className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" aria-hidden />
                <div>
                  <p className="text-body-sm font-medium text-primary">
                    Quản lý thành viên
                  </p>
                  <p className="mt-0.5 text-body-sm text-secondary">
                    Xem, thêm, đổi vai trò hoặc xoá thành viên workspace (UC10).
                  </p>
                </div>
              </div>
              <ArrowRight
                className="h-4 w-4 shrink-0 text-tertiary"
                aria-hidden
              />
            </Link>
          </section>
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
        title="Xoá Workspace?"
        description={`Workspace "${workspace?.name ?? ""}" sẽ bị ẩn khỏi danh sách (soft-delete). Dữ liệu liên quan vẫn được giữ trong hệ thống. Hành động này cần quyền admin.`}
        confirmLabel="Xoá Workspace"
        confirming={deleteSubmitting}
        error={deleteError}
        onCancel={() => {
          if (!deleteSubmitting) setDeleteOpen(false);
        }}
        onConfirm={() => void handleDelete()}
      />
    </AppShell>
  );
}
