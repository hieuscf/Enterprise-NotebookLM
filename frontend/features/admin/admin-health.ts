/**
 * =============================================================================
 * File: admin-health.ts
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: Pure helpers for `/admin/health` — labels, icons, grouping.
 * Responsibilities:
 *   - Map HealthStatus → label / marker / description classes
 *   - Split services into core vs AI & retrieval
 * Dependencies:
 *   - types/admin SystemHealth*
 * Public Exports:
 *   - HEALTH_STATUS_META, groupHealthServices, formatHealthCheckedAt
 * Database/Table: N/A
 * Related Modules: features/admin/AdminHealth*
 * Important Notes: Overall status comes from backend — do not recompute on FE
 *   except for display grouping. Never invent health when API fails.
 * =============================================================================
 */

import { formatFullTs, formatRelativeAgo } from "@/features/admin/admin-pipeline";
import type {
  HealthService,
  SystemHealth,
  SystemHealthStatus,
} from "@/types/admin";

export { formatFullTs, formatRelativeAgo };

export const HEALTH_STATUS_META: Record<
  SystemHealthStatus,
  {
    label: string;
    marker: string;
    className: string;
    badgeClass: string;
    description: string;
  }
> = {
  healthy: {
    label: "Healthy",
    marker: "●",
    className: "text-success",
    badgeClass: "bg-success/10 text-success",
    description: "All monitored dependencies are responding normally.",
  },
  degraded: {
    label: "Degraded",
    marker: "△",
    className: "text-warning",
    badgeClass: "bg-warning/10 text-warning",
    description:
      "Most services are operational, but some dependencies are experiencing reduced availability.",
  },
  unhealthy: {
    label: "Unhealthy",
    marker: "×",
    className: "text-danger",
    badgeClass: "bg-danger-soft text-danger",
    description: "One or more critical dependencies are unavailable.",
  },
  unknown: {
    label: "Unknown",
    marker: "?",
    className: "text-tertiary",
    badgeClass: "bg-elevated text-tertiary",
    description: "Health information is currently unavailable.",
  },
};

/** Prefer backend overall message; fall back to status meta description. */
export function overallHealthDescription(health: SystemHealth | null): string {
  if (!health) return HEALTH_STATUS_META.unknown.description;
  if (health.message?.trim()) return health.message.trim();
  return HEALTH_STATUS_META[health.status].description;
}

export function groupHealthServices(services: HealthService[]): {
  core: HealthService[];
  ai: HealthService[];
} {
  return {
    core: services.filter((s) => s.category === "core"),
    ai: services.filter((s) => s.category === "ai_retrieval"),
  };
}

export function displayProvider(service: HealthService): string | null {
  const p = service.provider?.trim();
  if (!p) return null;
  return p;
}
