/**
 * =============================================================================
 * File: SettingsSwitch.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Accessible toggle switch for preference rows.
 * Responsibilities:
 *   - Keyboard-accessible on/off control with visible focus
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - SettingsSwitch
 * Database/Table: N/A
 * Related Modules: features/settings/SettingsRow.tsx
 * Important Notes: Hand-rolled to match ConfirmDialog/Toast (no Radix Switch).
 * =============================================================================
 */

"use client";

import { cn } from "@/lib/utils";

type Props = {
  id?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
};

export function SettingsSwitch({
  id,
  checked,
  onCheckedChange,
  disabled = false,
  label,
}: Props) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-accent-primary" : "bg-border-strong",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-xs transition-transform",
          checked && "translate-x-5",
        )}
      />
    </button>
  );
}
