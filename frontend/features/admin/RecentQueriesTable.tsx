/**
 * =============================================================================
 * File: RecentQueriesTable.tsx
 * Module/Service: Query Router / Observability (Web App)
 * Layer: UI
 * Purpose: Recent Query Activity table (Admin Dashboard §12) — compact audit
 *          view over the latest query_logs rows for the selected workspace.
 * Responsibilities:
 *   - Render Time / Route / LLM calls / Model / Latency columns
 *   - Truncate query_text — never render the full raw query on a dashboard
 *     that many admins can see, per the privacy note in the task brief
 * Dependencies:
 *   - features/admin/admin-format, features/admin/AdminSectionState
 * Public Exports:
 *   - RecentQueriesTable
 * Database/Table: query_logs
 * Related Modules: features/admin/AdminDashboardView, hooks/useAdminQueryLogs
 * Important Notes: No workspace column — the whole dashboard is already
 *   scoped to one workspace at a time (RBAC is per-workspace, not global).
 * =============================================================================
 */

"use client";

import { AdminCard } from "@/features/admin/AdminCard";
import {
  formatLatency,
  formatTimeShort,
  ROUTE_BADGE_CLASS,
  ROUTE_LABEL_VI,
} from "@/features/admin/admin-format";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import { cn } from "@/lib/utils";
import type { QueryLogItem } from "@/types/admin";

type Props = {
  items: QueryLogItem[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  headingId?: string;
};

function redactQueryText(text: string, max = 44): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max)}…`;
}

export function RecentQueriesTable({ items, loading, error, onRetry, headingId = "admin-recent-queries" }: Props) {
  return (
    <AdminCard
      headingId={headingId}
      title="Recent Query Activity"
      description="Các truy vấn gần nhất và cách Query Router định tuyến."
    >
      {loading ? (
        <SectionSkeleton rows={5} />
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : items.length === 0 ? (
        <SectionEmpty
          title="Chưa có hoạt động truy vấn nào."
          description="Dữ liệu định tuyến truy vấn sẽ xuất hiện tại đây khi người dùng bắt đầu tương tác với AI assistant."
        />
      ) : (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                <th className="px-1 py-2 font-medium">Time</th>
                <th className="px-1 py-2 font-medium">Query</th>
                <th className="px-1 py-2 font-medium">Route</th>
                <th className="px-1 py-2 text-right font-medium">LLM</th>
                <th className="px-1 py-2 text-right font-medium">Latency</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id} className="border-b border-border-default last:border-0">
                  <td className="whitespace-nowrap px-1 py-2 text-tertiary">
                    {formatTimeShort(row.created_at)}
                  </td>
                  <td className="max-w-[240px] truncate px-1 py-2 text-secondary">
                    {redactQueryText(row.query_text)}
                  </td>
                  <td className="px-1 py-2">
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-caption font-semibold",
                        ROUTE_BADGE_CLASS[row.route_type],
                      )}
                    >
                      {ROUTE_LABEL_VI[row.route_type]}
                    </span>
                  </td>
                  <td className="px-1 py-2 text-right text-primary">{row.llm_calls_count}</td>
                  <td className="whitespace-nowrap px-1 py-2 text-right text-primary">
                    {formatLatency(row.latency_ms)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AdminCard>
  );
}
