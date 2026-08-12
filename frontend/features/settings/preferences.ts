/**
 * =============================================================================
 * File: preferences.ts
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Device-local user preferences for Settings (no OpenAPI endpoint yet).
 * Responsibilities:
 *   - Read/write preferences from localStorage
 *   - Provide defaults for AI, citations, notifications, appearance
 * Dependencies:
 *   - None
 * Public Exports:
 *   - UserPreferences, DEFAULT_PREFERENCES, loadPreferences, savePreferences,
 *     updatePreferences
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Explicitly device-local — never present as a server save.
 *   Integration point for a future preferences API is isolated here.
 * =============================================================================
 */

export type ThemePreference = "light" | "dark" | "system";
export type DensityPreference = "comfortable" | "standard" | "compact";
export type ResponseStylePreference = "concise" | "balanced" | "detailed";

export type CitationPreferences = {
  showInAnswers: boolean;
  openSourceOnSelect: boolean;
  highlightCitedText: boolean;
};

export type KnowledgeSourcePreferences = {
  knowledgeGraph: boolean;
  vectorSearch: boolean;
  fullTextSearch: boolean;
};

export type NotificationPreferences = {
  documentCompleted: boolean;
  documentFailed: boolean;
  invitations: boolean;
  memberAccessChanges: boolean;
  systemAlerts: boolean;
  serviceInterruptions: boolean;
};

export type UserPreferences = {
  theme: ThemePreference;
  density: DensityPreference;
  responseStyle: ResponseStylePreference;
  citations: CitationPreferences;
  knowledgeSources: KnowledgeSourcePreferences;
  notifications: NotificationPreferences;
};

export const PREFERENCES_STORAGE_KEY = "enlm.settings.preferences.v1";

export const DEFAULT_PREFERENCES: UserPreferences = {
  theme: "system",
  density: "standard",
  responseStyle: "balanced",
  citations: {
    showInAnswers: true,
    openSourceOnSelect: true,
    highlightCitedText: true,
  },
  knowledgeSources: {
    knowledgeGraph: true,
    vectorSearch: true,
    fullTextSearch: true,
  },
  notifications: {
    documentCompleted: true,
    documentFailed: true,
    invitations: true,
    memberAccessChanges: true,
    systemAlerts: true,
    serviceInterruptions: true,
  },
};

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof localStorage !== "undefined";
}

function mergePreferences(raw: unknown): UserPreferences {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_PREFERENCES };
  const data = raw as Partial<UserPreferences>;
  return {
    theme:
      data.theme === "light" || data.theme === "dark" || data.theme === "system"
        ? data.theme
        : DEFAULT_PREFERENCES.theme,
    density:
      data.density === "comfortable" ||
      data.density === "standard" ||
      data.density === "compact"
        ? data.density
        : DEFAULT_PREFERENCES.density,
    responseStyle:
      data.responseStyle === "concise" ||
      data.responseStyle === "balanced" ||
      data.responseStyle === "detailed"
        ? data.responseStyle
        : DEFAULT_PREFERENCES.responseStyle,
    citations: {
      ...DEFAULT_PREFERENCES.citations,
      ...(data.citations ?? {}),
    },
    knowledgeSources: {
      ...DEFAULT_PREFERENCES.knowledgeSources,
      ...(data.knowledgeSources ?? {}),
    },
    notifications: {
      ...DEFAULT_PREFERENCES.notifications,
      ...(data.notifications ?? {}),
    },
  };
}

export function loadPreferences(): UserPreferences {
  if (!isBrowser()) return { ...DEFAULT_PREFERENCES };
  try {
    const raw = localStorage.getItem(PREFERENCES_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES };
    return mergePreferences(JSON.parse(raw) as unknown);
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function savePreferences(prefs: UserPreferences): void {
  if (!isBrowser()) return;
  localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(prefs));
  applyAppearance(prefs);
}

export function updatePreferences(
  patch: Partial<UserPreferences>,
): UserPreferences {
  const next = mergePreferences({ ...loadPreferences(), ...patch });
  savePreferences(next);
  return next;
}

/** Apply theme + density to <html> for immediate visual feedback. */
export function applyAppearance(prefs: Pick<UserPreferences, "theme" | "density">): void {
  if (!isBrowser()) return;
  const root = document.documentElement;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark =
    prefs.theme === "dark" || (prefs.theme === "system" && prefersDark);
  root.classList.toggle("dark", dark);
  root.dataset.density = prefs.density;
  root.dataset.theme = prefs.theme;
}
