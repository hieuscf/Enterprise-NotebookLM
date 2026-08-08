/**
 * =============================================================================
 * File: useAdminCostSummary.ts
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Load GET /admin/workspaces/{id}/cost-summary for the selected date
 *          range, plus the immediately preceding period of equal length so
 *          KPI/Usage cards can show a real (not invented) trend delta.
 * Responsibilities:
 *   - Fetch current + previous period in parallel; expose loading/error/reload
 *   - Compute from/to (YYYY-MM-DD) for a given "last N days" window
 * Dependencies:
 *   - lib/admin.api.getWorkspaceCostSummary
 * Public Exports:
 *   - useAdminCostSummary, type CostRangeDays
 * Database/Table: message_generations, agent_events
 * Related Modules: features/admin/AdminKpiCards, QueryRoutingCard, UsageCostCard
 * Important Notes: Backend only returns one aggregate per call (no daily time
 *   series) — do not fabricate a per-day chart from this endpoint.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { getWorkspaceCostSummary } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { CostSummary } from "@/types/admin";

export type CostRangeDays = 7 | 30 | 90;

function toDateParam(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** [from, to] for "last N days" ending today, plus the prior equal-length window. */
export function computeRangeWindows(days: CostRangeDays, now = new Date()) {
  const to = new Date(now);
  const from = new Date(now);
  from.setDate(from.getDate() - (days - 1));

  const previousTo = new Date(from);
  previousTo.setDate(previousTo.getDate() - 1);
  const previousFrom = new Date(previousTo);
  previousFrom.setDate(previousFrom.getDate() - (days - 1));

  return {
    from: toDateParam(from),
    to: toDateParam(to),
    previousFrom: toDateParam(previousFrom),
    previousTo: toDateParam(previousTo),
  };
}

export function useAdminCostSummary(
  workspaceId: string | null,
  days: CostRangeDays,
) {
  const [current, setCurrent] = useState<CostSummary | null>(null);
  const [previous, setPrevious] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    const { from, to, previousFrom, previousTo } = computeRangeWindows(days);
    try {
      const [curr, prev] = await Promise.all([
        getWorkspaceCostSummary(workspaceId, { from, to }),
        getWorkspaceCostSummary(workspaceId, { from: previousFrom, to: previousTo }),
      ]);
      setCurrent(curr);
      setPrevious(prev);
    } catch (err) {
      setCurrent(null);
      setPrevious(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được dữ liệu chi phí & sử dụng.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId, days]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { current, previous, loading, error, reload };
}
