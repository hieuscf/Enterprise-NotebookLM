/**
 * =============================================================================
 * File: graph-selection.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Pure helpers for path highlighting and neighborhood expansion.
 * Responsibilities:
 *   - Compute connected node/edge sets for a selection + depth
 *   - Filter graph by type / relation / view mode
 * Dependencies:
 *   - types/knowledge-graph
 * Public Exports:
 *   - computeNeighborhood, filterGraphPayload, searchGraphNodes
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Depth limits BFS hops from the selected node.
 * =============================================================================
 */

import type {
  KnowledgeGraphEdge,
  KnowledgeGraphFilters,
  KnowledgeGraphNode,
  KnowledgeGraphNodeType,
  KnowledgeGraphPayload,
  KnowledgeGraphViewMode,
} from "@/types/knowledge-graph";

export type Neighborhood = {
  nodeIds: Set<string>;
  edgeIds: Set<string>;
};

export function computeNeighborhood(
  edges: KnowledgeGraphEdge[],
  selectedNodeId: string | null,
  depth: number,
): Neighborhood {
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();
  if (!selectedNodeId) return { nodeIds, edgeIds };

  nodeIds.add(selectedNodeId);
  let frontier = new Set<string>([selectedNodeId]);
  const hops = Math.max(1, Math.min(5, depth));

  for (let i = 0; i < hops; i += 1) {
    const next = new Set<string>();
    for (const e of edges) {
      const aIn = frontier.has(e.source);
      const bIn = frontier.has(e.target);
      if (aIn || bIn) {
        edgeIds.add(e.id);
        if (!nodeIds.has(e.source)) {
          nodeIds.add(e.source);
          next.add(e.source);
        }
        if (!nodeIds.has(e.target)) {
          nodeIds.add(e.target);
          next.add(e.target);
        }
      }
    }
    frontier = next;
    if (frontier.size === 0) break;
  }

  return { nodeIds, edgeIds };
}

function viewModeAllowsType(
  mode: KnowledgeGraphViewMode,
  type: KnowledgeGraphNodeType,
): boolean {
  switch (mode) {
    case "topics":
      return type === "topic" || type === "concept";
    case "entities":
      return type === "entity" || type === "concept";
    case "documents":
      return type === "document" || type === "entity";
    case "overview":
    default:
      return true;
  }
}

export function filterGraphPayload(
  payload: KnowledgeGraphPayload,
  filters: KnowledgeGraphFilters,
): { nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[] } {
  const nodes = payload.nodes.filter(
    (n) =>
      filters.nodeTypes[n.type] &&
      viewModeAllowsType(filters.viewMode, n.type),
  );
  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = payload.edges.filter((e) => {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
    const key = e.relation;
    if (key in filters.relations && !filters.relations[key]) return false;
    return true;
  });
  return { nodes, edges };
}

export function searchGraphNodes(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  query: string,
): KnowledgeGraphNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];

  const relationHits = new Set<string>();
  for (const e of edges) {
    if (e.relation.toLowerCase().includes(q) || e.label?.toLowerCase().includes(q)) {
      relationHits.add(e.source);
      relationHits.add(e.target);
    }
  }

  return nodes.filter((n) => {
    if (relationHits.has(n.id)) return true;
    if (n.label.toLowerCase().includes(q)) return true;
    if (n.description?.toLowerCase().includes(q)) return true;
    if (n.subtype?.toLowerCase().includes(q)) return true;
    if (n.type.toLowerCase().includes(q)) return true;
    return false;
  });
}
