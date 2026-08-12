/**
 * =============================================================================
 * File: MembersSettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Members & Access settings — list, invite, role change, remove.
 * Responsibilities:
 *   - Reuse AddMemberModal + workspace member APIs (FR1 / UC10)
 *   - Table layout on desktop; stacked rows on mobile
 * Dependencies:
 *   - hooks/useWorkspaceMembers, AddMemberModal, ConfirmDialog
 * Public Exports:
 *   - MembersSettings
 * Database/Table: workspace_members
 * Related Modules: app/workspaces/[id]/settings/members/page.tsx
 * Important Notes: Backend RBAC is authoritative; UI only gates controls.
 * =============================================================================
 */

"use client";

import { Loader2, MoreHorizontal, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ToastStack } from "@/components/ui/toast";
import {
  AddMemberModal,
  type AddMemberFormValues,
} from "@/features/workspaces/AddMemberModal";
import { SettingsErrorState } from "@/features/settings/SettingsErrorState";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsLoadingState } from "@/features/settings/SettingsLoadingState";
import { SettingsPermissionState } from "@/features/settings/SettingsPermissionState";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceMembers } from "@/hooks/useWorkspaceMembers";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import {
  addWorkspaceMember,
  ApiClientError,
  removeWorkspaceMember,
  updateWorkspaceMemberRole,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { WorkspaceRole } from "@/types/auth";
import type { WorkspaceMember } from "@/types/workspaces";

type Props = {
  workspaceId: string;
};

const ROLE_LABEL: Record<WorkspaceRole, string> = {
  admin: "Admin",
  editor: "Editor",
  viewer: "Viewer",
};

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
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
        return "User này đã là thành viên của Workspace.";
      case "user_not_found":
        return "Không tìm thấy người dùng. Họ cần có tài khoản trước.";
      case "user_mismatch":
        return "Email và user ID không khớp.";
      case "not_found":
        return "Không tìm thấy thành viên hoặc Workspace.";
      case "last_admin":
        return "Không thể thực hiện: đây là admin cuối cùng của Workspace.";
      default:
        break;
    }
    if (err.status === 403) {
      return "Bạn không đủ quyền (cần role Admin).";
    }
    return err.message;
  }
  return fallback;
}

export function MembersSettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { isAdmin, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const { workspace } = useSettingsWorkspace(workspaceId);
  const {
    members,
    loading: membersLoading,
    error: membersError,
    reload,
  } = useWorkspaceMembers(workspaceId);
  const { toasts, dismiss, pushSuccess, pushError } = useToasts();

  const [query, setQuery] = useState("");
  const [roleUpdatingId, setRoleUpdatingId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [removeTarget, setRemoveTarget] = useState<WorkspaceMember | null>(null);
  const [removeSubmitting, setRemoveSubmitting] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return members;
    return members.filter((m) => m.email.toLowerCase().includes(q));
  }, [members, query]);

  async function handleAdd(values: AddMemberFormValues) {
    setAddSubmitting(true);
    setAddError(null);
    try {
      await addWorkspaceMember(workspaceId, {
        user_id: values.userId,
        email: values.email,
        role: values.role,
      });
      await reload();
      setAddOpen(false);
      pushSuccess("Đã gửi lời mời / thêm thành viên.");
    } catch (err) {
      setAddError(mapMemberError(err, "Không thêm được thành viên."));
    } finally {
      setAddSubmitting(false);
    }
  }

  async function handleRoleChange(member: WorkspaceMember, role: WorkspaceRole) {
    if (role === member.role) return;
    setRoleUpdatingId(member.user_id);
    try {
      await updateWorkspaceMemberRole(workspaceId, member.user_id, { role });
      await reload();
      pushSuccess("Đã cập nhật vai trò.");
    } catch (err) {
      pushError(mapMemberError(err, "Không đổi được vai trò."));
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
      pushSuccess("Đã gỡ quyền truy cập.");
    } catch (err) {
      setRemoveError(mapMemberError(err, "Không xoá được thành viên."));
    } finally {
      setRemoveSubmitting(false);
    }
  }

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="members"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Thành viên & quyền"
        description="Quản lý ai có thể truy cập Workspace này (Admin · Editor · Viewer)."
        actions={
          isAdmin ? (
            <button
              type="button"
              onClick={() => {
                setAddError(null);
                setAddOpen(true);
              }}
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white shadow-xs hover:bg-accent-primary-hover",
              )}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Mời thành viên
            </button>
          ) : null
        }
      />

      {!isAdmin && !roleLoading ? (
        <div className="mb-4">
          <SettingsPermissionState description="Chỉ Admin Workspace mới có thể mời, đổi vai trò hoặc gỡ thành viên." />
        </div>
      ) : null}

      <div className="relative mb-4 max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-tertiary"
          aria-hidden
        />
        <label htmlFor="member-search-settings" className="sr-only">
          Tìm thành viên
        </label>
        <input
          id="member-search-settings"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm thành viên…"
          className={cn(
            "h-10 w-full rounded-md border border-border-default bg-surface pl-9 pr-3",
            "text-body-sm text-primary outline-none",
            "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
          )}
        />
      </div>

      {membersLoading || roleLoading ? (
        <SettingsLoadingState message="Đang tải thành viên…" />
      ) : membersError ? (
        <SettingsErrorState message={membersError} onRetry={() => void reload()} />
      ) : filtered.length === 0 ? (
        <p className="rounded-md border border-dashed border-border-strong px-4 py-8 text-center text-body-sm text-secondary">
          {query.trim()
            ? "Không tìm thấy thành viên phù hợp."
            : "Chưa có thành viên nào."}
        </p>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden overflow-hidden rounded-md border border-border-default md:block">
            <table className="w-full text-left">
              <thead className="border-b border-border-default bg-elevated/50">
                <tr className="text-caption font-medium text-tertiary">
                  <th className="px-4 py-3 font-medium">Thành viên</th>
                  <th className="px-4 py-3 font-medium">Vai trò</th>
                  <th className="px-4 py-3 font-medium">Tham gia</th>
                  <th className="px-4 py-3 font-medium">
                    <span className="sr-only">Thao tác</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-default">
                {filtered.map((member) => {
                  const isSelf = user?.id === member.user_id;
                  const isUpdating = roleUpdatingId === member.user_id;
                  return (
                    <tr key={member.user_id} className="bg-surface">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-tertiary-soft text-caption font-semibold text-accent-tertiary">
                            {initialsOf(member.email)}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-body-sm font-medium text-primary">
                              {member.email}
                              {isSelf ? (
                                <span className="ml-2 text-caption font-normal text-tertiary">
                                  (Bạn)
                                </span>
                              ) : null}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {isAdmin ? (
                          <div className="flex items-center gap-2">
                            {isUpdating ? (
                              <Loader2
                                className="h-3.5 w-3.5 animate-spin text-tertiary"
                                aria-hidden
                              />
                            ) : null}
                            <select
                              value={member.role}
                              disabled={isUpdating}
                              aria-label={`Vai trò của ${member.email}`}
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
                                "disabled:opacity-60",
                              )}
                            >
                              <option value="admin">Admin</option>
                              <option value="editor">Editor</option>
                              <option value="viewer">Viewer</option>
                            </select>
                          </div>
                        ) : (
                          <span className="text-body-sm text-secondary">
                            {ROLE_LABEL[member.role]}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-body-sm text-secondary">
                        {formatDate(member.joined_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {isAdmin ? (
                          <div className="relative inline-block">
                            <button
                              type="button"
                              aria-label="Thao tác thành viên"
                              aria-expanded={menuOpenId === member.user_id}
                              onClick={() =>
                                setMenuOpenId((cur) =>
                                  cur === member.user_id ? null : member.user_id,
                                )
                              }
                              className="flex h-8 w-8 items-center justify-center rounded-md text-tertiary hover:bg-elevated hover:text-primary"
                            >
                              <MoreHorizontal className="h-4 w-4" aria-hidden />
                            </button>
                            {menuOpenId === member.user_id ? (
                              <div
                                role="menu"
                                className="absolute right-0 z-10 mt-1 w-44 rounded-md border border-border-default bg-surface py-1 shadow-md"
                              >
                                <button
                                  type="button"
                                  role="menuitem"
                                  onClick={() => {
                                    setMenuOpenId(null);
                                    setRemoveError(null);
                                    setRemoveTarget(member);
                                  }}
                                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-body-sm text-danger hover:bg-danger-soft"
                                >
                                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                                  Gỡ quyền truy cập
                                </button>
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile stacked rows */}
          <ul className="flex flex-col gap-2 md:hidden">
            {filtered.map((member) => {
              const isSelf = user?.id === member.user_id;
              const isUpdating = roleUpdatingId === member.user_id;
              return (
                <li
                  key={member.user_id}
                  className="rounded-md border border-border-default bg-surface p-4"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-tertiary-soft text-caption font-semibold text-accent-tertiary">
                      {initialsOf(member.email)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-body-sm font-medium text-primary">
                        {member.email}
                        {isSelf ? (
                          <span className="ml-1 text-caption text-tertiary">
                            (Bạn)
                          </span>
                        ) : null}
                      </p>
                      <p className="mt-0.5 text-caption text-tertiary">
                        Tham gia {formatDate(member.joined_at)}
                      </p>
                      <div className="mt-3 flex items-center gap-2">
                        {isAdmin ? (
                          <>
                            <select
                              value={member.role}
                              disabled={isUpdating}
                              aria-label={`Vai trò của ${member.email}`}
                              onChange={(e) =>
                                void handleRoleChange(
                                  member,
                                  e.target.value as WorkspaceRole,
                                )
                              }
                              className={cn(
                                "h-9 flex-1 cursor-pointer rounded-md border border-border-default bg-surface px-2.5",
                                "text-body-sm text-primary outline-none",
                                "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                              )}
                            >
                              <option value="admin">Admin</option>
                              <option value="editor">Editor</option>
                              <option value="viewer">Viewer</option>
                            </select>
                            <button
                              type="button"
                              title="Gỡ quyền truy cập"
                              onClick={() => {
                                setRemoveError(null);
                                setRemoveTarget(member);
                              }}
                              className="flex h-9 w-9 items-center justify-center rounded-md text-tertiary hover:bg-danger-soft hover:text-danger"
                            >
                              <Trash2 className="h-4 w-4" aria-hidden />
                            </button>
                          </>
                        ) : (
                          <span className="text-body-sm text-secondary">
                            {ROLE_LABEL[member.role]}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}

      <AddMemberModal
        open={addOpen}
        workspaceId={workspaceId}
        submitting={addSubmitting}
        error={addError}
        onClose={() => {
          if (!addSubmitting) setAddOpen(false);
        }}
        onSubmit={handleAdd}
      />

      <ConfirmDialog
        open={removeTarget !== null}
        title="Gỡ quyền truy cập?"
        description={`"${removeTarget?.email ?? ""}" sẽ bị xoá khỏi Workspace này.`}
        confirmLabel="Gỡ quyền truy cập"
        confirming={removeSubmitting}
        error={removeError}
        onCancel={() => {
          if (!removeSubmitting) setRemoveTarget(null);
        }}
        onConfirm={() => void handleRemoveConfirm()}
      />

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </SettingsLayout>
  );
}
