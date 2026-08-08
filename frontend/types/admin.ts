/**
 * =============================================================================
 * File: admin.ts
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Admin/Observability endpoints matching backend
 *          Pydantic schemas (app/schemas/admin.py) — query-logs, cost-summary.
 * Responsibilities:
 *   - Mirror QueryLogResponse / CostSummaryResponse 1:1 (no invented fields)
 * Dependencies:
 *   - types/chat (RouteType is already defined there — reused, not redefined)
 * Public Exports:
 *   - QueryLogItem, CostByModelItem, CostByRouteTypeItem, AgentTypeCostSummary,
 *     CostSummary
 * Database/Table: query_logs, message_generations, agent_events
 * Related Modules: lib/admin.api, features/admin/*, backend/app/schemas/admin.py
 * Important Notes: pipeline-runs reuses the existing `PipelineRun` type from
 *   types/documents.ts (identical shape) — not redefined here.
 * =============================================================================
 */

import type { RouteType } from "./chat";

/** OpenAPI QueryLog (admin audit row) — matches app/schemas/admin.py QueryLogResponse. */
export type QueryLogItem = {
  id: string;
  user_id: string;
  message_id: string | null;
  cache_id: string | null;
  query_text: string;
  route_type: RouteType;
  llm_calls_count: number;
  model_used: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type CostByModelItem = {
  model_used: string;
  calls: number;
  cost_usd: number;
};

export type CostByRouteTypeItem = {
  route_type: string;
  count: number;
};

/** Per Micro Agent cost/latency rollup (FR14) — additive, may be empty. */
export type AgentTypeCostSummary = {
  total_cost_usd: number;
  total_latency_ms: number;
  count: number;
  average_latency_ms: number;
};

export type CostSummary = {
  total_cost_usd: number;
  total_llm_calls: number;
  by_model: CostByModelItem[];
  by_route_type: CostByRouteTypeItem[];
  by_agent_type: Record<string, AgentTypeCostSummary>;
};
