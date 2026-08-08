/**
 * =============================================================================
 * File: AdminCard.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Consistent card container for Admin Dashboard sections — reuses the
 *          same border/radius/padding tokens as existing feature cards
 *          (see features/comparisons/ComparisonsView.tsx section pattern).
 * Responsibilities:
 *   - Render title + optional description/action header + body slot
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - AdminCard
 * Database/Table: N/A
 * Related Modules: features/admin/*Card.tsx
 * Important Notes: Does not introduce new radius/shadow/border tokens.
 * =============================================================================
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Props = {
  title: string;
  description?: string;
  action?: ReactNode;
  headingId: string;
  className?: string;
  children: ReactNode;
};

export function AdminCard({
  title,
  description,
  action,
  headingId,
  className,
  children,
}: Props) {
  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4 sm:p-5",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id={headingId} className="text-h3 text-primary">
            {title}
          </h2>
          {description ? (
            <p className="mt-0.5 text-caption text-tertiary">{description}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}
