/**
 * =============================================================================
 * File: AdminUsageKpis.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: KPI strip for `/admin/usage` — cost, calls, tokens, period.
 * Responsibilities:
 *   - Render Total Cost / LLM Calls / Avg Cost per Call / Selected Period
 *   - Render Input / Output / Total token aggregates from CostSummary
 * Dependencies:
 *   - features/admin/admin-usage
 * Public Exports:
 *   - AdminUsageKpis
 * Database/Table: message_generations (via CostSummary)
 * Related Modules: AdminUsageView
 * Important Notes: Token totals come from CostSummary API — never invent.
 * =============================================================================
 */

"use client";

import {
  costPerCall,
  formatCostExact,
  formatCostUsd,
  formatCount,
  formatPeriodShort,
} from "@/features/admin/admin-usage";
import type { CostSummary } from "@/types/admin";

type Props = {
  summary: CostSummary | null;
  from: string;
  to: string;
  periodLabel: string;
  loading: boolean;
};

function StatCard({
  label,
  value,
  hint,
  loading,
  title,
}: {
  label: string;
  value: string;
  hint: string;
  loading: boolean;
  title?: string;
}) {
  return (
    <div
      className="flex flex-col gap-1 rounded-lg border border-border-default bg-surface px-4 py-3 text-left"
      title={title}
    >
      <p className="text-caption font-semibold uppercase tracking-wider text-tertiary">
        {label}
      </p>
      {loading ? (
        <div className="h-7 w-20 animate-pulse rounded bg-elevated" />
      ) : (
        <p className="font-mono text-h2 font-semibold text-primary">{value}</p>
      )}
      <p className="text-caption text-tertiary">{hint}</p>
    </div>
  );
}

function tokenValue(
  summary: CostSummary | null,
  key: "total_prompt_tokens" | "total_completion_tokens" | "total_tokens",
): string {
  if (!summary) return "—";
  const raw = summary[key];
  if (typeof raw !== "number" || !Number.isFinite(raw)) return "—";
  return formatCount(raw);
}

export function AdminUsageKpis({ summary, from, to, periodLabel, loading }: Props) {
  const avg =
    summary && summary.total_llm_calls > 0
      ? costPerCall(summary.total_cost_usd, summary.total_llm_calls)
      : null;

  return (
    <section aria-labelledby="usage-kpi-heading" className="flex flex-col gap-3">
      <h2 id="usage-kpi-heading" className="sr-only">
        Usage overview
      </h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Total Cost"
          value={summary ? formatCostUsd(summary.total_cost_usd) : "—"}
          hint="total_cost_usd"
          loading={loading}
          title={summary ? formatCostExact(summary.total_cost_usd) : undefined}
        />
        <StatCard
          label="LLM Calls"
          value={summary ? formatCount(summary.total_llm_calls) : "—"}
          hint="total_llm_calls"
          loading={loading}
        />
        <StatCard
          label="Avg Cost / Call"
          value={avg === null ? "—" : formatCostUsd(avg)}
          hint="total_cost ÷ LLM calls"
          loading={loading}
          title={avg === null ? undefined : formatCostExact(avg)}
        />
        <StatCard
          label="Selected Period"
          value={formatPeriodShort(from, to)}
          hint={periodLabel}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          label="Input Tokens"
          value={tokenValue(summary, "total_prompt_tokens")}
          hint="sum(prompt_tokens)"
          loading={loading}
        />
        <StatCard
          label="Output Tokens"
          value={tokenValue(summary, "total_completion_tokens")}
          hint="sum(completion_tokens)"
          loading={loading}
        />
        <StatCard
          label="Total Tokens"
          value={tokenValue(summary, "total_tokens")}
          hint="sum(total_tokens)"
          loading={loading}
        />
      </div>
    </section>
  );
}
