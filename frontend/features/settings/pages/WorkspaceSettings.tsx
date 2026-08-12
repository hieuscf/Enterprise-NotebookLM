/**
 * =============================================================================
 * File: WorkspaceSettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Workspace information edit + danger-zone soft-delete (FR1).
 * Responsibilities:
 *   - PATCH /workspaces/{id}; DELETE with exact-name confirmation
 *   - Gate mutations via useWorkspaceRole / canEditWorkspace
 * Dependencies:
 *   - lib/api-client, Confirm/Delete dialogs, Settings* components
 * Public Exports:
 *   - WorkspaceSettings
 * Database/Table: workspaces
 * Related Modules: app/workspaces/[id]/settings/workspace/page.tsx
 * Important Notes: Soft-delete — backend remains RBAC authority.
 * =============================================================================
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import { DeleteWorkspaceDialog } from "@/features/settings/DeleteWorkspaceDialog";
import { SettingsDangerZone } from "@/features/settings/SettingsDangerZone";
import { SettingsErrorState } from "@/features/settings/SettingsErrorState";
import { SettingsField, settingsInputClass } from "@/features/settings/SettingsField";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsLoadingState } from "@/features/settings/SettingsLoadingState";
import { SettingsPermissionState } from "@/features/settings/SettingsPermissionState";
import { SettingsSaveBar } from "@/features/settings/SettingsSaveBar";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import {
  ApiClientError,
  deleteWorkspace,
  updateWorkspace,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
};

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "long",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function mapApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 403) {
      return "Bạn không đủ quyền thực hiện thao tác này.";
    }
    return err.message;
  }
  return fallback;
}

export function WorkspaceSettings({ workspaceId }: Props) {
  const router = useRouter();
  const { user, reload: reloadAuth } = useAuth();
  const { isAdmin, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const { workspace, loading, error, reload, setWorkspace } =
    useSettingsWorkspace(workspaceId);
  const { toasts, dismiss, pushSuccess, pushError } = useToasts();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    setName(workspace.name);
    setDescription(workspace.description ?? "");
  }, [workspace]);

  const dirty = useMemo(() => {
    if (!workspace) return false;
    return (
      name.trim() !== workspace.name ||
      (description.trim() || "") !== (workspace.description?.trim() || "")
    );
  }, [workspace, name, description]);

  async function handleSave() {
    if (!workspace || !isAdmin) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setSaveError("Tên Workspace không được để trống.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateWorkspace(workspaceId, {
        name: trimmed,
        description: description.trim() || null,
      });
      setWorkspace(updated);
      pushSuccess("Đã lưu thay đổi Workspace.");
    } catch (err) {
      const message = mapApiError(err, "Không lưu được thay đổi.");
      setSaveError(message);
      pushError(message);
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    if (!workspace) return;
    setName(workspace.name);
    setDescription(workspace.description ?? "");
    setSaveError(null);
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(workspaceId);
      await reloadAuth();
      setDeleteOpen(false);
      router.replace("/workspaces");
      router.refresh();
    } catch (err) {
      setDeleteError(mapApiError(err, "Không xoá được Workspace."));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="workspace"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Workspace"
        description="Quản lý Workspace hiện tại — tài liệu, chat và quyền truy cập được cô lập theo Workspace."
      />

      {loading || roleLoading ? (
        <SettingsLoadingState />
      ) : error ? (
        <SettingsErrorState message={error} onRetry={() => void reload()} />
      ) : workspace ? (
        <>
          <SettingsSection
            title="Thông tin Workspace"
            description="Các thay đổi chỉ áp dụng cho Workspace này."
          >
            {!isAdmin ? (
              <SettingsPermissionState description="Bạn không có quyền sửa Workspace này. Liên hệ quản trị viên Workspace." />
            ) : null}

            <fieldset
              disabled={!isAdmin || saving}
              className="flex flex-col gap-5 disabled:opacity-90"
            >
              <SettingsField label="Tên Workspace" required>
                {(id) => (
                  <input
                    id={id}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={settingsInputClass}
                    maxLength={120}
                  />
                )}
              </SettingsField>

              <SettingsField label="Mô tả">
                {(id) => (
                  <textarea
                    id={id}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    className={cn(settingsInputClass, "h-auto py-2.5")}
                    maxLength={500}
                  />
                )}
              </SettingsField>

              <div className="grid max-w-xl gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-body-sm font-medium text-primary">
                    Workspace ID
                  </p>
                  <p className="mt-1 break-all font-mono text-caption text-tertiary">
                    {workspace.id}
                  </p>
                </div>
                <div>
                  <p className="text-body-sm font-medium text-primary">
                    Ngày tạo
                  </p>
                  <p className="mt-1 text-caption text-tertiary">
                    {formatDate(workspace.created_at)}
                  </p>
                </div>
              </div>
            </fieldset>

            {saveError ? <SettingsErrorState message={saveError} /> : null}
          </SettingsSection>

          {isAdmin ? (
            <SettingsSection
              title="Vùng nguy hiểm"
              description="Các thao tác không thể hoàn tác dễ dàng."
              tone="danger"
            >
              <SettingsDangerZone
                title="Xoá Workspace"
                description="Xoá vĩnh viễn Workspace này và dữ liệu liên quan (soft-delete phía máy chủ)."
                actionLabel="Xoá Workspace"
                onAction={() => {
                  setDeleteError(null);
                  setDeleteOpen(true);
                }}
              />
            </SettingsSection>
          ) : null}

          <SettingsSaveBar
            dirty={dirty && isAdmin}
            saving={saving}
            onDiscard={handleDiscard}
            onSave={() => void handleSave()}
          />
        </>
      ) : null}

      <DeleteWorkspaceDialog
        open={deleteOpen}
        workspaceName={workspace?.name ?? ""}
        confirming={deleting}
        error={deleteError}
        onCancel={() => {
          if (!deleting) setDeleteOpen(false);
        }}
        onConfirm={() => void handleDelete()}
      />

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </SettingsLayout>
  );
}
