/**
 * =============================================================================
 * File: AdminHealthOverall.tsx
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: Overall system status banner for `/admin/health`.
 * Responsibilities:
 *   - Render authoritative overall status from SystemHealth
 *   - Show last-checked relative time
 * Dependencies:
 *   - features/admin/admin-health
 * Public Exports:
 *   - AdminHealthOverall
 * Database/Table: N/A
 * Related Modules: AdminHealthView
 * Important Notes: Unknown ≠ Healthy. Prefer backend message.
 * =============================================================================
 */

"use client";

import {
  formatRelativeAgo,
  HEALTH_STATUS_META,
  overallHealthDescription,
} from "@/features/admin/admin-health";
import { cn } from "@/lib/utils";
import type { SystemHealth } from "@/types/admin";

type Props = {
  health: SystemHealth | null;
  loading: boolean;
  nowTick: number;
};

export function AdminHealthOverall({ health, loading, nowTick }: Props) {
  const status = health?.status ?? "unknown";
  const meta = HEALTH_STATUS_META[status];
  const description = overallHealthDescription(health);
  const checkedLabel = health?.checked_at
    ? formatRelativeAgo(health.checked_at, new Date(nowTick))
    : "—";

  return (
    <section
      aria-labelledby="system-health-overall-heading"
      className="rounded-lg border border-border-default bg-surface px-5 py-5"
    >
      <h2
        id="system-health-overall-heading"
        className="text-caption font-semibold uppercase tracking-wider text-tertiary"
      >
        System Status
      </h2>

      {loading && !health ? (
        <div className="mt-3 space-y-2" role="status" aria-label="Loading system status">
          <div className="h-8 w-40 animate-pulse rounded bg-elevated" />
          <div className="h-4 w-80 max-w-full animate-pulse rounded bg-elevated" />
        </div>
      ) : (
        <div className="mt-3">
          <p
            className={cn("flex items-center gap-2 text-h2 font-semibold", meta.className)}
            aria-label={`System status: ${meta.label}`}
          >
            <span aria-hidden className="text-h1 leading-none">
              {meta.marker}
            </span>
            {meta.label === "Healthy" ? "Operational" : meta.label}
          </p>
          <p className="mt-2 max-w-2xl text-body-sm text-secondary">{description}</p>
          <p className="mt-3 text-caption text-tertiary" aria-live="polite">
            Last checked {checkedLabel}
          </p>
        </div>
      )}
    </section>
  );
}
