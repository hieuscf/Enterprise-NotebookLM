/**
 * =============================================================================
 * File: admin-format.ts
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Pure formatting + derivation helpers shared across Admin Dashboard
 *          cards (currency, latency, dates, route/status labels & colors,
 *          pipeline health rollups derived from the raw pipeline_runs sample).
 * Responsibilities:
 *   - Vietnamese-locale number/currency/date formatting (matches app tone)
 *   - route_type / pipeline status → label + semantic Tailwind classes
 *   - Derive pipeline status counts + per-stage completion % from a bounded
 *     pipeline_runs sample (no backend aggregate endpoint exists yet)
 * Dependencies:
 *   - lib/pipeline-stages (PIPELINE_STAGE_ORDER / STAGE_LABEL_VI — reused,
 *     not redefined)
 * Public Exports:
 *   - formatCurrencyUsd, formatCompactNumber, formatPercent, formatLatency,
 *     formatDateTimeShort, formatTimeShort, ROUTE_LABEL_VI, ROUTE_BADGE_CLASS,
 *     PIPELINE_STATUS_LABEL_VI, PIPELINE_STATUS_BADGE_CLASS, deltaOf,
 *     derivePipelineHealth, shortId
 * Database/Table: N/A
 * Related Modules: features/admin/*
 * Important Notes: Keep all derivations here (not inline in components) so
 *   every card computes numbers the same way.
 * =============================================================================
 */

import { PIPELINE_STAGE_ORDER, STAGE_LABEL_VI } from "@/lib/pipeline-stages";
import type { RouteType } from "@/types/chat";
import type { PipelineRun, PipelineStageName, PipelineStatus } from "@/types/documents";

export function formatCurrencyUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(value);
}

export function formatPercent(ratio: number, digits = 0): string {
  if (!Number.isFinite(ratio)) return "—";
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms >= 10000 ? 0 : 1)}s`;
}

export function formatDateTimeShort(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatTimeShort(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", { timeStyle: "medium" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

/** % change vs previous period — null when the previous baseline is 0 (undefined trend). */
export function deltaOf(curr: number, prev: number): number | null {
  if (prev === 0) return curr === 0 ? 0 : null;
  return (curr - prev) / prev;
}

export const ROUTE_ORDER: RouteType[] = ["cache_hit", "metadata", "factoid", "complex"];

export const ROUTE_LABEL_VI: Record<RouteType, string> = {
  cache_hit: "Cache Hit",
  metadata: "Metadata",
  factoid: "Factoid",
  complex: "Complex",
};

/** Dot + bar color — semantic, not decorative (cheap→expensive reading order). */
export const ROUTE_DOT_CLASS: Record<RouteType, string> = {
  cache_hit: "bg-success",
  metadata: "bg-info",
  factoid: "bg-accent-secondary",
  complex: "bg-warning",
};

export const ROUTE_BADGE_CLASS: Record<RouteType, string> = {
  cache_hit: "bg-success/10 text-success",
  metadata: "bg-info/10 text-info",
  factoid: "bg-accent-secondary-soft text-accent-secondary",
  complex: "bg-warning/10 text-warning",
};

export const PIPELINE_STATUS_LABEL_VI: Record<PipelineStatus, string> = {
  pending: "Chờ xử lý",
  running: "Đang xử lý",
  completed: "Hoàn tất",
  failed: "Lỗi",
};

export const PIPELINE_STATUS_BADGE_CLASS: Record<PipelineStatus, string> = {
  pending: "bg-elevated text-tertiary",
  running: "bg-info/10 text-info",
  completed: "bg-success/10 text-success",
  failed: "bg-danger-soft text-danger",
};

export type PipelineHealthSummary = {
  total: number;
  byStatus: Record<PipelineStatus, number>;
  stageCompletion: Array<{
    stage: PipelineStageName;
    label: string;
    completed: number;
    total: number;
    ratio: number | null;
  }>;
};

/**
 * Derive status counts + per-stage completion ratios from a bounded sample of
 * pipeline_runs (see useAdminPipelineRuns — up to 100 most-recent runs). This
 * is intentionally a sample rollup, not a workspace-wide aggregate, because
 * the admin contract does not expose a counts/aggregate endpoint.
 */
export function derivePipelineHealth(runs: PipelineRun[]): PipelineHealthSummary {
  const byStatus: Record<PipelineStatus, number> = {
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };
  for (const run of runs) {
    byStatus[run.status] += 1;
  }

  const stageTotals = new Map<PipelineStageName, { completed: number; total: number }>();
  for (const run of runs) {
    for (const stage of run.stages) {
      const entry = stageTotals.get(stage.stage) ?? { completed: 0, total: 0 };
      entry.total += 1;
      if (stage.status === "completed") entry.completed += 1;
      stageTotals.set(stage.stage, entry);
    }
  }

  const stageCompletion = PIPELINE_STAGE_ORDER.map((stage) => {
    const entry = stageTotals.get(stage);
    const total = entry?.total ?? 0;
    const completed = entry?.completed ?? 0;
    return {
      stage,
      label: STAGE_LABEL_VI[stage],
      completed,
      total,
      ratio: total > 0 ? completed / total : null,
    };
  });

  return { total: runs.length, byStatus, stageCompletion };
}

export function pipelineDurationLabel(run: PipelineRun): string {
  if (!run.started_at) return "—";
  const start = new Date(run.started_at).getTime();
  const end = run.completed_at ? new Date(run.completed_at).getTime() : null;
  if (end === null) return "—";
  const ms = Math.max(0, end - start);
  return formatLatency(ms);
}
