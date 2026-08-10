/**
 * =============================================================================
 * File: AdminHealthServiceCard.tsx
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: Single dependency health card (read-only).
 * Responsibilities:
 *   - Show status marker + label + message + last checked
 *   - Open detail drawer on activate
 * Dependencies:
 *   - features/admin/admin-health
 * Public Exports:
 *   - AdminHealthServiceCard
 * Database/Table: N/A
 * Related Modules: AdminHealthServiceGrid, AdminHealthDrawer
 * Important Notes: Never show secrets. Status is not color-only.
 * =============================================================================
 */

"use client";

import {
  displayProvider,
  formatRelativeAgo,
  HEALTH_STATUS_META,
} from "@/features/admin/admin-health";
import { cn } from "@/lib/utils";
import type { HealthService } from "@/types/admin";

type Props = {
  service: HealthService;
  nowTick: number;
  onOpen: (service: HealthService) => void;
};

export function AdminHealthServiceCard({ service, nowTick, onOpen }: Props) {
  const meta = HEALTH_STATUS_META[service.status];
  const provider = displayProvider(service);
  const checked = formatRelativeAgo(service.checked_at, new Date(nowTick));

  return (
    <button
      type="button"
      onClick={() => onOpen(service)}
      aria-label={`${service.name} status: ${meta.label}`}
      className={cn(
        "flex w-full flex-col gap-2 rounded-lg border border-border-default bg-surface px-4 py-3 text-left",
        "transition-colors hover:bg-elevated/50",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-body-sm font-semibold text-primary">
            <span className={cn("mr-1.5", meta.className)} aria-hidden>
              {meta.marker}
            </span>
            {service.name}
          </p>
          {provider ? (
            <p className="mt-0.5 font-mono text-caption text-tertiary">{provider}</p>
          ) : null}
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold",
            meta.badgeClass,
          )}
        >
          {meta.label}
        </span>
      </div>
      <p className="line-clamp-2 text-caption text-secondary">
        {service.message?.trim() || "No status message"}
      </p>
      <div className="flex flex-wrap items-center gap-x-3 font-mono text-caption text-tertiary">
        <span>Last checked {checked}</span>
        {service.response_time_ms != null ? (
          <span title="Health-check probe latency (not an SLA)">
            {service.response_time_ms} ms
          </span>
        ) : null}
        {service.critical ? <span>Critical</span> : null}
      </div>
    </button>
  );
}
