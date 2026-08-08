/**
 * =============================================================================
 * File: QueryRoutingCard.tsx
 * Module/Service: Query Router (Web App)
 * Layer: UI
 * Purpose: Query Routing Analytics card (Admin Dashboard §9) — visualizes how
 *          the 4-branch Query Router is distributing traffic, and how much
 *          LLM spend it is avoiding by design (FR11).
 * Responsibilities:
 *   - Compact horizontal-bar distribution over {cache_hit, metadata, factoid,
 *     complex} derived from CostSummary.by_route_type (real aggregate, not a
 *     client-side guess)
 *   - LLM Avoidance Rate / LLM Calls per Query / Complex Query Rate, derived
 *     from total_llm_calls vs total query count in the same aggregate
 * Dependencies:
 *   - features/admin/admin-format, features/admin/AdminSectionState
 * Public Exports:
 *   - QueryRoutingCard
 * Database/Table: message_generations, query_logs (via cost-summary aggregate)
 * Related Modules: features/admin/AdminDashboardView, RecentQueriesTable
 * Important Notes: "complex → tối đa 1 LLM call" per FR11 — avoidance rate is
 *   therefore exactly (1 - total_llm_calls / total_queries), not an estimate.
 * =============================================================================
 */

"use client";

import { ArrowRight } from "lucide-react";

import { AdminCard } from "@/features/admin/AdminCard";
import {
  formatCompactNumber,
  formatPercent,
  ROUTE_DOT_CLASS,
  ROUTE_LABEL_VI,
  ROUTE_ORDER,
} from "@/features/admin/admin-format";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import type { CostSummary } from "@/types/admin";
import type { RouteType } from "@/types/chat";

type Props = {
  cost: CostSummary | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onViewQueryLogs: () => void;
};

export function QueryRoutingCard({ cost, loading, error, onRetry, onViewQueryLogs }: Props) {
  const counts: Record<RouteType, number> = {
    cache_hit: 0,
    metadata: 0,
    factoid: 0,
    complex: 0,
  };
  for (const item of cost?.by_route_type ?? []) {
    if (item.route_type in counts) counts[item.route_type as RouteType] += item.count;
  }
  const total = ROUTE_ORDER.reduce((sum, r) => sum + counts[r], 0);
  const totalLlmCalls = cost?.total_llm_calls ?? 0;

  const avoidanceRate = total > 0 ? 1 - totalLlmCalls / total : null;
  const llmCallsPerQuery = total > 0 ? totalLlmCalls / total : null;
  const complexRate = total > 0 ? counts.complex / total : null;

  return (
    <AdminCard
      headingId="admin-query-routing"
      title="Query Routing"
      description="Phân bổ 4 nhánh của Query Router trong kỳ đã chọn."
      action={
        <button
          type="button"
          onClick={onViewQueryLogs}
          className="inline-flex items-center gap-1 text-caption font-medium text-accent-primary hover:underline"
        >
          Xem nhật ký truy vấn
          <ArrowRight className="h-3 w-3" aria-hidden />
        </button>
      }
    >
      {loading ? (
        <SectionSkeleton rows={4} />
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : total === 0 ? (
        <SectionEmpty
          title="Chưa có dữ liệu định tuyến truy vấn."
          description="Dữ liệu sẽ xuất hiện sau khi người dùng bắt đầu trò chuyện với AI trong kỳ này."
        />
      ) : (
        <>
          <ul className="flex flex-col gap-2.5">
            {ROUTE_ORDER.map((route) => {
              const count = counts[route];
              const ratio = total > 0 ? count / total : 0;
              return (
                <li key={route} className="flex items-center gap-3">
                  <span className="w-20 shrink-0 text-body-sm text-secondary">
                    {ROUTE_LABEL_VI[route]}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-elevated">
                    <div
                      className={`h-full rounded-full ${ROUTE_DOT_CLASS[route]}`}
                      style={{ width: `${Math.max(ratio * 100, count > 0 ? 2 : 0)}%` }}
                    />
                  </div>
                  <span className="w-24 shrink-0 text-right text-body-sm font-medium text-primary">
                    {formatPercent(ratio)}
                    <span className="ml-1 font-normal text-tertiary">
                      ({formatCompactNumber(count)})
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>

          <div className="grid grid-cols-3 gap-3 border-t border-border-default pt-3">
            <div>
              <p className="text-caption text-tertiary">LLM Avoidance Rate</p>
              <p className="text-h3 font-semibold text-primary">
                {avoidanceRate === null ? "—" : formatPercent(avoidanceRate, 1)}
              </p>
            </div>
            <div>
              <p className="text-caption text-tertiary">LLM Calls / Query</p>
              <p className="text-h3 font-semibold text-primary">
                {llmCallsPerQuery === null ? "—" : llmCallsPerQuery.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-caption text-tertiary">Complex Query Rate</p>
              <p className="text-h3 font-semibold text-primary">
                {complexRate === null ? "—" : formatPercent(complexRate, 1)}
              </p>
            </div>
          </div>
        </>
      )}
    </AdminCard>
  );
}
