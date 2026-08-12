/**
 * =============================================================================
 * File: NotificationSettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Workspace notification preference toggles (device-local).
 * Responsibilities:
 *   - Preference rows with switches; toast on change
 * Dependencies:
 *   - preferences.ts, Settings* components
 * Public Exports:
 *   - NotificationSettings
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/settings/notifications/page.tsx
 * Important Notes: No notifications API — stored locally, not presented as server save.
 * =============================================================================
 */

"use client";

import { useEffect, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import {
  loadPreferences,
  updatePreferences,
  type NotificationPreferences,
  type UserPreferences,
} from "@/features/settings/preferences";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsRow } from "@/features/settings/SettingsRow";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { SettingsSwitch } from "@/features/settings/SettingsSwitch";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";

type Props = {
  workspaceId: string;
};

const ROWS: {
  key: keyof NotificationPreferences;
  label: string;
  group: "documents" | "workspace" | "system";
}[] = [
  {
    key: "documentCompleted",
    label: "Xử lý tài liệu hoàn tất",
    group: "documents",
  },
  {
    key: "documentFailed",
    label: "Xử lý tài liệu thất bại",
    group: "documents",
  },
  {
    key: "invitations",
    label: "Lời mời Workspace",
    group: "workspace",
  },
  {
    key: "memberAccessChanges",
    label: "Thay đổi quyền thành viên",
    group: "workspace",
  },
  {
    key: "systemAlerts",
    label: "Cảnh báo hệ thống",
    group: "system",
  },
  {
    key: "serviceInterruptions",
    label: "Gián đoạn dịch vụ",
    group: "system",
  },
];

export function NotificationSettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);
  const { toasts, dismiss, pushSuccess } = useToasts();
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);

  useEffect(() => {
    setPrefs(loadPreferences());
  }, []);

  function toggle(key: keyof NotificationPreferences, checked: boolean) {
    if (!prefs) return;
    const next = {
      ...prefs,
      notifications: { ...prefs.notifications, [key]: checked },
    };
    setPrefs(next);
    updatePreferences(next);
    pushSuccess("Đã cập nhật tuỳ chọn.");
  }

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="notifications"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Thông báo"
        description="Chọn sự kiện Workspace bạn muốn nhận."
      />

      <p className="mb-2 max-w-2xl text-caption text-tertiary">
        Tuỳ chọn lưu trên thiết bị. Kênh thông báo đẩy chưa có trong hợp đồng API.
      </p>

      <SettingsSection title="Tài liệu">
        {!prefs ? null : (
          <div className="max-w-2xl divide-y divide-border-default">
            {ROWS.filter((r) => r.group === "documents").map((row) => (
              <SettingsRow key={row.key} label={row.label} htmlFor={`n-${row.key}`}>
                <SettingsSwitch
                  id={`n-${row.key}`}
                  label={row.label}
                  checked={prefs.notifications[row.key]}
                  onCheckedChange={(checked) => toggle(row.key, checked)}
                />
              </SettingsRow>
            ))}
          </div>
        )}
      </SettingsSection>

      <SettingsSection title="Workspace">
        {!prefs ? null : (
          <div className="max-w-2xl divide-y divide-border-default">
            {ROWS.filter((r) => r.group === "workspace").map((row) => (
              <SettingsRow key={row.key} label={row.label} htmlFor={`n-${row.key}`}>
                <SettingsSwitch
                  id={`n-${row.key}`}
                  label={row.label}
                  checked={prefs.notifications[row.key]}
                  onCheckedChange={(checked) => toggle(row.key, checked)}
                />
              </SettingsRow>
            ))}
          </div>
        )}
      </SettingsSection>

      <SettingsSection title="Hệ thống">
        {!prefs ? null : (
          <div className="max-w-2xl divide-y divide-border-default">
            {ROWS.filter((r) => r.group === "system").map((row) => (
              <SettingsRow key={row.key} label={row.label} htmlFor={`n-${row.key}`}>
                <SettingsSwitch
                  id={`n-${row.key}`}
                  label={row.label}
                  checked={prefs.notifications[row.key]}
                  onCheckedChange={(checked) => toggle(row.key, checked)}
                />
              </SettingsRow>
            ))}
          </div>
        )}
      </SettingsSection>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </SettingsLayout>
  );
}
