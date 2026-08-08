/**
 * =============================================================================
 * File: SystemHealthCard.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: System Health card (Admin Dashboard §8) — dependency status list.
 * Responsibilities:
 *   - "API" row reflects real signal: whether the dashboard's own admin calls
 *     are currently succeeding (derived, not fabricated)
 *   - All other dependencies (Database, Redis, Workers, Vector Store,
 *     Knowledge Graph, Search Index, LLM Provider) render "Unknown" — no
 *     per-dependency health endpoint exists in the OpenAPI contract yet
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - SystemHealthCard, type HealthStatus
 * Database/Table: N/A
 * Related Modules: features/admin/AdminDashboardView
 * Important Notes: TODO(backend) — add GET /admin/health (or per-service
 *   probes) so this card can report real Degraded/Down states instead of
 *   Unknown. Do not fake production health here.
 * =============================================================================
 */

import { Circle, HelpCircle, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { AdminCard } from "@/features/admin/AdminCard";
import { cn } from "@/lib/utils";

export type HealthStatus = "healthy" | "degraded" | "down" | "unknown";

const STATUS_META: Record<HealthStatus, { label: string; className: string; icon: LucideIcon }> = {
  healthy: { label: "Healthy", className: "text-success", icon: Circle },
  degraded: { label: "Degraded", className: "text-warning", icon: Circle },
  down: { label: "Down", className: "text-danger", icon: XCircle },
  unknown: { label: "Unknown", className: "text-tertiary", icon: HelpCircle },
};

type Row = { key: string; label: string; status: HealthStatus; hint?: string };

type Props = {
  apiStatus: HealthStatus;
};

export function SystemHealthCard({ apiStatus }: Props) {
  const rows: Row[] = [
    { key: "api", label: "API", status: apiStatus, hint: "Suy ra từ kết quả gọi API Admin gần nhất" },
    { key: "database", label: "Database", status: "unknown", hint: "Chưa có health endpoint" },
    { key: "redis", label: "Redis", status: "unknown", hint: "Chưa có health endpoint" },
    { key: "workers", label: "Workers", status: "unknown", hint: "Chưa có health endpoint" },
    { key: "vector_store", label: "Vector Store", status: "unknown", hint: "Chưa có health endpoint" },
    { key: "knowledge_graph", label: "Knowledge Graph", status: "unknown", hint: "Chưa có health endpoint" },
    { key: "search_index", label: "Search Index", status: "unknown", hint: "Chưa có health endpoint" },
    { key: "llm_provider", label: "LLM Provider", status: "unknown", hint: "Chưa có health endpoint" },
  ];

  return (
    <AdminCard
      headingId="admin-system-health"
      title="System Health"
      description="Trạng thái các thành phần hạ tầng phụ thuộc."
    >
      <ul className="flex flex-col divide-y divide-border-default">
        {rows.map((row) => {
          const meta = STATUS_META[row.status];
          const Icon = meta.icon;
          return (
            <li key={row.key} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
              <span className="text-body-sm text-secondary">{row.label}</span>
              <span
                className={cn("flex items-center gap-1.5 text-body-sm font-medium", meta.className)}
                title={row.hint}
              >
                <Icon className={cn("h-2.5 w-2.5", row.status !== "unknown" && "fill-current")} aria-hidden />
                {meta.label}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-caption text-tertiary">
        Trạng thái “Unknown” nghĩa là hệ thống chưa có health-check endpoint cho thành phần này (TODO backend).
      </p>
    </AdminCard>
  );
}
