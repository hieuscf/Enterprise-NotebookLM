/**
 * =============================================================================
 * File: SettingsField.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Labeled form field wrapper for Settings forms.
 * Responsibilities:
 *   - Associate label, hint, error, and control with accessible ids
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - SettingsField, settingsInputClass
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Matches existing hand-rolled input styling in the app.
 * =============================================================================
 */

import { useId } from "react";

import { cn } from "@/lib/utils";

export const settingsInputClass = cn(
  "h-11 w-full rounded-md border border-border-default bg-surface px-3",
  "text-body text-primary placeholder:text-tertiary",
  "outline-none transition-colors",
  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
  "disabled:cursor-not-allowed disabled:bg-elevated/60 disabled:text-secondary",
  "read-only:bg-elevated/40 read-only:text-secondary",
);

type Props = {
  label: string;
  description?: string;
  error?: string | null;
  required?: boolean;
  htmlFor?: string;
  children: React.ReactNode | ((id: string) => React.ReactNode);
  className?: string;
};

export function SettingsField({
  label,
  description,
  error,
  required,
  htmlFor,
  children,
  className,
}: Props) {
  const autoId = useId();
  const id = htmlFor ?? autoId;

  return (
    <div className={cn("flex max-w-xl flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-body-sm font-medium text-primary">
        {label}
        {required ? <span className="text-danger"> *</span> : null}
      </label>
      {typeof children === "function" ? children(id) : children}
      {description && !error ? (
        <p className="text-caption text-tertiary">{description}</p>
      ) : null}
      {error ? (
        <p role="alert" className="text-caption text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
