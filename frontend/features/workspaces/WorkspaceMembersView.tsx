/**
 * =============================================================================
 * File: WorkspaceMembersView.tsx
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Member management UI — list, add, change role, remove (FR1 / UC10).
 * Responsibilities:
 *   - Load workspace name + member list; gate mutations via useWorkspaceRole
 *   - Handle 403/404/409/400(last_admin) from API with friendly messages
 * Dependencies:
 *   - hooks/useWorkspaceMembers, useWorkspaceRole, useAuth; lib/api-client
 *   - features/workspaces/AddMemberModal; components/ui/confirm-dialog
 * Public Exports:
 *   - WorkspaceMembersView
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/members/page.tsx
 * Important Notes: Backend is the source of truth for RBAC — UI gates only hide
 *   controls; a mid-session role change still surfaces as a 403 from the API.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowLeft,
  Loader2,
  Plus,
  Trash2,
  UserX,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  AddMemberModal,
  type AddMemberFormValues,
} from "@/features/workspaces/AddMemberModal";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useWorkspaceMembers } from "@/hooks/useWorkspaceMembers";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import {
  addWorkspaceMember,
  ApiClientError,
  getWorkspace,
  removeWorkspaceMember,
  updateWorkspaceMemberRole,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { WorkspaceRole } from "@/types/auth";
import type { Workspace, WorkspaceMember } from "@/types/workspaces";

type Props = {
  workspaceId: string;
};

const ROLE_LABEL: Record<WorkspaceRole, string> = {
  admin: "Quản trị viên",
  editor: "Biên tập viên",
  viewer: "Người xem",
};

const ROLE_BADGE_CLASS: Record<WorkspaceRole, string> = {
  admin: "bg-accent-primary-soft text-accent-primary",
  editor: "bg-accent-secondary-soft text-accent-secondary",
  viewer: "bg-elevated text-tertiary",
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

function initialsOf(email: string): string {
  return email.trim()[0]?.toUpperCase() ?? "?";
}

function mapMemberError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    switch (err.code) {
      case "member_exists":
        return "User này đã là thành viên của workspace.";
      case "user_not_found":
        return "Không tìm thấy user với ID này.";
      case "not_found":
        return "Không tìm thấy thành viên hoặc workspace.";
      case "last_admin":
        return "Không thể thực hiện: đây là admin cuối cùng của workspace.";
      default:
        break;
    }
    if (err.status === 403) {
      return "Bạn không đủ quyền thực hiện thao tác này (cần role admin).";
    }
    return err.message;
  }
  return fallback;
}

export function WorkspaceMembersView({ workspaceId }: Props) {
  const { user } = useAuth();
  const { isAdmin, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const {
    members,
    loading: membersLoading,
    error: membersError,
    reload,
  } = useWorkspaceMembers(workspaceId);

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [wsLoadError, setWsLoadError] = useState<string | null>(null);

  const [actionError, setActionError] = useState<string | null>(null);
  const [roleUpdatingId, setRoleUpdatingId] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [removeTarget, setRemoveTarget] = useState<WorkspaceMember | null>(
    null,
  );
  const [removeSubmitting, setRemoveSubmitting] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const loadWorkspace = useCallback(async () => {
    try {
      const data = await getWorkspace(workspaceId);
      setWorkspace(data);
      setWsLoadError(null);
    } catch (err) {
      setWsLoadError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được thông tin workspace.",
      );
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  async function handleAdd(values: AddMemberFormValues) {
    setAddSubmitting(true);
    setAddError(null);
    try {
      await addWorkspaceMember(workspaceId, {
        user_id: values.userId,
        role: values.role,
      });
      await reload();
      setAddOpen(false);
    } catch (err) {
      setAddError(mapMemberError(err, "Không thêm được thành viên."));
    } finally {
      setAddSubmitting(false);
    }
  }

  async function handleRoleChange(member: WorkspaceMember, role: WorkspaceRole) {
    if (role === member.role) return;
    setActionError(null);
    setRoleUpdatingId(member.user_id);
    try {
      await updateWorkspaceMemberRole(workspaceId, member.user_id, { role });
      await reload();
    } catch (err) {
      setActionError(mapMemberError(err, "Không đổi được vai trò."));
    } finally {
      setRoleUpdatingId(null);
    }
  }

  async function handleRemoveConfirm() {
    if (!removeTarget) return;
    setRemoveSubmitting(true);
    setRemoveError(null);
    try {
      await removeWorkspaceMember(workspaceId, removeTarget.user_id);
      await reload();
      setRemoveTarget(null);
    } catch (err) {
      setRemoveError(mapMemberError(err, "Không xoá được thành viên."));
    } finally {
      setRemoveSubmitting(false);
    }
  }

  const headerLoading = roleLoading || (!workspace && !wsLoadError);

  return (
    <AppShell active="members" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-8">
        <Link
          href={`/workspaces/${workspaceId}`}
          className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Quay lại workspace
        </Link>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <p className="text-caption font-medium text-accent-primary">
              Quản lý thành viên
            </p>
            <h1 className="mt-1 truncate text-h1 text-primary">
              {headerLoading ? "Đang tải…" : workspace?.name ?? "Workspace"}
            </h1>
            <p className="mt-1 text-body-sm text-secondary">
              {members.length} thành viên đang hoạt động trong workspace này.
            </p>
          </div>
          {isAdmin ? (
            <button
              type="button"
              onClick={() => {
                setAddError(null);
                setAddOpen(true);
              }}
              className={cn(
                "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white shadow-xs hover:bg-accent-primary-hover",
              )}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Thêm thành viên
            </button>
          ) : null}
        </div>

        {wsLoadError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {wsLoadError}
          </div>
        ) : null}

        {actionError ? (
          <div
            role="alert"
            className="flex items-start justify-between gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <span className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {actionError}
            </span>
            <button
              type="button"
              onClick={() => setActionError(null)}
              className="shrink-0 font-medium underline"
            >
              Đóng
            </button>
          </div>
        ) : null}

        {membersLoading ? (
          <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface px-4 py-10 text-body-sm text-tertiary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Đang tải danh sách thành viên…
          </div>
        ) : membersError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex flex-col gap-2">
              <span>{membersError}</span>
              <button
                type="button"
                onClick={() => void reload()}
                className="w-fit text-body-sm font-medium underline"
              >
                Thử lại
              </button>
            </div>
          </div>
        ) : members.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-strong bg-surface px-6 py-10 text-center text-body-sm text-secondary">
            Chưa có thành viên nào.
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {members.map((member) => {
              const isSelf = user?.id === member.user_id;
              const isUpdating = roleUpdatingId === member.user_id;

              return (
                <li
                  key={member.user_id}
                  className="flex items-center gap-3 rounded-lg border border-border-default bg-surface p-4 shadow-xs"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-tertiary-soft text-body-sm font-semibold text-accent-tertiary">
                    {initialsOf(member.email)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 truncate text-body-sm font-medium text-primary">
                      <span className="truncate">{member.email}</span>
                      {isSelf ? (
                        <span className="shrink-0 rounded-full bg-elevated px-1.5 py-0.5 text-[10px] font-medium text-tertiary">
                          Bạn
                        </span>
                      ) : null}
                    </p>
                    <p className="text-caption text-tertiary">
                      Tham gia {formatDate(member.joined_at)}
                    </p>
                  </div>

                  {isAdmin ? (
                    <div className="flex shrink-0 items-center gap-2">
                      {isUpdating ? (
                        <Loader2
                          className="h-4 w-4 animate-spin text-tertiary"
                          aria-hidden
                        />
                      ) : null}
                      <select
                        value={member.role}
                        disabled={isUpdating}
                        onChange={(e) =>
                          void handleRoleChange(
                            member,
                            e.target.value as WorkspaceRole,
                          )
                        }
                        className={cn(
                          "h-9 cursor-pointer rounded-md border border-border-default bg-surface px-2.5",
                          "text-body-sm text-primary outline-none",
                          "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                          "disabled:cursor-not-allowed disabled:opacity-60",
                        )}
                      >
                        <option value="admin">Quản trị viên</option>
                        <option value="editor">Biên tập viên</option>
                        <option value="viewer">Người xem</option>
                      </select>
                      <button
                        type="button"
                        title="Xoá khỏi workspace"
                        disabled={isUpdating}
                        onClick={() => {
                          setRemoveError(null);
                          setRemoveTarget(member);
                        }}
                        className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-md text-tertiary",
                          "hover:bg-danger-soft hover:text-danger disabled:cursor-not-allowed disabled:opacity-60",
                        )}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                      </button>
                    </div>
                  ) : (
                    <span
                      className={cn(
                        "shrink-0 rounded-full px-2.5 py-1 text-caption font-medium",
                        ROLE_BADGE_CLASS[member.role],
                      )}
                    >
                      {ROLE_LABEL[member.role]}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {!isAdmin && !roleLoading ? (
          <p className="flex items-center gap-2 text-caption text-tertiary">
            <UserX className="h-3.5 w-3.5" aria-hidden />
            Chỉ quản trị viên (admin) mới có thể thêm, đổi vai trò hoặc xoá
            thành viên.
          </p>
        ) : null}
      </div>

      <AddMemberModal
        open={addOpen}
        submitting={addSubmitting}
        error={addError}
        onClose={() => {
          if (!addSubmitting) setAddOpen(false);
        }}
        onSubmit={handleAdd}
      />

      <ConfirmDialog
        open={removeTarget !== null}
        title="Xoá thành viên?"
        description={`"${removeTarget?.email ?? ""}" sẽ bị xoá khỏi workspace này (soft-delete, có thể thêm lại sau).`}
        confirmLabel="Xoá thành viên"
        confirming={removeSubmitting}
        error={removeError}
        onCancel={() => {
          if (!removeSubmitting) setRemoveTarget(null);
        }}
        onConfirm={() => void handleRemoveConfirm()}
      />
    </AppShell>
  );
}
