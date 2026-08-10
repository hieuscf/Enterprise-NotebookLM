/**
 * =============================================================================
 * File: AdminHealthChecksTable.tsx
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: Compact “last checked” table from the current SystemHealth payload.
 * Responsibilities:
 *   - List each service status + relative checked time (no fake history)
 * Dependencies:
 *   - features/admin/admin-health, AdminCard
 * Public Exports:
 *   - AdminHealthChecksTable
 * Database/Table: N/A
 * Related Modules: AdminHealthView
 * Important Notes: Not a historical log — only the latest probe per service.
 * =============================================================================
 */

"use client";

import {
  formatRelativeAgo,
  HEALTH_STATUS_META,
} from "@/features/admin/admin-health";
import { AdminCard } from "@/features/admin/AdminCard";
import { cn } from "@/lib/utils";
import type { HealthService } from "@/types/admin";

type Props = {
  services: HealthService[];
  loading: boolean;
  nowTick: number;
  onOpen: (service: HealthService) => void;
};

export function AdminHealthChecksTable({
  services,
  loading,
  nowTick,
  onOpen,
}: Props) {
  return (
    <AdminCard
      headingId="health-recent-checks-heading"
      title="Recent Health Checks"
      description="Latest probe result per dependency from the current health response."
    >
      {loading && services.length === 0 ? (
        <div className="flex flex-col gap-2" role="status" aria-label="Loading checks">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-elevated" />
          ))}
        </div>
      ) : services.length === 0 ? (
        <p className="text-body-sm text-tertiary">No health checks available.</p>
      ) : (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                <th className="px-2 py-2 font-medium">Service</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 text-right font-medium">Last Check</th>
              </tr>
            </thead>
            <tbody>
              {services.map((svc) => {
                const meta = HEALTH_STATUS_META[svc.status];
                return (
                  <tr
                    key={svc.id}
                    className="cursor-pointer border-b border-border-default last:border-0 hover:bg-elevated/40"
                    onClick={() => onOpen(svc)}
                  >
                    <td className="px-2 py-2.5 font-medium text-primary">{svc.name}</td>
                    <td className="px-2 py-2.5">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-semibold",
                          meta.badgeClass,
                        )}
                      >
                        <span aria-hidden>{meta.marker}</span>
                        {meta.label}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-tertiary">
                      {formatRelativeAgo(svc.checked_at, new Date(nowTick))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </AdminCard>
  );
}
