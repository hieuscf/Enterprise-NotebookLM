/**
 * =============================================================================
 * File: ThemeBootstrap.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Apply saved theme/density on first paint (FOUC-safe inline script).
 * Responsibilities:
 *   - Inject a tiny before-hydration script reading localStorage preferences
 * Dependencies:
 *   - features/settings/preferences (storage key)
 * Public Exports:
 *   - ThemeBootstrap
 * Database/Table: N/A
 * Related Modules: app/layout.tsx, features/settings/preferences.ts
 * Important Notes: Must stay in sync with PREFERENCES_STORAGE_KEY + defaults.
 * =============================================================================
 */

import { PREFERENCES_STORAGE_KEY } from "@/features/settings/preferences";

/**
 * Inline script — runs before React hydrates so dark mode doesn't flash.
 * Kept as a string to avoid bundling localStorage access into SSR.
 */
const BOOTSTRAP_SCRIPT = `
(function () {
  try {
    var key = ${JSON.stringify(PREFERENCES_STORAGE_KEY)};
    var raw = localStorage.getItem(key);
    var theme = "system";
    var density = "standard";
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && (parsed.theme === "light" || parsed.theme === "dark" || parsed.theme === "system")) {
        theme = parsed.theme;
      }
      if (parsed && (parsed.density === "comfortable" || parsed.density === "standard" || parsed.density === "compact")) {
        density = parsed.density;
      }
    }
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var dark = theme === "dark" || (theme === "system" && prefersDark);
    var root = document.documentElement;
    root.classList.toggle("dark", dark);
    root.dataset.theme = theme;
    root.dataset.density = density;
  } catch (e) {}
})();
`;

export function ThemeBootstrap() {
  return (
    <script
      dangerouslySetInnerHTML={{ __html: BOOTSTRAP_SCRIPT }}
      suppressHydrationWarning
    />
  );
}
