/**
 * =============================================================================
 * File: admin-usage.ts
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: Pure helpers for `/admin/usage` — date presets, cost formatting,
 *          model/route rollups, and deterministic insights.
 * Responsibilities:
 *   - Build YYYY-MM-DD ranges without timezone day-shift
 *   - Format USD / shares / cost-per-call (presentation-only derivations)
 *   - Normalize route breakdown to all 4 Query Router routes
 * Dependencies:
 *   - features/admin/admin-format, types/admin, types/chat
 * Public Exports:
 *   - resolveUsageDateRange, formatCostUsd, deriveUsageInsights, …
 * Database/Table: message_generations (via CostSummary)
 * Related Modules: features/admin/AdminUsage*
 * Important Notes: CostSummary is the source of truth. No fake time-series.
 *   by_route_type has count only (no cost_usd) per OpenAPI.
 * =============================================================================
 */

import {
  formatCurrencyUsd,
  formatPercent,
  ROUTE_BADGE_CLASS,
  ROUTE_DOT_CLASS,
  ROUTE_ORDER,
} from "@/features/admin/admin-format";
import { formatCount } from "@/features/admin/admin-pipeline";
import type { CostByModelItem, CostByRouteTypeItem, CostSummary } from "@/types/admin";
import type { RouteType } from "@/types/chat";

export {
  formatCount,
  formatCurrencyUsd,
  formatPercent,
  ROUTE_BADGE_CLASS,
  ROUTE_DOT_CLASS,
  ROUTE_ORDER,
};

export const ROUTE_LABEL_EN: Record<RouteType, string> = {
  cache_hit: "Cache Hit",
  metadata: "Metadata",
  section_extraction: "Section Extraction",
  factoid: "Factoid",
  complex: "Complex",
};

export const ROUTE_LABEL = ROUTE_LABEL_EN;

/** Expected LLM calls for Query Router design (explanation, not measured cost). */
export const ROUTE_EXPECTED_LLM: Record<RouteType, string> = {
  cache_hit: "0 LLM",
  metadata: "0 LLM",
  section_extraction: "0 LLM",
  factoid: "0 LLM",
  complex: "≤1 LLM",
};

export type UsageDatePreset =
  | "today"
  | "last_7"
  | "last_30"
  | "this_month"
  | "previous_month"
  | "custom";

export const USAGE_DATE_PRESETS: { value: UsageDatePreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "last_7", label: "Last 7 days" },
  { value: "last_30", label: "Last 30 days" },
  { value: "this_month", label: "This month" },
  { value: "previous_month", label: "Previous month" },
  { value: "custom", label: "Custom" },
];

/** Local calendar YYYY-MM-DD — never use toISOString (UTC can shift the day). */
export function toLocalDateParam(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseLocalDateParam(raw: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const date = new Date(y, mo - 1, d);
  if (
    date.getFullYear() !== y ||
    date.getMonth() !== mo - 1 ||
    date.getDate() !== d
  ) {
    return null;
  }
  return date;
}

export function resolveUsageDateRange(
  preset: UsageDatePreset,
  customFrom?: string,
  customTo?: string,
  now = new Date(),
): { from: string; to: string } {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  if (preset === "custom") {
    const from = customFrom && parseLocalDateParam(customFrom) ? customFrom : toLocalDateParam(today);
    const to = customTo && parseLocalDateParam(customTo) ? customTo : toLocalDateParam(today);
    return from <= to ? { from, to } : { from: to, to: from };
  }

  if (preset === "today") {
    const s = toLocalDateParam(today);
    return { from: s, to: s };
  }

  if (preset === "last_7") {
    const from = new Date(today);
    from.setDate(from.getDate() - 6);
    return { from: toLocalDateParam(from), to: toLocalDateParam(today) };
  }

  if (preset === "last_30") {
    const from = new Date(today);
    from.setDate(from.getDate() - 29);
    return { from: toLocalDateParam(from), to: toLocalDateParam(today) };
  }

  if (preset === "this_month") {
    const from = new Date(today.getFullYear(), today.getMonth(), 1);
    return { from: toLocalDateParam(from), to: toLocalDateParam(today) };
  }

  // previous_month
  const firstThis = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastPrev = new Date(firstThis);
  lastPrev.setDate(0);
  const firstPrev = new Date(lastPrev.getFullYear(), lastPrev.getMonth(), 1);
  return { from: toLocalDateParam(firstPrev), to: toLocalDateParam(lastPrev) };
}

export function formatDateRangeLabel(from: string, to: string): string {
  const a = parseLocalDateParam(from);
  const b = parseLocalDateParam(to);
  if (!a || !b) return `${from} — ${to}`;
  const fmt = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  if (from === to) return fmt.format(a);
  const short = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  });
  if (a.getFullYear() === b.getFullYear()) {
    return `${short.format(a)} – ${fmt.format(b)}`;
  }
  return `${fmt.format(a)} — ${fmt.format(b)}`;
}

export function formatPeriodShort(from: string, to: string): string {
  const a = parseLocalDateParam(from);
  const b = parseLocalDateParam(to);
  if (!a || !b) return `${from} – ${to}`;
  const short = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  });
  if (from === to) return short.format(a);
  return `${short.format(a)} – ${short.format(b)}`;
}

/**
 * Display formatting for USD. Uses backend totals as-is; only affects display
 * digits (2–4) based on magnitude. Tooltip/detail can use full raw value.
 */
export function formatCostUsd(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  let digits = 2;
  if (abs > 0 && abs < 0.01) digits = 4;
  else if (abs > 0 && abs < 1) digits = 4;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCostExact(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(value);
}

export function costPerCall(costUsd: number, calls: number): number | null {
  if (!Number.isFinite(costUsd) || !Number.isFinite(calls) || calls <= 0) {
    return null;
  }
  return costUsd / calls;
}

export function costShare(part: number, total: number): number | null {
  if (!Number.isFinite(part) || !Number.isFinite(total) || total <= 0) return null;
  return part / total;
}

export function modelDisplayName(modelUsed: string | null | undefined): string {
  const raw = (modelUsed ?? "").trim();
  if (!raw || raw.toLowerCase() === "unknown" || raw.toLowerCase() === "null") {
    return "Unknown / Not recorded";
  }
  return raw;
}

export type NormalizedRouteRow = {
  route: RouteType;
  label: string;
  count: number;
  share: number | null;
  expectedLlm: string;
};

/**
 * Always surface all Query Router routes (including zero counts) so Admins
 * can see zero-LLM routes even when the API omits empty buckets.
 */
export function normalizeRouteBreakdown(
  items: CostByRouteTypeItem[],
): NormalizedRouteRow[] {
  const counts: Record<RouteType, number> = {
    cache_hit: 0,
    metadata: 0,
    section_extraction: 0,
    factoid: 0,
    complex: 0,
  };
  for (const item of items) {
    if (item.route_type in counts) {
      counts[item.route_type as RouteType] += item.count;
    }
  }
  const total = ROUTE_ORDER.reduce((sum, r) => sum + counts[r], 0);
  return ROUTE_ORDER.map((route) => ({
    route,
    label: ROUTE_LABEL_EN[route],
    count: counts[route],
    share: total > 0 ? counts[route] / total : null,
    expectedLlm: ROUTE_EXPECTED_LLM[route],
  }));
}

export type ModelBreakdownRow = CostByModelItem & {
  displayName: string;
  share: number | null;
  costPerCall: number | null;
};

export function normalizeModelBreakdown(
  items: CostByModelItem[],
  totalCostUsd: number,
): ModelBreakdownRow[] {
  return [...items]
    .map((m) => ({
      ...m,
      prompt_tokens: m.prompt_tokens ?? 0,
      completion_tokens: m.completion_tokens ?? 0,
      total_tokens: m.total_tokens ?? 0,
      displayName: modelDisplayName(m.model_used),
      share: costShare(m.cost_usd, totalCostUsd),
      costPerCall: costPerCall(m.cost_usd, m.calls),
    }))
    .sort((a, b) => b.cost_usd - a.cost_usd);
}

export type UsageInsights = {
  mostExpensiveModel: ModelBreakdownRow | null;
  highestUsageRoute: NormalizedRouteRow | null;
  zeroCostRouteLabels: string[];
  totalRouteQueries: number;
};

export function deriveUsageInsights(summary: CostSummary | null): UsageInsights {
  if (!summary) {
    return {
      mostExpensiveModel: null,
      highestUsageRoute: null,
      zeroCostRouteLabels: [],
      totalRouteQueries: 0,
    };
  }
  const models = normalizeModelBreakdown(summary.by_model, summary.total_cost_usd);
  const routes = normalizeRouteBreakdown(summary.by_route_type);
  const totalRouteQueries = routes.reduce((s, r) => s + r.count, 0);
  const topRoute = routes.reduce((best, row) =>
    row.count > best.count ? row : best,
  );

  return {
    mostExpensiveModel: models[0] ?? null,
    highestUsageRoute: topRoute.count > 0 ? topRoute : null,
    zeroCostRouteLabels: ["Cache Hit", "Metadata", "Factoid"],
    totalRouteQueries,
  };
}

export function isEmptyUsage(summary: CostSummary | null): boolean {
  if (!summary) return true;
  return (
    summary.total_llm_calls === 0 &&
    summary.total_cost_usd === 0 &&
    summary.by_model.length === 0 &&
    summary.by_route_type.every((r) => r.count === 0)
  );
}

export function parseUsagePreset(raw: string | null): UsageDatePreset {
  const allowed = new Set<UsageDatePreset>([
    "today",
    "last_7",
    "last_30",
    "this_month",
    "previous_month",
    "custom",
  ]);
  if (raw && allowed.has(raw as UsageDatePreset)) return raw as UsageDatePreset;
  return "last_7";
}
