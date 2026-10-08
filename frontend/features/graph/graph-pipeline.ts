/**
 * =============================================================================
 * File: graph-pipeline.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Turn a filtered Knowledge Graph into a focused, ranked subgraph.
 * Responsibilities:
 *   - Choose a focus node and a depth-limited neighborhood
 *   - Rank nodes with signals already present on the graph
 *   - Group by existing entity type / subtype for visualization only
 *   - Hide low-relevance nodes and noisy edges without deleting data
 * Dependencies:
 *   - types/knowledge-graph, graph-style
 * Public Exports:
 *   - prepareKnowledgeStructure, selectDisplayEdges, resolveOpenedNodeId,
 *     pickCentralNode, semanticGroupKey
 * Database/Table: N/A
 * Related Modules: features/graph/layout/structuredLayout.ts
 * Important Notes: Presentation only. Never mutates stored graph payloads.
 * =============================================================================
 */

import { nodeTypeLabel } from "@/features/graph/graph-style";
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphNodeType,
} from "@/types/knowledge-graph";

/** Nodes shown per semantic group before the user asks for more. */
export const GROUP_PAGE = 5;

/** Open columns before the rest start collapsed. */
export const MAX_OPEN_GROUPS = 8;

/** Disconnected components shown as cards before "show more". */
export const COMPONENT_PAGE = 4;

/** Soft cap so a single screen does not draw every cross edge. */
export const MAX_PRIMARY_EDGES = 36;

const RELATION_IMPORTANCE: Record<string, number> = {
  contains: 1,
  owns: 0.95,
  manages: 0.92,
  supports: 0.9,
  targets: 0.78,
  depends_on: 0.7,
  mentions: 0.55,
  related_to: 0.48,
};

export function relationImportance(relation: string): number {
  return RELATION_IMPORTANCE[relation] ?? 0.5;
}

export type RankedMember = {
  node: KnowledgeGraphNode;
  hop: number;
  score: number;
};

export type PreparedGroup = {
  key: string;
  label: string;
  accentType: KnowledgeGraphNodeType;
  /** Every member inside the depth window, highest score first. */
  members: RankedMember[];
  visible: RankedMember[];
  hiddenCount: number;
  collapsed: boolean;
  maxScore: number;
};

export type PreparedComponent = {
  id: string;
  focusId: string;
  label: string;
  count: number;
  /** Click reveals the remaining collapsed components. */
  more: boolean;
};

export type PreparedStructure = {
  focus: KnowledgeGraphNode | null;
  groups: PreparedGroup[];
  components: PreparedComponent[];
  /** Real edges whose endpoints are both currently visible. */
  candidateEdges: KnowledgeGraphEdge[];
  /** node id → semantic group key. Focus is omitted. */
  groupOf: Map<string, string>;
};

export type GroupOverride = "open" | "closed";

export type StructureOptions = {
  explicitFocusId: string | null;
  openedNodeId: string | null;
  depth: number;
  expandedIds: ReadonlySet<string>;
  groupOverrides: Readonly<Record<string, GroupOverride>>;
  /** Extra nodes revealed per group, added to GROUP_PAGE. */
  groupReveal: Readonly<Record<string, number>>;
  showAllComponents: boolean;
};

type Link = { neighbor: string; edge: KnowledgeGraphEdge };

function degreeMap(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
): Map<string, number> {
  const degree = new Map<string, number>();
  for (const n of nodes) degree.set(n.id, 0);
  for (const e of edges) {
    if (!degree.has(e.source) || !degree.has(e.target)) continue;
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  return degree;
}

function adjacency(
  nodeIds: Set<string>,
  edges: KnowledgeGraphEdge[],
): Map<string, Link[]> {
  const adj = new Map<string, Link[]>();
  for (const id of nodeIds) adj.set(id, []);
  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue;
    adj.get(edge.source)?.push({ neighbor: edge.target, edge });
    adj.get(edge.target)?.push({ neighbor: edge.source, edge });
  }
  return adj;
}

function hopsFrom(
  start: string,
  adj: Map<string, Link[]>,
  maxHop: number,
): Map<string, { hop: number; via: KnowledgeGraphEdge | null }> {
  const result = new Map<string, { hop: number; via: KnowledgeGraphEdge | null }>();
  if (!adj.has(start)) return result;
  result.set(start, { hop: 0, via: null });
  let frontier = [start];
  const limit = Math.max(0, maxHop);
  for (let hop = 1; hop <= limit; hop += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const link of adj.get(id) ?? []) {
        if (result.has(link.neighbor)) continue;
        result.set(link.neighbor, { hop, via: link.edge });
        next.push(link.neighbor);
      }
    }
    frontier = next;
    if (frontier.length === 0) break;
  }
  return result;
}

export function semanticGroupKey(node: KnowledgeGraphNode): string {
  if (node.type === "entity") {
    const subtype = node.subtype?.trim();
    return subtype ? `entity:${subtype}` : "entity";
  }
  return node.type;
}

export function semanticGroupLabel(node: KnowledgeGraphNode): string {
  if (node.type === "entity" && node.subtype?.trim()) return node.subtype.trim();
  return nodeTypeLabel(node.type);
}

function relevanceScore(
  node: KnowledgeGraphNode,
  hop: number,
  degree: number,
  via: KnowledgeGraphEdge | null,
): number {
  const confidence = typeof node.confidence === "number" ? node.confidence : 0.5;
  const degreeSignal =
    typeof node.connection_count === "number" ? node.connection_count : degree;
  const linkConfidence = typeof via?.confidence === "number" ? via.confidence : 1;
  const importance = via ? relationImportance(via.relation) : 1;
  return (
    Math.max(0, 3 - Math.min(hop, 3)) * 2 +
    Math.min(degreeSignal, 24) * 0.22 +
    confidence * 1.5 +
    linkConfidence * importance
  );
}

/**
 * Highest-signal node already in the graph: degree, confidence, topic hubs,
 * and an existing subtype that marks a root. No synthetic nodes.
 */
export function pickCentralNode(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
): string | null {
  if (nodes.length === 0) return null;
  const degree = degreeMap(nodes, edges);
  let bestId = nodes[0]?.id ?? null;
  let bestScore = Number.NEGATIVE_INFINITY;
  let bestLabel = "";
  for (const node of nodes) {
    const deg = degree.get(node.id) ?? 0;
    let score = (node.connection_count ?? deg) + (node.confidence ?? 0) * 2;
    if (node.type === "topic") score += 2.5;
    if ((node.subtype ?? "").toLowerCase().includes("root")) score += 4;
    const label = node.label;
    if (
      score > bestScore ||
      (score === bestScore && (bestId === null || label.localeCompare(bestLabel) < 0))
    ) {
      bestScore = score;
      bestId = node.id;
      bestLabel = label;
    }
  }
  return bestId;
}

export function resolveOpenedNodeId(
  nodes: KnowledgeGraphNode[],
  openedNodeId: string | null,
  openedDocumentId: string | null,
): string | null {
  if (openedNodeId && nodes.some((n) => n.id === openedNodeId)) return openedNodeId;
  if (!openedDocumentId) return null;
  const byMeta = nodes.find((n) => n.metadata?.document_id === openedDocumentId);
  if (byMeta) return byMeta.id;
  const byDocument = nodes.find(
    (n) =>
      n.type === "document" &&
      n.citations?.some((c) => c.document_id === openedDocumentId),
  );
  if (byDocument) return byDocument.id;
  const byCitation = nodes.find((n) =>
    n.citations?.some((c) => c.document_id === openedDocumentId),
  );
  return byCitation?.id ?? null;
}

function resolveFocusId(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  options: StructureOptions,
): string | null {
  if (
    options.explicitFocusId &&
    nodes.some((n) => n.id === options.explicitFocusId)
  ) {
    return options.explicitFocusId;
  }
  if (options.openedNodeId && nodes.some((n) => n.id === options.openedNodeId)) {
    return options.openedNodeId;
  }
  return pickCentralNode(nodes, edges);
}

function connectedIds(start: string, adj: Map<string, Link[]>): Set<string> {
  return new Set(hopsFrom(start, adj, Number.MAX_SAFE_INTEGER).keys());
}

function otherComponents(
  nodes: KnowledgeGraphNode[],
  nodesById: Map<string, KnowledgeGraphNode>,
  adj: Map<string, Link[]>,
  exclude: Set<string>,
  degree: Map<string, number>,
): { focusId: string; label: string; count: number; ids: string[] }[] {
  const seen = new Set(exclude);
  const comps: { focusId: string; label: string; count: number; ids: string[] }[] = [];
  for (const node of nodes) {
    if (seen.has(node.id)) continue;
    const stack = [node.id];
    const ids: string[] = [];
    seen.add(node.id);
    while (stack.length > 0) {
      const id = stack.pop();
      if (!id) break;
      ids.push(id);
      for (const link of adj.get(id) ?? []) {
        if (seen.has(link.neighbor)) continue;
        seen.add(link.neighbor);
        stack.push(link.neighbor);
      }
    }
    let hub = ids[0] ?? node.id;
    let hubScore = Number.NEGATIVE_INFINITY;
    for (const id of ids) {
      const current = nodesById.get(id);
      if (!current) continue;
      const score = relevanceScore(current, 1, degree.get(id) ?? 0, null);
      if (score > hubScore) {
        hubScore = score;
        hub = id;
      }
    }
    const hubNode = nodesById.get(hub);
    comps.push({
      focusId: hub,
      label: hubNode?.label ?? "Thành phần",
      count: ids.length,
      ids,
    });
  }
  comps.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  return comps;
}

export function prepareKnowledgeStructure(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  options: StructureOptions,
): PreparedStructure {
  const empty: PreparedStructure = {
    focus: null,
    groups: [],
    components: [],
    candidateEdges: [],
    groupOf: new Map(),
  };
  if (nodes.length === 0) return empty;

  const nodeIds = new Set(nodes.map((n) => n.id));
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const degree = degreeMap(nodes, edges);
  const adj = adjacency(nodeIds, edges);
  const focusId = resolveFocusId(nodes, edges, options);
  if (!focusId) return empty;
  const focus = nodesById.get(focusId) ?? null;
  if (!focus) return empty;

  const depth = Math.max(1, Math.min(3, Math.round(options.depth) || 2));
  const reached = hopsFrom(focusId, adj, depth);

  for (const id of options.expandedIds) {
    if (!reached.has(id)) continue;
    const baseHop = reached.get(id)?.hop ?? depth;
    const extra = hopsFrom(id, adj, 1);
    for (const [nid, info] of extra) {
      if (reached.has(nid)) continue;
      reached.set(nid, { hop: baseHop + info.hop, via: info.via });
    }
  }

  const buckets = new Map<string, RankedMember[]>();
  for (const [id, info] of reached) {
    if (id === focusId) continue;
    const node = nodesById.get(id);
    if (!node) continue;
    const key = semanticGroupKey(node);
    const member: RankedMember = {
      node,
      hop: info.hop,
      score: relevanceScore(node, info.hop, degree.get(id) ?? 0, info.via),
    };
    const list = buckets.get(key) ?? [];
    list.push(member);
    buckets.set(key, list);
  }

  const built: PreparedGroup[] = [];
  for (const [key, members] of buckets) {
    members.sort(
      (a, b) => b.score - a.score || a.node.label.localeCompare(b.node.label),
    );
    const sample = members[0]?.node;
    if (!sample) continue;
    built.push({
      key,
      label: semanticGroupLabel(sample),
      accentType: sample.type,
      members,
      visible: members,
      hiddenCount: 0,
      collapsed: false,
      maxScore: members[0]?.score ?? 0,
    });
  }
  built.sort((a, b) => b.maxScore - a.maxScore || a.label.localeCompare(b.label));

  built.forEach((group, index) => {
    const override = options.groupOverrides[group.key];
    const defaultCollapsed = index >= MAX_OPEN_GROUPS;
    group.collapsed = override
      ? override === "closed"
      : defaultCollapsed;
    if (group.collapsed) {
      group.visible = [];
      group.hiddenCount = group.members.length;
      return;
    }
    const limit = GROUP_PAGE + (options.groupReveal[group.key] ?? 0);
    const head = group.members.slice(0, limit);
    const headIds = new Set(head.map((m) => m.node.id));
    const forced = group.members.filter(
      (m) => options.expandedIds.has(m.node.id) && !headIds.has(m.node.id),
    );
    group.visible = [...head, ...forced];
    group.hiddenCount = Math.max(0, group.members.length - group.visible.length);
  });

  const groupOf = new Map<string, string>();
  const visibleIds = new Set<string>([focusId]);
  for (const group of built) {
    for (const member of group.visible) {
      groupOf.set(member.node.id, group.key);
      visibleIds.add(member.node.id);
    }
  }

  const mainComponent = connectedIds(focusId, adj);
  const comps = otherComponents(nodes, nodesById, adj, mainComponent, degree);
  const componentSlice = options.showAllComponents
    ? comps
    : comps.slice(0, COMPONENT_PAGE);
  const components: PreparedComponent[] = componentSlice.map((comp, index) => ({
    id: `component:${comp.focusId}:${index}`,
    focusId: comp.focusId,
    label: comp.label,
    count: comp.count,
    more: false,
  }));
  const hiddenComponents = comps.length - componentSlice.length;
  if (hiddenComponents > 0) {
    const next = comps[componentSlice.length];
    components.push({
      id: "component:more",
      focusId: next?.focusId ?? focusId,
      label: `+ ${hiddenComponents} thành phần`,
      count: hiddenComponents,
      more: true,
    });
  }

  const candidateEdges = edges.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
  );

  return {
    focus,
    groups: built,
    components,
    candidateEdges,
    groupOf,
  };
}

export function selectDisplayEdges(
  structure: PreparedStructure,
  showAllEdges: boolean,
): { edges: KnowledgeGraphEdge[]; hiddenCount: number } {
  const among = structure.candidateEdges;
  const focusId = structure.focus?.id ?? null;
  if (showAllEdges || among.length <= 16) {
    return { edges: among, hiddenCount: 0 };
  }

  const scored = among.map((edge) => {
    const incident = edge.source === focusId || edge.target === focusId;
    const sameGroup =
      structure.groupOf.get(edge.source) !== undefined &&
      structure.groupOf.get(edge.source) === structure.groupOf.get(edge.target);
    const importance = relationImportance(edge.relation);
    const confidence = edge.confidence ?? 0.5;
    const keep =
      incident ||
      confidence >= 0.88 ||
      importance >= 0.9 ||
      (sameGroup && importance >= 0.75);
    return {
      edge,
      incident,
      keep,
      score: confidence * importance + (incident ? 2 : 0),
    };
  });

  let kept = scored.filter((item) => item.keep);
  if (kept.length > MAX_PRIMARY_EDGES) {
    const forced = kept.filter((item) => item.incident);
    const rest = kept
      .filter((item) => !item.incident)
      .sort((a, b) => b.score - a.score)
      .slice(0, Math.max(0, MAX_PRIMARY_EDGES - forced.length));
    kept = [...forced, ...rest];
  }

  const hiddenCount = Math.max(0, among.length - kept.length);
  return { edges: kept.map((item) => item.edge), hiddenCount };
}
