/**
 * =============================================================================
 * File: SystemHealthCard.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: System Health card (Admin Dashboard §8) — dependency status list.
 * Responsibilities:
 *   - Prefer real GET /admin/health payload when provided
 *   - Fall back to API-derived row + Unknown for others when health unavailable
 * Dependencies:
 *   - lucide-react, features/admin/admin-health
 * Public Exports:
 *   - SystemHealthCard, type HealthStatus
 * Database/Table: N/A
 * Related Modules: features/admin/AdminDashboardView, AdminHealthView
 * Important Notes: Do not fake production health. Link to /admin/health.
 * =============================================================================
 */

"use client";

import { ArrowRight, Circle, HelpCircle, Triangle, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { HEALTH_STATUS_META } from "@/features/admin/admin-health";
import { AdminCard } from "@/features/admin/AdminCard";
import { cn } from "@/lib/utils";
import type { SystemHealth, SystemHealthStatus } from "@/types/admin";

/** @deprecated Prefer SystemHealthStatus from types/admin. */
export type HealthStatus = SystemHealthStatus | "down";

const LEGACY_META: Record<
  HealthStatus,
  { label: string; className: string; icon: LucideIcon }
> = {
  healthy: { label: "Healthy", className: "text-success", icon: Circle },
  degraded: { label: "Degraded", className: "text-warning", icon: Triangle },
  unhealthy: { label: "Unhealthy", className: "text-danger", icon: XCircle },
  down: { label: "Down", className: "text-danger", icon: XCircle },
  unknown: { label: "Unknown", className: "text-tertiary", icon: HelpCircle },
};

type Row = { key: string; label: string; status: HealthStatus; hint?: string };

type Props = {
  apiStatus: HealthStatus;
  health?: SystemHealth | null;
  healthLoading?: boolean;
};

function normalizeStatus(status: SystemHealthStatus): HealthStatus {
  return status;
}

export function SystemHealthCard({ apiStatus, health, healthLoading }: Props) {
  const rows: Row[] = health
    ? health.services.map((svc) => ({
        key: svc.id,
        label: svc.name,
        status: normalizeStatus(svc.status),
        hint: svc.message ?? undefined,
      }))
    : [
        {
          key: "api",
          label: "API",
          status: apiStatus,
          hint: "Derived from recent Admin API calls",
        },
        { key: "database", label: "Database", status: "unknown", hint: "Open /admin/health" },
        { key: "redis", label: "Redis", status: "unknown", hint: "Open /admin/health" },
        { key: "workers", label: "Workers", status: "unknown", hint: "Open /admin/health" },
        {
          key: "vector_store",
          label: "Vector Store",
          status: "unknown",
          hint: "Open /admin/health",
        },
        {
          key: "knowledge_graph",
          label: "Knowledge Graph",
          status: "unknown",
          hint: "Open /admin/health",
        },
        {
          key: "search_index",
          label: "Search Index",
          status: "unknown",
          hint: "Open /admin/health",
        },
        {
          key: "llm_provider",
          label: "LLM Provider",
          status: "unknown",
          hint: "Open /admin/health",
        },
      ];

  const overall = health
    ? HEALTH_STATUS_META[health.status]
    : HEALTH_STATUS_META[apiStatus === "down" ? "unhealthy" : (apiStatus as SystemHealthStatus)];

  return (
    <AdminCard
      headingId="admin-system-health"
      title="System Health"
      description="Availability of infrastructure dependencies."
      action={
        <Link
          href="/admin/health"
          className="inline-flex items-center gap-1 text-caption font-medium text-accent-primary hover:underline"
        >
          Open health
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
      }
    >
      {healthLoading && !health ? (
        <div className="flex flex-col gap-2" role="status" aria-label="Loading health">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-elevated" />
          ))}
        </div>
      ) : (
        <>
          {health ? (
            <p className={cn("mb-3 text-body-sm font-medium", overall.className)}>
              <span aria-hidden className="mr-1">
                {overall.marker}
              </span>
              {overall.label}
              {health.message ? (
                <span className="ml-2 font-normal text-tertiary">{health.message}</span>
              ) : null}
            </p>
          ) : null}
          <ul className="flex flex-col divide-y divide-border-default">
            {rows.map((row) => {
              const meta = LEGACY_META[row.status];
              const Icon = meta.icon;
              return (
                <li
                  key={row.key}
                  className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0"
                >
                  <span className="text-body-sm text-secondary">{row.label}</span>
                  <span
                    className={cn(
                      "flex items-center gap-1.5 text-body-sm font-medium",
                      meta.className,
                    )}
                    title={row.hint}
                  >
                    <Icon
                      className={cn(
                        "h-2.5 w-2.5",
                        row.status === "healthy" && "fill-current",
                      )}
                      aria-hidden
                    />
                    {meta.label}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </AdminCard>
  );
}
