/**
 * =============================================================================
 * File: AdminSidebar.tsx
 * Module/Service: Observability / Admin Console (Web App)
 * Layer: UI
 * Purpose: Dedicated left navigation for the Admin Console (`/admin/*`),
 *          separate from the product AppShell sidebar.
 * Responsibilities:
 *   - Render Admin Console brand + admin-only nav links
 *   - Provide a clear exit back to the main product app
 *   - Render signed-in user footer + logout
 *   - Support mobile off-canvas drawer (controlled by AdminShell)
 * Dependencies:
 *   - next/link, lucide-react, lib/utils
 * Public Exports:
 *   - AdminSidebar, type AdminSidebarActiveKey
 * Database/Table: N/A
 * Related Modules: features/admin/AdminShell.tsx
 * Important Notes: Dashboard, Workspaces, Documents, Pipeline, Query Logs, Users.
 * =============================================================================
 */

"use client";

import {
  ArrowLeft,
  Building2,
  FileText,
  GitBranch,
  type LucideIcon,
  LayoutDashboard,
  LogOut,
  Route,
  Shield,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

export type AdminSidebarActiveKey =
  | "dashboard"
  | "workspaces"
  | "documents"
  | "pipeline"
  | "query-logs"
  | "users";

type NavItem = {
  key: AdminSidebarActiveKey;
  label: string;
  icon: LucideIcon;
  href: string;
};

const NAV_ITEMS: NavItem[] = [
  {
    key: "dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    href: "/admin/dashboard",
  },
  {
    key: "workspaces",
    label: "Workspaces",
    icon: Building2,
    href: "/admin/workspaces",
  },
  {
    key: "documents",
    label: "Documents",
    icon: FileText,
    href: "/admin/documents",
  },
  {
    key: "pipeline",
    label: "Pipeline",
    icon: GitBranch,
    href: "/admin/pipeline",
  },
  {
    key: "query-logs",
    label: "Query Logs",
    icon: Route,
    href: "/admin/query-logs",
  },
  {
    key: "users",
    label: "Users",
    icon: Users,
    href: "/admin/users",
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
  active: AdminSidebarActiveKey;
  user: User | null;
  mobileOpen: boolean;
  onClose: () => void;
};

export function AdminSidebar({ active, user, mobileOpen, onClose }: Props) {
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
          <Link href="/admin/dashboard" className="flex min-w-0 items-center gap-2" onClick={onClose}>
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-primary-soft">
              <Shield className="h-4 w-4 text-accent-primary" aria-hidden />
            </span>
            <span className="truncate text-h3 font-semibold text-primary">
              Admin <span className="text-secondary">Console</span>
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

        <nav aria-label="Admin Console" className="flex-1 overflow-y-auto px-3 py-4">
          <p className="px-3 pb-1.5 text-caption font-semibold uppercase tracking-wider text-tertiary">
            Quản trị
          </p>
          <ul className="flex flex-col gap-0.5">
            {NAV_ITEMS.map((item) => {
              const isActive = item.key === active;
              const Icon = item.icon;
              return (
                <li key={item.key}>
                  <Link
                    href={item.href}
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
            })}
          </ul>

          <div className="mt-5 border-t border-border-default pt-4">
            <Link
              href="/"
              onClick={onClose}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary"
            >
              <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden />
              <span className="truncate">Về ứng dụng</span>
            </Link>
          </div>
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
