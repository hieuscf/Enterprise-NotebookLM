/**
 * =============================================================================
 * File: SettingsLayout.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Two-column Settings chrome inside AppShell.
 * Responsibilities:
 *   - Compose AppShell + SettingsSidebar + content pane
 *   - Scope settings to the current Workspace
 * Dependencies:
 *   - features/shell/AppShell, SettingsSidebar, settings-nav
 * Public Exports:
 *   - SettingsLayout
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Active AppShell key is "settings".
 * =============================================================================
 */

"use client";

import { AppShell } from "@/features/shell/AppShell";
import { SettingsSidebar } from "@/features/settings/SettingsSidebar";
import type { SettingsSectionId } from "@/features/settings/settings-nav";
import type { User } from "@/types/auth";

type Props = {
  workspaceId: string;
  active: SettingsSectionId;
  user: User | null;
  workspaceName?: string | null;
  children: React.ReactNode;
};

export function SettingsLayout({
  workspaceId,
  active,
  user,
  workspaceName,
  children,
}: Props) {
  return (
    <AppShell active="settings" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 sm:px-6 sm:py-8">
        {workspaceName ? (
          <p className="text-caption text-tertiary">
            Workspace ·{" "}
            <span className="font-medium text-secondary">{workspaceName}</span>
          </p>
        ) : null}

        <div className="flex flex-col gap-2 lg:flex-row lg:gap-10">
          <SettingsSidebar
            workspaceId={workspaceId}
            active={active}
            user={user}
          />
          <div className="min-w-0 flex-1 pb-16 lg:max-w-[920px]">{children}</div>
        </div>
      </div>
    </AppShell>
  );
}
