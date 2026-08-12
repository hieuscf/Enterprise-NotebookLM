/**
 * =============================================================================
 * File: SettingsPermissionState.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Restricted-access empty state for Settings sections.
 * Responsibilities:
 *   - Explain missing permission without replacing the whole shell
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - SettingsPermissionState
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Backend remains authoritative — this only reflects UI gates.
 * =============================================================================
 */

import { ShieldAlert } from "lucide-react";

type Props = {
  title?: string;
  description?: string;
};

export function SettingsPermissionState({
  title = "Hạn chế quyền truy cập",
  description = "Bạn không có quyền sửa cài đặt Workspace này. Liên hệ quản trị viên Workspace.",
}: Props) {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-md border border-border-default bg-elevated/40 px-4 py-5"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-elevated">
        <ShieldAlert className="h-4 w-4 text-tertiary" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-body-sm font-medium text-primary">{title}</p>
        <p className="mt-1 text-body-sm text-secondary">{description}</p>
      </div>
    </div>
  );
}
