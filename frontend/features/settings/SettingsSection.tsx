/**
 * =============================================================================
 * File: SettingsSection.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Grouped settings block with title + optional description.
 * Responsibilities:
 *   - Provide vertical rhythm without heavy card chrome
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - SettingsSection
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Prefer separator over nested colored cards.
 * =============================================================================
 */

import { cn } from "@/lib/utils";

type Props = {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  /** Soft warning strip for danger-adjacent sections. */
  tone?: "default" | "danger";
};

export function SettingsSection({
  title,
  description,
  children,
  className,
  tone = "default",
}: Props) {
  return (
    <section
      className={cn(
        "flex flex-col gap-4 border-b border-border-default py-8 last:border-b-0",
        tone === "danger" && "border-danger/20",
        className,
      )}
    >
      <div className="max-w-2xl">
        <h2
          className={cn(
            "text-h3 text-primary",
            tone === "danger" && "text-danger",
          )}
        >
          {title}
        </h2>
        {description ? (
          <p className="mt-1 text-body-sm text-secondary">{description}</p>
        ) : null}
      </div>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}
