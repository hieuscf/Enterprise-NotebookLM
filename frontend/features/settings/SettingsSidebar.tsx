/**
 * =============================================================================
 * File: SettingsSidebar.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Quiet vertical navigation for Workspace Settings sections.
 * Responsibilities:
 *   - Render SETTINGS / ADMINISTRATION groups with subtle active state
 *   - Hide admin-only items unless Platform Manage
 *   - Provide mobile select fallback
 * Dependencies:
 *   - next/link, lucide-react, settings-nav, lib/rbac, lib/utils
 * Public Exports:
 *   - SettingsSidebar
 * Database/Table: N/A
 * Related Modules: features/settings/SettingsLayout.tsx
 * Important Notes: Active state mirrors developer-tool precision — soft bg + accent.
 * =============================================================================
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  SETTINGS_NAV_GROUPS,
  settingsHref,
  type SettingsSectionId,
} from "@/features/settings/settings-nav";
import { canAccessAdmin } from "@/lib/rbac";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

type Props = {
  workspaceId: string;
  active: SettingsSectionId;
  user: User | null;
};

export function SettingsSidebar({ workspaceId, active, user }: Props) {
  const router = useRouter();
  const showAdmin = canAccessAdmin(user);

  const visibleGroups = SETTINGS_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.adminOnly || showAdmin),
  })).filter((group) => group.items.length > 0);

  const mobileOptions = visibleGroups.flatMap((g) => g.items);

  return (
    <>
      {/* Mobile: compact select */}
      <div className="mb-6 lg:hidden">
        <label htmlFor="settings-section-mobile" className="sr-only">
          Mục cài đặt
        </label>
        <select
          id="settings-section-mobile"
          value={active}
          onChange={(e) => {
            router.push(
              settingsHref(workspaceId, e.target.value as SettingsSectionId),
            );
          }}
          className={cn(
            "h-11 w-full cursor-pointer rounded-md border border-border-default bg-surface px-3",
            "text-body-sm font-medium text-primary outline-none",
            "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
          )}
        >
          {mobileOptions.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      {/* Desktop / tablet sidebar */}
      <nav
        aria-label="Điều hướng cài đặt"
        className="hidden w-[220px] shrink-0 lg:block xl:w-[240px]"
      >
        <div className="sticky top-20 flex flex-col gap-6">
          {visibleGroups.map((group) => (
            <div key={group.label}>
              <p className="px-2.5 pb-1.5 text-caption font-semibold uppercase tracking-wider text-tertiary">
                {group.label}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = item.id === active;
                  return (
                    <li key={item.id}>
                      <Link
                        href={settingsHref(workspaceId, item.id)}
                        aria-current={isActive ? "page" : undefined}
                        className={cn(
                          "group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-body-sm font-medium transition-colors",
                          isActive
                            ? "bg-accent-primary-soft text-accent-primary"
                            : "text-secondary hover:bg-elevated hover:text-primary",
                        )}
                      >
                        {isActive ? (
                          <span
                            aria-hidden
                            className="absolute top-1/2 left-0 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent-primary"
                          />
                        ) : null}
                        <Icon className="h-4 w-4 shrink-0" aria-hidden />
                        <span className="truncate">{item.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>
    </>
  );
}
