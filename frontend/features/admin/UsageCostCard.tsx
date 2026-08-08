/**
 * =============================================================================
 * File: UsageCostCard.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Usage & Cost card (Admin Dashboard §10) — LLM spend for the
 *          selected period, broken down by model and by route type.
 * Responsibilities:
 *   - Reflects the page-level date range (7/30/90 days, controlled by
 *     AdminDashboardView so every cost-driven card stays in sync)
 *   - Minimal horizontal-bar chart of cost by model (CostSummary.by_model)
 *   - Compact route-type count breakdown (CostSummary.by_route_type)
 *   - Summary numbers: Total Cost, LLM Calls, Avg Cost/Query
 * Dependencies:
 *   - features/admin/admin-format, features/admin/AdminSectionState
 * Public Exports:
 *   - UsageCostCard
 * Database/Table: message_generations (via cost-summary aggregate)
 * Related Modules: features/admin/AdminDashboardView, hooks/useAdminCostSummary
 * Important Notes: The cost-summary contract returns ONE aggregate per
 *   from/to window (no daily buckets) and no token counts — do not fabricate
 *   a time-series line chart or Input/Output Token numbers; both are shown as
 *   "unavailable" rather than invented. No workspace-breakdown UI either,
 *   since the endpoint is already scoped to a single workspace.
 * =============================================================================
 */

"use client";

import type { CostRangeDays } from "@/hooks/useAdminCostSummary";
import { AdminCard } from "@/features/admin/AdminCard";
import { formatCompactNumber, formatCurrencyUsd, formatPercent } from "@/features/admin/admin-format";
import { SectionEmpty, SectionError, SectionSkeleton } from "@/features/admin/AdminSectionState";
import type { CostSummary } from "@/types/admin";

type Props = {
  cost: CostSummary | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  rangeDays: CostRangeDays;
};

export function UsageCostCard({ cost, loading, error, onRetry, rangeDays }: Props) {
  const totalQueries = (cost?.by_route_type ?? []).reduce((sum, r) => sum + r.count, 0);
  const avgCostPerQuery =
    cost && totalQueries > 0 ? cost.total_cost_usd / totalQueries : null;
  const byModel = [...(cost?.by_model ?? [])].sort((a, b) => b.cost_usd - a.cost_usd);
  const maxModelCost = byModel.reduce((max, m) => Math.max(max, m.cost_usd), 0);

  return (
    <AdminCard
      headingId="admin-usage-cost"
      title="Usage & Cost"
      description={`Chi phí LLM theo mô hình và loại định tuyến — ${rangeDays} ngày gần nhất.`}
    >
      {loading ? (
        <SectionSkeleton rows={5} />
      ) : error ? (
        <SectionError message={error} onRetry={onRetry} />
      ) : !cost || (cost.total_llm_calls === 0 && byModel.length === 0) ? (
        <SectionEmpty
          title="Chưa có dữ liệu chi phí trong kỳ này."
          description="Chi phí LLM sẽ xuất hiện sau khi nhánh Complex Query của Query Router thực hiện lệnh gọi LLM đầu tiên."
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-caption text-tertiary">Total Cost</p>
              <p className="text-h3 font-semibold text-primary">
                {formatCurrencyUsd(cost.total_cost_usd)}
              </p>
            </div>
            <div>
              <p className="text-caption text-tertiary">LLM Calls</p>
              <p className="text-h3 font-semibold text-primary">
                {formatCompactNumber(cost.total_llm_calls)}
              </p>
            </div>
            <div>
              <p className="text-caption text-tertiary">Avg Cost / Query</p>
              <p className="text-h3 font-semibold text-primary">
                {avgCostPerQuery === null ? "—" : formatCurrencyUsd(avgCostPerQuery)}
              </p>
            </div>
            <div title="API chưa cung cấp tổng token — cần bổ sung ở backend (TODO)">
              <p className="text-caption text-tertiary">Input / Output Tokens</p>
              <p className="text-h3 font-semibold text-tertiary">Chưa khả dụng</p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
            <div>
              <p className="mb-2 text-caption font-semibold uppercase tracking-wide text-tertiary">
                Theo Model
              </p>
              {byModel.length === 0 ? (
                <p className="text-body-sm text-tertiary">Không có dữ liệu theo model.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {byModel.map((m) => (
                    <li key={m.model_used} className="flex items-center gap-3">
                      <span className="w-28 shrink-0 truncate text-body-sm text-secondary" title={m.model_used}>
                        {m.model_used}
                      </span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-elevated">
                        <div
                          className="h-full rounded-full bg-accent-primary"
                          style={{
                            width: `${maxModelCost > 0 ? Math.max((m.cost_usd / maxModelCost) * 100, 2) : 0}%`,
                          }}
                        />
                      </div>
                      <span className="w-28 shrink-0 text-right text-body-sm font-medium text-primary">
                        {formatCurrencyUsd(m.cost_usd)}
                        <span className="ml-1 font-normal text-tertiary">
                          ({formatCompactNumber(m.calls)})
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="mb-2 text-caption font-semibold uppercase tracking-wide text-tertiary">
                Theo Route Type
              </p>
              {(cost.by_route_type ?? []).length === 0 ? (
                <p className="text-body-sm text-tertiary">Không có dữ liệu theo route type.</p>
              ) : (
                <ul className="divide-y divide-border-default rounded-md border border-border-default">
                  {cost.by_route_type.map((r) => (
                    <li key={r.route_type} className="flex items-center justify-between px-3 py-1.5 text-body-sm">
                      <span className="capitalize text-secondary">{r.route_type.replace("_", " ")}</span>
                      <span className="font-medium text-primary">
                        {formatCompactNumber(r.count)}
                        {totalQueries > 0 ? (
                          <span className="ml-1 font-normal text-tertiary">
                            ({formatPercent(r.count / totalQueries)})
                          </span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </AdminCard>
  );
}
