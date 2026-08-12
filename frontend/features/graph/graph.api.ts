/**
 * =============================================================================
 * File: graph.api.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: Adapter
 * Purpose: Load workspace-scoped Knowledge Graph payloads for the UI.
 * Responsibilities:
 *   - Attempt future OpenAPI graph-read endpoint when available
 *   - Fall back to demo graph so the exploration UI is usable today
 * Dependencies:
 *   - lib/api-client, features/graph/data/demo-graph
 * Public Exports:
 *   - fetchKnowledgeGraph
 * Database/Table: entities, entity_relations, topics (via future API)
 * Related Modules: features/graph/useKnowledgeGraph.ts
 * Important Notes: Demo fallback is intentional until OpenAPI publishes
 *   GET /workspaces/{id}/knowledge-graph.
 * =============================================================================
 */

import { buildDemoKnowledgeGraph } from "@/features/graph/data/demo-graph";
import { apiFetch, ApiClientError, parseApiError } from "@/lib/api-client";
import type { KnowledgeGraphPayload } from "@/types/knowledge-graph";

/**
 * Prefer live API; on 404/501 fall back to workspace-stamped demo data.
 * Other errors are rethrown so the UI can show an error state.
 */
export async function fetchKnowledgeGraph(
  workspaceId: string,
): Promise<{ data: KnowledgeGraphPayload; source: "api" | "demo" }> {
  try {
    const response = await apiFetch(
      `/workspaces/${workspaceId}/knowledge-graph`,
    );
    if (response.status === 404 || response.status === 501) {
      return { data: buildDemoKnowledgeGraph(workspaceId), source: "demo" };
    }
    if (!response.ok) {
      throw await parseApiError(response);
    }
    const data = (await response.json()) as KnowledgeGraphPayload;
    if (data.workspace_id && data.workspace_id !== workspaceId) {
      throw new Error("Knowledge graph workspace mismatch.");
    }
    return {
      data: { ...data, workspace_id: workspaceId },
      source: "api",
    };
  } catch (err) {
    if (err instanceof ApiClientError && (err.status === 404 || err.status === 501)) {
      return { data: buildDemoKnowledgeGraph(workspaceId), source: "demo" };
    }
    if (
      err instanceof TypeError ||
      (err instanceof Error && /failed to fetch/i.test(err.message))
    ) {
      return { data: buildDemoKnowledgeGraph(workspaceId), source: "demo" };
    }
    throw err;
  }
}
