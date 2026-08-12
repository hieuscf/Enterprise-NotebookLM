/**
 * =============================================================================
 * File: SettingsDangerZone.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Restrained destructive action block for Workspace settings.
 * Responsibilities:
 *   - Present danger copy + action without a large red card
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - SettingsDangerZone
 * Database/Table: N/A
 * Related Modules: features/settings/pages/WorkspaceSettings.tsx
 * Important Notes: Uses danger text token; confirmation is the caller's job.
 * =============================================================================
 */

import { cn } from "@/lib/utils";

type Props = {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  disabled?: boolean;
};

export function SettingsDangerZone({
  title,
  description,
  actionLabel,
  onAction,
  disabled = false,
}: Props) {
  return (
    <div className="flex flex-col gap-4 rounded-md border border-danger/25 px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="min-w-0 max-w-xl">
        <h3 className="text-body-sm font-semibold text-danger">{title}</h3>
        <p className="mt-1 text-body-sm text-secondary">{description}</p>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={onAction}
        className={cn(
          "h-10 shrink-0 rounded-md border border-danger/40 bg-surface px-4",
          "text-body-sm font-medium text-danger",
          "hover:bg-danger-soft disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        {actionLabel}
      </button>
    </div>
  );
}
