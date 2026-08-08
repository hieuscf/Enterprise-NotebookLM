/**
 * =============================================================================
 * File: AdminKpiCards.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Compact KPI row — Workspaces, Users, Documents, Queries, LLM Calls,
 *          Estimated Cost (Admin Dashboard §7).
 * Responsibilities:
 *   - Render one MetricCard per KPI with its own loading/error micro-state so
 *     one failed source (e.g. documents) never blanks the others
 *   - Compute period-over-period deltas only where a real baseline exists
 *     (Queries / LLM Calls / Cost via cost-summary previous period)
 * Dependencies:
 *   - features/admin/admin-format
 * Public Exports:
 *   - AdminKpiCards
 * Database/Table: N/A (aggregates workspaces/members/documents/cost-summary)
 * Related Modules: features/admin/AdminDashboardView
 * Important Notes: Workspaces/Users/Documents have no historical baseline
 *   available from the contract — shown without a delta (never fabricated).
 * =============================================================================
 */

"use client";

import { AlertCircle } from "lucide-react";

import {
  deltaOf,
  formatCompactNumber,
  formatCurrencyUsd,
  formatPercent,
} from "@/features/admin/admin-format";
import { cn } from "@/lib/utils";

type MetricState = {
  value: number | null;
  loading: boolean;
  error: string | null;
};

type Props = {
  workspaces: MetricState;
  users: MetricState;
  documents: MetricState;
  queries: MetricState;
  queriesDeltaPrev: number | null;
  llmCalls: MetricState;
  llmCallsDeltaPrev: number | null;
  cost: MetricState;
  costDeltaPrev: number | null;
};

function DeltaTag({ current, previous }: { current: number | null; previous: number | null }) {
  if (current === null || previous === null) return null;
  const ratio = deltaOf(current, previous);
  if (ratio === null) return null;
  const isUp = ratio > 0;
  const isFlat = ratio === 0;
  return (
    <span
      className={cn(
        "text-caption font-medium",
        isFlat ? "text-tertiary" : isUp ? "text-success" : "text-danger",
      )}
    >
      {isFlat ? "±0%" : `${isUp ? "↑" : "↓"} ${formatPercent(Math.abs(ratio), 1)}`}
      <span className="ml-1 font-normal text-tertiary">so với kỳ trước</span>
    </span>
  );
}

function MetricCard({
  label,
  state,
  format,
  deltaPrev,
}: {
  label: string;
  state: MetricState;
  format: (v: number) => string;
  deltaPrev?: number | null;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border-default bg-surface p-4">
      <p className="text-caption font-medium uppercase tracking-wide text-tertiary">{label}</p>
      {state.loading ? (
        <div className="h-7 w-16 animate-pulse rounded bg-elevated" />
      ) : state.error ? (
        <div className="flex items-center gap-1.5 text-danger" title={state.error}>
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          <span className="text-body-sm font-medium">Lỗi</span>
        </div>
      ) : (
        <p className="text-h1 font-semibold text-primary">
          {state.value === null ? "—" : format(state.value)}
        </p>
      )}
      {!state.loading && !state.error && state.value !== null && deltaPrev !== undefined ? (
        <DeltaTag current={state.value} previous={deltaPrev} />
      ) : null}
    </div>
  );
}

export function AdminKpiCards({
  workspaces,
  users,
  documents,
  queries,
  queriesDeltaPrev,
  llmCalls,
  llmCallsDeltaPrev,
  cost,
  costDeltaPrev,
}: Props) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <MetricCard label="Workspaces" state={workspaces} format={formatCompactNumber} />
      <MetricCard label="Users" state={users} format={formatCompactNumber} />
      <MetricCard label="Documents" state={documents} format={formatCompactNumber} />
      <MetricCard
        label="Queries"
        state={queries}
        format={formatCompactNumber}
        deltaPrev={queriesDeltaPrev}
      />
      <MetricCard
        label="LLM Calls"
        state={llmCalls}
        format={formatCompactNumber}
        deltaPrev={llmCallsDeltaPrev}
      />
      <MetricCard
        label="Estimated Cost"
        state={cost}
        format={formatCurrencyUsd}
        deltaPrev={costDeltaPrev}
      />
    </div>
  );
}

export type { MetricState };
