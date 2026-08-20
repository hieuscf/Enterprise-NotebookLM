/**
 * =============================================================================
 * File: AppShell.tsx
 * Module/Service: Web App shell
 * Layer: UI
 * Purpose: App-wide layout (sidebar + top bar + content) shared by every
 *          authenticated page, replacing the old top-only AppHeader.
 * Responsibilities:
 *   - Compose Sidebar with a top bar (mobile menu toggle, global search
 *     placeholder, notifications placeholder)
 *   - Own the mobile drawer open/close state
 * Dependencies:
 *   - features/shell/Sidebar, lucide-react
 * Public Exports:
 *   - AppShell
 * Database/Table: N/A
 * Related Modules: app/page.tsx, features/workspaces/WorkspaceListView,
 *   features/workspaces/WorkspaceDetailView, features/workspaces/WorkspaceMembersView
 * Important Notes: Shell is locked to the viewport (h-svh overflow-hidden).
 *   Sidebar nav scrolls independently; page content scrolls inside <main>.
 *   Search is live when workspaceId is set. Notifications remain a visual
 *   placeholder until a notifications API exists. Settings live under
 *   /workspaces/[id]/settings/*.
 * =============================================================================
 */

"use client";

import { Bell, Menu, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Sidebar, type SidebarActiveKey } from "@/features/shell/Sidebar";
import { useAuth } from "@/hooks/useAuth";
import type { User } from "@/types/auth";

type Props = {
  active: SidebarActiveKey;
  user?: User | null;
  /** Current workspace in view — forwarded to Sidebar for the contextual "Thành viên" link. */
  workspaceId?: string | null;
  children: React.ReactNode;
};

export function AppShell({ active, user: userProp = null, workspaceId, children }: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user: authUser, loading: authLoading } = useAuth();
  const user = userProp ?? authUser;

  return (
    <div className="flex h-svh overflow-hidden bg-base">
      <Sidebar
        active={active}
        user={user}
        userLoading={authLoading && !user}
        workspaceId={workspaceId}
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

          <div className="relative hidden max-w-md flex-1 sm:block">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
              aria-hidden
            />
            {workspaceId ? (
              <Link
                href={`/workspaces/${workspaceId}/search`}
                className="flex h-10 w-full items-center rounded-md border border-border-default bg-base pl-9 pr-3 text-body-sm text-tertiary transition-colors hover:border-accent-primary/40 hover:bg-surface hover:text-secondary"
              >
                Tìm kiếm trong Workspace…
              </Link>
            ) : (
              <input
                type="search"
                disabled
                title="Chọn workspace để tìm kiếm"
                placeholder="Tìm kiếm trong Workspace… (chọn workspace)"
                className="h-10 w-full cursor-not-allowed rounded-md border border-border-default bg-elevated/60 pl-9 pr-3 text-body-sm text-tertiary placeholder:text-tertiary"
              />
            )}
          </div>
          <div className="flex-1 sm:hidden" />

          <button
            type="button"
            disabled
            title="Thông báo — sắp có"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-tertiary hover:bg-elevated disabled:cursor-not-allowed"
          >
            <Bell className="h-4 w-4" aria-hidden />
          </button>
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain">{children}</main>
      </div>
    </div>
  );
}
