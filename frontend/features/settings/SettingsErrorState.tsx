/**
 * =============================================================================
 * File: SettingsErrorState.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Inline error banner for Settings save/load failures.
 * Responsibilities:
 *   - Surface recoverable errors without wiping the page
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - SettingsErrorState
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Prefer keeping existing form values when this appears.
 * =============================================================================
 */

import { AlertCircle } from "lucide-react";

type Props = {
  message: string;
  onRetry?: () => void;
};

export function SettingsErrorState({ message, onRetry }: Props) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex min-w-0 flex-col gap-2">
        <span>{message}</span>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="w-fit text-body-sm font-medium underline"
          >
            Thử lại
          </button>
        ) : null}
      </div>
    </div>
  );
}
