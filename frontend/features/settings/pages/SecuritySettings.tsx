/**
 * =============================================================================
 * File: SecuritySettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Authentication & session security — honest about available controls.
 * Responsibilities:
 *   - Show OAuth2/JWT auth method without exposing tokens
 *   - Current session summary + logout via /logout
 * Dependencies:
 *   - Settings* components, useAuth
 * Public Exports:
 *   - SecuritySettings
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/settings/security/page.tsx
 * Important Notes: No session-list / revoke-other API in OpenAPI — do not fake it.
 * =============================================================================
 */

"use client";

import { CheckCircle2, LogOut, Monitor } from "lucide-react";
import Link from "next/link";

import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
};

function detectClientLabel(): string {
  if (typeof navigator === "undefined") return "Trình duyệt hiện tại";
  const ua = navigator.userAgent;
  let browser = "Trình duyệt";
  if (ua.includes("Edg/")) browser = "Edge";
  else if (ua.includes("Chrome/")) browser = "Chrome";
  else if (ua.includes("Firefox/")) browser = "Firefox";
  else if (ua.includes("Safari/") && !ua.includes("Chrome/")) browser = "Safari";

  let os = "Hệ điều hành";
  if (ua.includes("Windows")) os = "Windows";
  else if (ua.includes("Mac OS")) os = "macOS";
  else if (ua.includes("Linux")) os = "Linux";
  else if (ua.includes("Android")) os = "Android";
  else if (ua.includes("iPhone") || ua.includes("iPad")) os = "iOS";

  return `${browser} · ${os}`;
}

export function SecuritySettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);
  const clientLabel = detectClientLabel();

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="security"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Bảo mật"
        description="Quản lý xác thực và bảo mật tài khoản."
      />

      <SettingsSection
        title="Xác thực"
        description="Enterprise NotebookLM sử dụng OAuth2 / JWT. Token không được hiển thị trên giao diện."
      >
        <div className="flex max-w-xl items-start gap-3 rounded-md border border-border-default px-4 py-4">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent-primary-soft">
            <CheckCircle2 className="h-4 w-4 text-accent-primary" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-body-sm font-medium text-primary">
              Phương thức xác thực
            </p>
            <p className="mt-0.5 text-body-sm text-secondary">OAuth2 / SSO · JWT</p>
            <p className="mt-2 inline-flex items-center gap-1.5 text-caption font-medium text-success">
              <span
                aria-hidden
                className="h-1.5 w-1.5 rounded-full bg-success"
              />
              Đã kết nối
            </p>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Phiên đăng nhập"
        description="Chỉ phiên hiện tại được biết trên thiết bị này. Máy chủ chưa cung cấp danh sách phiên khác."
      >
        <div className="flex max-w-xl items-start gap-3 rounded-md border border-border-default px-4 py-4">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-elevated">
            <Monitor className="h-4 w-4 text-secondary" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-body-sm font-medium text-primary">
              Phiên hiện tại
            </p>
            <p className="mt-0.5 text-body-sm text-secondary">{clientLabel}</p>
            <p className="mt-1 text-caption text-tertiary">Đang hoạt động</p>
          </div>
        </div>

        <div className="mt-2">
          <Link
            href="/logout"
            className={cn(
              "inline-flex h-10 items-center gap-2 rounded-md border border-border-default px-4",
              "text-body-sm font-medium text-secondary",
              "hover:bg-elevated hover:text-danger",
            )}
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Đăng xuất phiên này
          </Link>
        </div>
      </SettingsSection>
    </SettingsLayout>
  );
}
