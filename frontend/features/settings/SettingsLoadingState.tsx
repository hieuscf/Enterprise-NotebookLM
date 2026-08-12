/**
 * =============================================================================
 * File: SettingsLoadingState.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Inline loading placeholder for Settings content panes.
 * Responsibilities:
 *   - Show a calm loading row without full-page takeover
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - SettingsLoadingState
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Keep form values intact when reloading around this state.
 * =============================================================================
 */

import { Loader2 } from "lucide-react";

type Props = {
  message?: string;
};

export function SettingsLoadingState({
  message = "Đang tải cài đặt…",
}: Props) {
  return (
    <div className="flex items-center gap-2 py-10 text-body-sm text-tertiary">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {message}
    </div>
  );
}
