/**
 * =============================================================================
 * File: SettingsRow.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Preference row — label/description on the left, control on the right.
 * Responsibilities:
 *   - Consistent spacing for switches and inline controls
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - SettingsRow
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Avoid wrapping every row in a card.
 * =============================================================================
 */

import { cn } from "@/lib/utils";

type Props = {
  label: string;
  description?: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
};

export function SettingsRow({
  label,
  description,
  htmlFor,
  children,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-8",
        className,
      )}
    >
      <div className="min-w-0 max-w-xl">
        <label
          htmlFor={htmlFor}
          className="block text-body-sm font-medium text-primary"
        >
          {label}
        </label>
        {description ? (
          <p className="mt-0.5 text-caption text-tertiary">{description}</p>
        ) : null}
      </div>
      <div className="shrink-0 sm:flex sm:justify-end">{children}</div>
    </div>
  );
}
