/**
 * =============================================================================
 * File: settings-nav.ts
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Shared navigation metadata for the Workspace Settings experience.
 * Responsibilities:
 *   - Define section ids, labels, icons, and route segments
 *   - Separate user settings from administration sections
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - SettingsSectionId, SETTINGS_NAV_GROUPS, settingsHref
 * Database/Table: N/A
 * Related Modules: features/settings/SettingsSidebar.tsx
 * Important Notes: Routes are workspace-scoped under /workspaces/[id]/settings/*.
 * =============================================================================
 */

import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bell,
  Building2,
  ChartColumn,
  Palette,
  Shield,
  Sparkles,
  User,
  Users,
} from "lucide-react";

export type SettingsSectionId =
  | "general"
  | "workspace"
  | "members"
  | "security"
  | "ai"
  | "notifications"
  | "appearance"
  | "usage"
  | "observability";

export type SettingsNavItem = {
  id: SettingsSectionId;
  label: string;
  description: string;
  icon: LucideIcon;
  /** When true, only Platform Manage users see this nav item. */
  adminOnly?: boolean;
};

export type SettingsNavGroup = {
  label: string;
  items: SettingsNavItem[];
};

export const SETTINGS_NAV_GROUPS: SettingsNavGroup[] = [
  {
    label: "Cài đặt",
    items: [
      {
        id: "general",
        label: "Chung",
        description: "Quản lý tài khoản và tuỳ chọn cá nhân.",
        icon: User,
      },
      {
        id: "workspace",
        label: "Workspace",
        description: "Quản lý Workspace hiện tại.",
        icon: Building2,
      },
      {
        id: "members",
        label: "Thành viên & quyền",
        description: "Quản lý ai có quyền truy cập Workspace này.",
        icon: Users,
      },
      {
        id: "security",
        label: "Bảo mật",
        description: "Quản lý xác thực và bảo mật tài khoản.",
        icon: Shield,
      },
      {
        id: "ai",
        label: "AI & Retrieval",
        description: "Kiểm soát cách AI sử dụng tri thức Workspace.",
        icon: Sparkles,
      },
      {
        id: "notifications",
        label: "Thông báo",
        description: "Chọn sự kiện Workspace bạn muốn nhận.",
        icon: Bell,
      },
      {
        id: "appearance",
        label: "Giao diện",
        description: "Tuỳ chỉnh giao diện Enterprise NotebookLM.",
        icon: Palette,
      },
    ],
  },
  {
    label: "Quản trị",
    items: [
      {
        id: "usage",
        label: "Sử dụng & chi phí",
        description: "Theo dõi mức sử dụng AI của Workspace.",
        icon: ChartColumn,
        adminOnly: true,
      },
      {
        id: "observability",
        label: "Quan sát hệ thống",
        description: "Theo dõi sức khoẻ hệ thống tri thức Workspace.",
        icon: Activity,
        adminOnly: true,
      },
    ],
  },
];

export function settingsHref(
  workspaceId: string,
  section: SettingsSectionId,
): string {
  return `/workspaces/${workspaceId}/settings/${section}`;
}

export function findSettingsNavItem(
  section: SettingsSectionId,
): SettingsNavItem | undefined {
  for (const group of SETTINGS_NAV_GROUPS) {
    const item = group.items.find((i) => i.id === section);
    if (item) return item;
  }
  return undefined;
}
