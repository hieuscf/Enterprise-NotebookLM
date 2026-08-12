/**
 * =============================================================================
 * File: graph-selection.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Pure helpers for path highlighting and neighborhood expansion.
 * Responsibilities:
 *   - Compute connected node/edge sets for a selection + depth
 *   - Filter graph by type / relation / view mode
 *   - Progressive visible-set for large graphs (overview + expand)
 * Dependencies:
 *   - types/knowledge-graph
 * Public Exports:
 *   - computeNeighborhood, filterGraphPayload, searchGraphNodes,
 *     resolveVisibleGraph, LARGE_GRAPH_THRESHOLD
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Depth limits BFS hops from the selected node (display).
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

/** Above this count, overview mode clusters until the user expands nodes. */
export const LARGE_GRAPH_THRESHOLD = 28;

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

/**
 * Resolve which nodes/edges to render:
 * - With selection → neighborhood limited by depth (display scope)
 * - Large graph, no selection → topics + top entities + linked docs + expanded hops
 * - Otherwise → full filtered set
 */
export function resolveVisibleGraph(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  opts: {
    selectedNodeId: string | null;
    depth: number;
    expandedIds: ReadonlySet<string>;
  },
): { nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[] } {
  const { selectedNodeId, depth, expandedIds } = opts;

  if (selectedNodeId) {
    const nb = computeNeighborhood(edges, selectedNodeId, depth);
    for (const id of expandedIds) {
      if (!nb.nodeIds.has(id)) continue;
      const extra = computeNeighborhood(edges, id, 1);
      for (const nid of extra.nodeIds) nb.nodeIds.add(nid);
      for (const eid of extra.edgeIds) nb.edgeIds.add(eid);
    }
    const visNodes = nodes.filter((n) => nb.nodeIds.has(n.id));
    const ids = new Set(visNodes.map((n) => n.id));
    const visEdges = edges.filter(
      (e) => ids.has(e.source) && ids.has(e.target),
    );
    return { nodes: visNodes, edges: visEdges };
  }

  if (nodes.length <= LARGE_GRAPH_THRESHOLD && expandedIds.size === 0) {
    return { nodes, edges };
  }

  const degree = new Map<string, number>();
  for (const n of nodes) degree.set(n.id, 0);
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }

  const keep = new Set<string>();
  for (const n of nodes) {
    if (n.type === "topic") keep.add(n.id);
  }

  const entities = nodes
    .filter((n) => n.type === "entity")
    .sort(
      (a, b) =>
        (b.connection_count ?? degree.get(b.id) ?? 0) -
        (a.connection_count ?? degree.get(a.id) ?? 0),
    );
  for (const n of entities.slice(0, 12)) keep.add(n.id);

  for (const e of edges) {
    if (keep.has(e.source) || keep.has(e.target)) {
      const otherId = keep.has(e.source) ? e.target : e.source;
      const other = nodes.find((n) => n.id === otherId && n.type === "document");
      if (other) keep.add(other.id);
    }
  }

  for (const id of expandedIds) {
    keep.add(id);
    const nb = computeNeighborhood(edges, id, 1);
    for (const nid of nb.nodeIds) keep.add(nid);
  }

  const visNodes = nodes.filter((n) => keep.has(n.id));
  const ids = new Set(visNodes.map((n) => n.id));
  const visEdges = edges.filter(
    (e) => ids.has(e.source) && ids.has(e.target),
  );
  return { nodes: visNodes, edges: visEdges };
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
    if (
      e.relation.toLowerCase().includes(q) ||
      e.label?.toLowerCase().includes(q)
    ) {
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
