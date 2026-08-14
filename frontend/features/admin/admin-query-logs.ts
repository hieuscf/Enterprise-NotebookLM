/**
 * =============================================================================
 * File: admin-query-logs.ts
 * Module/Service: Observability / Query Logs Console (Web App) — FR13
 * Layer: UI
 * Purpose: Pure helpers for `/admin/query-logs` — route labels, LLM invariants,
 *          overview rollups, truncation, and search matching.
 * Responsibilities:
 *   - Map route_type → English label + badge classes (reuse admin-format tokens)
 *   - Detect Query Router LLM-call invariant violations (read-only warning)
 *   - Derive sample overview KPIs + route distribution (never invent totals)
 * Dependencies:
 *   - features/admin/admin-format, types/admin, types/chat
 * Public Exports:
 *   - ROUTE_LABEL_EN, expectedLlmCalls, hasRoutingInvariantViolation
 *   - deriveQueryLogsOverview, truncateQueryText, matchesQueryLogSearch
 * Database/Table: query_logs
 * Related Modules: features/admin/AdminQueryLogs*
 * Important Notes: Query logs are read-only audit data. Stats are sample-derived
 *   when the API returns a bare array (no aggregate / total metadata).
 * =============================================================================
 */

import {
  formatCount,
  formatRelativeAgo,
  formatFullTs,
} from "@/features/admin/admin-pipeline";
import {
  formatLatency,
  formatPercent,
  ROUTE_BADGE_CLASS,
  ROUTE_DOT_CLASS,
  ROUTE_ORDER,
  shortId,
} from "@/features/admin/admin-format";
import type { QueryLogItem } from "@/types/admin";
import type { RouteType } from "@/types/chat";

export {
  formatCount,
  formatFullTs,
  formatLatency,
  formatPercent,
  formatRelativeAgo,
  ROUTE_BADGE_CLASS,
  ROUTE_DOT_CLASS,
  ROUTE_ORDER,
  shortId,
};

/** English UI labels (Scholarly Precision / observability console). */
export const ROUTE_LABEL_EN: Record<RouteType, string> = {
  cache_hit: "Cache Hit",
  metadata: "Metadata",
  section_extraction: "Section Extraction",
  factoid: "Factoid",
  complex: "Complex",
};

/** Prefer English for this console. */
export const ROUTE_LABEL = ROUTE_LABEL_EN;

/** Icon-like markers so route identity is not color-only. */
export const ROUTE_MARKER: Record<RouteType, string> = {
  cache_hit: "◈",
  metadata: "▣",
  section_extraction: "▤",
  factoid: "◆",
  complex: "✦",
};

/**
 * Presentation-only latency warning threshold (ms). Not an SLA —
 * used only to draw subtle visual attention in the table/drawer.
 */
export const LATENCY_WARN_MS = 2_000;

export type ExpectedLlmCalls = {
  /** Inclusive upper bound (0 for zero-LLM routes; 1 for complex). */
  max: number;
  label: string;
};

export function expectedLlmCalls(route: RouteType): ExpectedLlmCalls {
  if (route === "complex") {
    return { max: 1, label: "≤ 1" };
  }
  return { max: 0, label: "0" };
}

/**
 * Query Router invariants (project rules):
 * - cache_hit / metadata / section_extraction / factoid → llm_calls_count must be 0
 * - complex → llm_calls_count must be ≤ 1
 * UI never mutates the row; it only surfaces a warning.
 */
export function hasRoutingInvariantViolation(log: QueryLogItem): boolean {
  const expected = expectedLlmCalls(log.route_type);
  return log.llm_calls_count > expected.max;
}

export function llmCallsHint(log: QueryLogItem): string {
  if (log.llm_calls_count === 0) return "No LLM";
  if (log.llm_calls_count === 1) return "1 call";
  return `${log.llm_calls_count} calls`;
}

export type RouteDistributionRow = {
  route: RouteType;
  label: string;
  count: number;
  ratio: number;
};

export type QueryLogsOverviewStats = {
  total: number;
  cacheHitRate: number | null;
  totalLlmCalls: number;
  avgLatencyMs: number | null;
  distribution: RouteDistributionRow[];
  sampleCapped: boolean;
};

export function deriveQueryLogsOverview(
  logs: QueryLogItem[],
  sampleCapped: boolean,
): QueryLogsOverviewStats {
  const total = logs.length;
  const byRoute: Record<RouteType, number> = {
    cache_hit: 0,
    metadata: 0,
    section_extraction: 0,
    factoid: 0,
    complex: 0,
  };
  let totalLlmCalls = 0;
  let latencySum = 0;
  let latencyCount = 0;

  for (const log of logs) {
    byRoute[log.route_type] += 1;
    totalLlmCalls += Math.max(0, log.llm_calls_count);
    if (log.latency_ms !== null && log.latency_ms !== undefined) {
      latencySum += log.latency_ms;
      latencyCount += 1;
    }
  }

  const distribution: RouteDistributionRow[] = ROUTE_ORDER.map((route) => ({
    route,
    label: ROUTE_LABEL_EN[route],
    count: byRoute[route],
    ratio: total > 0 ? byRoute[route] / total : 0,
  }));

  return {
    total,
    cacheHitRate: total > 0 ? byRoute.cache_hit / total : null,
    totalLlmCalls,
    avgLatencyMs: latencyCount > 0 ? latencySum / latencyCount : null,
    distribution,
    sampleCapped,
  };
}

export function truncateQueryText(text: string, max = 64): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max)}…`;
}

export function matchesQueryLogSearch(log: QueryLogItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystacks = [
    log.query_text,
    log.id,
    log.user_id,
    log.model_used ?? "",
    log.route_type,
    log.message_id ?? "",
    log.cache_id ?? "",
  ];
  return haystacks.some((h) => h.toLowerCase().includes(q));
}

export type RoutingDecisionCopy = {
  title: string;
  body: string;
  expectedLabel: string;
};

export function routingDecisionCopy(route: RouteType): RoutingDecisionCopy {
  switch (route) {
    case "cache_hit":
      return {
        title: "Cache Hit",
        body: "The query was served from query cache.",
        expectedLabel: "0",
      };
    case "metadata":
      return {
        title: "Metadata Query",
        body: "The query was resolved through structured metadata/database access.",
        expectedLabel: "0",
      };
    case "section_extraction":
      return {
        title: "Section Extraction",
        body: "The query was answered from document heading hierarchy without an LLM.",
        expectedLabel: "0",
      };
    case "factoid":
      return {
        title: "Simple Factoid",
        body: "The query was resolved extractively from a high-confidence chunk.",
        expectedLabel: "0",
      };
    case "complex":
      return {
        title: "Complex Query",
        body: "This query was routed through the full RAG pipeline.",
        expectedLabel: "≤ 1",
      };
  }
}
