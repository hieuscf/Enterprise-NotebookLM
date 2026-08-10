/**
 * =============================================================================
 * File: Sidebar.tsx
 * Module/Service: Web App shell
 * Layer: UI
 * Purpose: Persistent left navigation grouped by product area (Knowledge / AI
 *          Tools / Management), matching the enterprise reference layout.
 * Responsibilities:
 *   - Render brand mark + grouped nav links
 *   - Disable/badge nav items for modules not yet implemented (honest UI)
 *   - Render signed-in user footer + logout
 *   - Support mobile off-canvas drawer (controlled by AppShell)
 * Dependencies:
 *   - next/link, lucide-react, lib/utils
 * Public Exports:
 *   - Sidebar, type SidebarActiveKey
 * Database/Table: N/A
 * Related Modules: features/shell/AppShell.tsx
 * Important Notes: "home", "workspaces", "members", "upload", "documents",
 *   "search", "chat", "comparisons", "reports" (when a workspaceId is in
 *   context) and "admin" (entry into the dedicated Admin Console at /admin)
 *   are real routes today. Everything else must stay visibly disabled — never
 *   link to a page that 404s.
 * =============================================================================
 */

"use client";

import {
  FileBarChart2,
  FileText,
  GitCompare,
  Hash,
  Home,
  Layers,
  LogOut,
  type LucideIcon,
  MessageSquare,
  Network,
  ScrollText,
  Search,
  Settings,
  Shield,
  Sparkles,
  UploadCloud,
  Users,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";

import { canAccessAdmin } from "@/lib/rbac";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

export type SidebarActiveKey =
  | "home"
  | "workspaces"
  | "members"
  | "upload"
  | "documents"
  | "search"
  | "chat"
  | "comparisons"
  | "reports"
  | "admin";

type NavItem = {
  key?: SidebarActiveKey;
  label: string;
  icon: LucideIcon;
  href?: string;
  /** Static badge for not-yet-built modules; ignored once `href` resolves. */
  badge?: string;
  /** Marks items whose href depends on the current workspaceId. */
  contextual?:
    | "members"
    | "upload"
    | "documents"
    | "search"
    | "chat"
    | "comparisons"
    | "reports";
};

type NavGroup = {
  label?: string;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    items: [{ key: "home", label: "Tổng quan", icon: Home, href: "/" }],
  },
  {
    label: "Knowledge",
    items: [
      {
        key: "documents",
        label: "Tài liệu",
        icon: FileText,
        contextual: "documents",
        badge: "Chọn workspace",
      },
      {
        key: "upload",
        label: "Tải lên tài liệu",
        icon: UploadCloud,
        contextual: "upload",
        badge: "Chọn workspace",
      },
      {
        key: "search",
        label: "Tìm kiếm",
        icon: Search,
        contextual: "search",
        badge: "Chọn workspace",
      },
      { label: "Chủ đề", icon: Hash, badge: "Sắp có" },
      { label: "Knowledge Graph", icon: Network, badge: "Sắp có" },
    ],
  },
  {
    label: "AI Tools",
    items: [
      {
        key: "chat",
        label: "AI Chat",
        icon: MessageSquare,
        contextual: "chat",
        badge: "Chọn workspace",
      },
      { label: "Tóm tắt", icon: ScrollText, badge: "Sắp có" },
      { label: "Trích xuất", icon: Wand2, badge: "Sắp có" },
      {
        key: "comparisons",
        label: "So sánh",
        icon: GitCompare,
        contextual: "comparisons",
        badge: "Chọn workspace",
      },
      {
        key: "reports",
        label: "Báo cáo",
        icon: FileBarChart2,
        contextual: "reports",
        badge: "Chọn workspace",
      },
    ],
  },
  {
    label: "Management",
    items: [
      {
        key: "workspaces",
        label: "Workspaces",
        icon: Layers,
        href: "/workspaces",
      },
      {
        key: "members",
        label: "Thành viên",
        icon: Users,
        contextual: "members",
        badge: "Chọn workspace",
      },
      {
        key: "admin",
        label: "Admin Console",
        icon: Shield,
        href: "/admin",
      },
      { label: "Cài đặt", icon: Settings, badge: "Sắp có" },
    ],
  },
];

function initialsOf(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return trimmed
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

type Props = {
  active: SidebarActiveKey;
  user: User | null;
  /** Current workspace in view (detail/members pages) — enables the contextual "Thành viên" link. */
  workspaceId?: string | null;
  mobileOpen: boolean;
  onClose: () => void;
};

export function Sidebar({
  active,
  user,
  workspaceId = null,
  mobileOpen,
  onClose,
}: Props) {
  const showAdminConsole = canAccessAdmin(user);

  return (
    <>
      {mobileOpen ? (
        <div
          aria-hidden
          onClick={onClose}
          className="fixed inset-0 z-30 bg-slate-950/40 md:hidden"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-border-default bg-surface",
          "transition-transform duration-200 md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border-default px-4">
          <Link href="/" className="flex min-w-0 items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-primary-soft">
              <Sparkles className="h-4 w-4 text-accent-primary" aria-hidden />
            </span>
            <span className="truncate text-h3 font-semibold text-primary">
              NotebookLM <span className="text-secondary">Enterprise</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng menu"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-secondary hover:bg-elevated md:hidden"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <nav
          aria-label="Điều hướng chính"
          className="flex-1 overflow-y-auto px-3 py-4"
        >
          {NAV_GROUPS.map((group, gi) => (
            <div key={group.label ?? `group-${gi}`} className={gi > 0 ? "mt-5" : undefined}>
              {group.label ? (
                <p className="px-3 pb-1.5 text-caption font-semibold uppercase tracking-wider text-tertiary">
                  {group.label}
                </p>
              ) : null}
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  if (item.key === "admin" && !showAdminConsole) {
                    return null;
                  }
                  const isActive = item.key === active;
                  const Icon = item.icon;
                  const href = workspaceId
                    ? item.contextual === "members"
                      ? `/workspaces/${workspaceId}/members`
                      : item.contextual === "upload"
                        ? `/workspaces/${workspaceId}/upload`
                        : item.contextual === "documents"
                          ? `/workspaces/${workspaceId}/documents`
                          : item.contextual === "search"
                            ? `/workspaces/${workspaceId}/search`
                            : item.contextual === "chat"
                              ? `/workspaces/${workspaceId}/chat`
                              : item.contextual === "comparisons"
                                ? `/workspaces/${workspaceId}/comparisons`
                                : item.contextual === "reports"
                                  ? `/workspaces/${workspaceId}/reports`
                                  : item.href
                    : item.href;

                  if (href) {
                    return (
                      <li key={item.label}>
                        <Link
                          href={href}
                          onClick={onClose}
                          className={cn(
                            "flex items-center gap-3 rounded-md px-3 py-2 text-body-sm font-medium transition-colors",
                            isActive
                              ? "bg-accent-primary-soft text-accent-primary"
                              : "text-secondary hover:bg-elevated hover:text-primary",
                          )}
                        >
                          <Icon className="h-4 w-4 shrink-0" aria-hidden />
                          <span className="truncate">{item.label}</span>
                        </Link>
                      </li>
                    );
                  }

                  return (
                    <li key={item.label}>
                      <div
                        aria-disabled
                        title={`${item.label} — ${item.badge}`}
                        className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-body-sm font-medium text-tertiary/70"
                      >
                        <Icon className="h-4 w-4 shrink-0" aria-hidden />
                        <span className="truncate">{item.label}</span>
                        {item.badge ? (
                          <span className="ml-auto shrink-0 rounded-full bg-elevated px-1.5 py-0.5 text-[10px] font-medium text-tertiary">
                            {item.badge}
                          </span>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="shrink-0 border-t border-border-default p-3">
          <div className="flex items-center gap-2.5 rounded-md px-1 py-1.5">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-tertiary-soft text-body-sm font-semibold text-accent-tertiary">
              {user ? initialsOf(user.full_name) : "?"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-body-sm font-medium text-primary">
                {user ? user.full_name : "Đang tải…"}
              </p>
              <p className="truncate text-caption text-tertiary">
                {user ? user.email : ""}
              </p>
            </div>
            <Link
              href="/logout"
              title="Đăng xuất"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-tertiary hover:bg-elevated hover:text-danger"
            >
              <LogOut className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
}
