/**
 * =============================================================================
 * File: AppearanceSettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Theme + interface density preferences (client-side .dark tokens).
 * Responsibilities:
 *   - Theme selector (Light / System / Dark) using existing CSS variables
 *   - Density preference stored for future spacing system
 * Dependencies:
 *   - preferences.ts, Settings* components
 * Public Exports:
 *   - AppearanceSettings
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/settings/appearance/page.tsx
 * Important Notes: Reuses .dark in globals.css — no second theme system.
 *   Localization selector omitted — app is Vietnamese-only today.
 * =============================================================================
 */

"use client";

import { Moon, Monitor, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import {
  applyAppearance,
  loadPreferences,
  updatePreferences,
  type DensityPreference,
  type ThemePreference,
  type UserPreferences,
} from "@/features/settings/preferences";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
};

const THEMES: {
  id: ThemePreference;
  label: string;
  icon: typeof Sun;
}[] = [
  { id: "light", label: "Sáng", icon: Sun },
  { id: "system", label: "Hệ thống", icon: Monitor },
  { id: "dark", label: "Tối", icon: Moon },
];

const DENSITIES: {
  id: DensityPreference;
  label: string;
  description: string;
}[] = [
  {
    id: "comfortable",
    label: "Thoải mái",
    description: "Khoảng cách rộng hơn — sắp sẵn cho mật độ giao diện tương lai.",
  },
  {
    id: "standard",
    label: "Tiêu chuẩn",
    description: "Mật độ mặc định của Enterprise NotebookLM.",
  },
  {
    id: "compact",
    label: "Gọn",
    description: "Khoảng cách chặt hơn — sẵn sàng khi hệ thống mật độ được áp dụng.",
  },
];

export function AppearanceSettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);
  const { toasts, dismiss, pushSuccess } = useToasts();
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);

  useEffect(() => {
    const loaded = loadPreferences();
    setPrefs(loaded);
    applyAppearance(loaded);
  }, []);

  useEffect(() => {
    if (!prefs || prefs.theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyAppearance(prefs);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [prefs]);

  function setTheme(theme: ThemePreference) {
    if (!prefs) return;
    const next = { ...prefs, theme };
    setPrefs(next);
    updatePreferences(next);
    pushSuccess("Đã cập nhật giao diện.");
  }

  function setDensity(density: DensityPreference) {
    if (!prefs) return;
    const next = { ...prefs, density };
    setPrefs(next);
    updatePreferences(next);
    pushSuccess("Đã cập nhật mật độ giao diện.");
  }

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="appearance"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Giao diện"
        description="Tuỳ chỉnh cách Enterprise NotebookLM hiển thị."
      />

      <SettingsSection title="Chủ đề" description="Mặc định: theo hệ thống.">
        {!prefs ? null : (
          <div
            className="grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-3"
            role="radiogroup"
            aria-label="Chủ đề"
          >
            {THEMES.map((theme) => {
              const Icon = theme.icon;
              const selected = prefs.theme === theme.id;
              return (
                <button
                  key={theme.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setTheme(theme.id)}
                  className={cn(
                    "flex flex-col items-center gap-2 rounded-md border px-4 py-5 transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
                    selected
                      ? "border-accent-primary/50 bg-accent-primary-soft/50 text-accent-primary"
                      : "border-border-default text-secondary hover:bg-elevated",
                  )}
                >
                  <Icon className="h-5 w-5" aria-hidden />
                  <span className="text-body-sm font-medium">{theme.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        title="Mật độ giao diện"
        description="Tuỳ chọn được lưu sẵn; ứng dụng sẽ tôn trọng khi hệ thống mật độ được triển khai rộng."
      >
        {!prefs ? null : (
          <div
            className="flex max-w-xl flex-col gap-2"
            role="radiogroup"
            aria-label="Mật độ giao diện"
          >
            {DENSITIES.map((d) => {
              const selected = prefs.density === d.id;
              return (
                <label
                  key={d.id}
                  className={cn(
                    "flex cursor-pointer gap-3 rounded-md border px-3.5 py-3 transition-colors",
                    selected
                      ? "border-accent-primary/40 bg-accent-primary-soft/40"
                      : "border-border-default hover:bg-elevated/60",
                  )}
                >
                  <input
                    type="radio"
                    name="density"
                    value={d.id}
                    checked={selected}
                    onChange={() => setDensity(d.id)}
                    className="mt-1 accent-[var(--accent-primary)]"
                  />
                  <span>
                    <span className="block text-body-sm font-medium text-primary">
                      {d.label}
                    </span>
                    <span className="mt-0.5 block text-caption text-tertiary">
                      {d.description}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </SettingsSection>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </SettingsLayout>
  );
}
