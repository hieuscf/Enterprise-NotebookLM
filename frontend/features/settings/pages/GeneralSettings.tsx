/**
 * =============================================================================
 * File: GeneralSettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Account profile settings — read-only (no PATCH /auth/me in contract).
 * Responsibilities:
 *   - Display full name, email, avatar initials from GET /auth/me
 *   - Clearly state that profile is managed by authentication
 * Dependencies:
 *   - SettingsLayout, useAuth, useSettingsWorkspace
 * Public Exports:
 *   - GeneralSettings
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/settings/general/page.tsx
 * Important Notes: Do not fake a successful profile save — OpenAPI has no update.
 * =============================================================================
 */

"use client";

import { SettingsField, settingsInputClass } from "@/features/settings/SettingsField";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsLoadingState } from "@/features/settings/SettingsLoadingState";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";

type Props = {
  workspaceId: string;
};

function initialsOf(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return trimmed
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export function GeneralSettings({ workspaceId }: Props) {
  const { user, loading: authLoading } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="general"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Chung"
        description="Quản lý tài khoản và tuỳ chọn cá nhân."
      />

      <SettingsSection
        title="Hồ sơ"
        description="Thông tin tài khoản dùng trên Enterprise NotebookLM."
      >
        {authLoading || !user ? (
          <SettingsLoadingState message="Đang tải hồ sơ…" />
        ) : (
          <div className="flex flex-col gap-5">
            <SettingsField label="Họ và tên">
              {(id) => (
                <input
                  id={id}
                  readOnly
                  value={user.full_name}
                  className={settingsInputClass}
                />
              )}
            </SettingsField>

            <SettingsField
              label="Email"
              description="Email chỉ đọc — xác thực được quản lý bởi hệ thống đăng nhập."
            >
              {(id) => (
                <input
                  id={id}
                  readOnly
                  value={user.email}
                  className={settingsInputClass}
                />
              )}
            </SettingsField>

            <SettingsField label="Ảnh đại diện">
              <div className="flex items-center gap-3">
                <span
                  aria-hidden
                  className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-tertiary-soft text-body font-semibold text-accent-tertiary"
                >
                  {initialsOf(user.full_name)}
                </span>
                <p className="text-body-sm text-tertiary">
                  Avatar đồng bộ từ thông tin tài khoản. Chưa hỗ trợ tải ảnh lên.
                </p>
              </div>
            </SettingsField>

            <p className="max-w-xl rounded-md border border-border-default bg-elevated/40 px-3 py-2.5 text-caption text-secondary">
              Cập nhật hồ sơ chưa có trong hợp đồng API hiện tại. Thông tin hiển
              thị theo phiên đăng nhập (OAuth2 / JWT).
            </p>
          </div>
        )}
      </SettingsSection>
    </SettingsLayout>
  );
}
