/**
 * =============================================================================
 * File: AdminShell.tsx
 * Module/Service: Observability / Admin Console (Web App)
 * Layer: UI
 * Purpose: Dedicated layout shell for `/admin/*` — separate from the product
 *          AppShell so Admin Console navigation does not mix with Knowledge /
 *          AI Tools workspace chrome.
 * Responsibilities:
 *   - Compose AdminSidebar with a top bar (mobile menu toggle)
 *   - Own mobile drawer open/close state
 * Dependencies:
 *   - features/admin/AdminSidebar, lucide-react
 * Public Exports:
 *   - AdminShell
 * Database/Table: N/A
 * Related Modules: AdminDashboardView, AdminWorkspacesView,
 *   AdminWorkspaceDetailView
 * Important Notes: Keep visual tokens aligned with AppShell; only the nav
 *   surface and top-bar purpose differ. Viewport lock matches AppShell
 *   (h-svh overflow-hidden; sidebar nav scrolls independently).
 * =============================================================================
 */

"use client";

import { Menu, Shield } from "lucide-react";
import { useState } from "react";

import {
  AdminSidebar,
  type AdminSidebarActiveKey,
} from "@/features/admin/AdminSidebar";
import type { User } from "@/types/auth";

type Props = {
  active: AdminSidebarActiveKey;
  user: User | null;
  children: React.ReactNode;
};

export function AdminShell({ active, user, children }: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-svh overflow-hidden bg-base">
      <AdminSidebar
        active={active}
        user={user}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-20 flex h-16 shrink-0 items-center gap-3 border-b border-border-default bg-surface px-4 sm:px-6">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Mở menu"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-secondary hover:bg-elevated md:hidden"
          >
            <Menu className="h-5 w-5" aria-hidden />
          </button>

          <div className="flex min-w-0 items-center gap-2 text-body-sm text-secondary">
            <Shield className="hidden h-4 w-4 shrink-0 text-accent-primary sm:block" aria-hidden />
            <span className="truncate font-medium text-primary">Admin Console</span>
            <span className="hidden text-tertiary sm:inline">·</span>
            <span className="hidden truncate text-tertiary sm:inline">
              Observability &amp; workspace management
            </span>
          </div>
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain">{children}</main>
      </div>
    </div>
  );
}
