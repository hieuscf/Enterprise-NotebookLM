/**
 * Node-side smoke checks for Knowledge Graph pure helpers.
 * Mirrors features/graph/graph-selection.ts selection / filter / search logic.
 * Run: node scripts/test-graph-ui.mjs
 */

function computeNeighborhood(edges, selectedNodeId, depth) {
  const nodeIds = new Set();
  const edgeIds = new Set();
  if (!selectedNodeId) return { nodeIds, edgeIds };

  nodeIds.add(selectedNodeId);
  let frontier = new Set([selectedNodeId]);
  const hops = Math.max(1, Math.min(5, depth));

  for (let i = 0; i < hops; i += 1) {
    const next = new Set();
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

function viewModeAllowsType(mode, type) {
  switch (mode) {
    case "topics":
      return type === "topic" || type === "concept";
    case "entities":
      return type === "entity" || type === "concept";
    case "documents":
      return type === "document" || type === "entity";
    default:
      return true;
  }
}

function filterGraphPayload(payload, filters) {
  const nodes = payload.nodes.filter(
    (n) => filters.nodeTypes[n.type] && viewModeAllowsType(filters.viewMode, n.type),
  );
  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = payload.edges.filter((e) => {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
    if (e.relation in filters.relations && !filters.relations[e.relation]) return false;
    return true;
  });
  return { nodes, edges };
}

function searchGraphNodes(nodes, edges, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const relationHits = new Set();
  for (const e of edges) {
    if (e.relation.toLowerCase().includes(q)) {
      relationHits.add(e.source);
      relationHits.add(e.target);
    }
  }
  return nodes.filter((n) => {
    if (relationHits.has(n.id)) return true;
    return n.label.toLowerCase().includes(q) || n.type.toLowerCase().includes(q);
  });
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const nodes = [
  { id: "a", type: "topic", label: "Enterprise Strategy" },
  { id: "b", type: "entity", label: "Product A" },
  { id: "c", type: "entity", label: "Vietnam Market" },
  { id: "d", type: "document", label: "Annual Report 2025" },
  { id: "e", type: "concept", label: "Go-to-Market" },
];

const edges = [
  { id: "r1", source: "a", target: "b", relation: "contains" },
  { id: "r2", source: "b", target: "c", relation: "targets" },
  { id: "r3", source: "d", target: "b", relation: "supports" },
  { id: "r4", source: "a", target: "e", relation: "contains" },
];

const hop1 = computeNeighborhood(edges, "b", 1);
assert(hop1.nodeIds.has("a") && hop1.nodeIds.has("c") && hop1.nodeIds.has("d"), "depth 1 neighbors");
assert(hop1.edgeIds.has("r1") && hop1.edgeIds.has("r2") && hop1.edgeIds.has("r3"), "depth 1 edges");
assert(!hop1.nodeIds.has("e"), "depth 1 should not reach concept via a only as frontier expand once from b");

const hop2 = computeNeighborhood(edges, "b", 2);
assert(hop2.nodeIds.has("e"), "depth 2 reaches concept through topic a");

function resolveVisibleGraph(nodes, edges, opts) {
  const { selectedNodeId, depth, expandedIds } = opts;
  if (selectedNodeId) {
    const nb = computeNeighborhood(edges, selectedNodeId, depth);
    const visNodes = nodes.filter((n) => nb.nodeIds.has(n.id));
    const ids = new Set(visNodes.map((n) => n.id));
    const visEdges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes: visNodes, edges: visEdges };
  }
  if (nodes.length <= 28 && expandedIds.size === 0) return { nodes, edges };
  const keep = new Set(nodes.filter((n) => n.type === "topic").map((n) => n.id));
  for (const id of expandedIds) {
    keep.add(id);
    const nb = computeNeighborhood(edges, id, 1);
    for (const nid of nb.nodeIds) keep.add(nid);
  }
  const visNodes = nodes.filter((n) => keep.has(n.id));
  const ids = new Set(visNodes.map((n) => n.id));
  return {
    nodes: visNodes,
    edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
  };
}

const depthScoped = resolveVisibleGraph(nodes, edges, {
  selectedNodeId: "b",
  depth: 1,
  expandedIds: new Set(),
});
assert(depthScoped.nodes.every((n) => ["a", "b", "c", "d"].includes(n.id)), "depth scopes display");
assert(!depthScoped.nodes.some((n) => n.id === "e"), "depth 1 hides distant concept");

const filtered = filterGraphPayload(
  { nodes, edges },
  {
    nodeTypes: { topic: true, entity: true, document: false, concept: false },
    relations: { contains: true, targets: true, supports: true },
    viewMode: "overview",
  },
);
assert(filtered.nodes.every((n) => n.type !== "document" && n.type !== "concept"), "type filter");
assert(!filtered.edges.some((e) => e.id === "r3"), "document edge dropped");

const topicsOnly = filterGraphPayload(
  { nodes, edges },
  {
    nodeTypes: { topic: true, entity: true, document: true, concept: true },
    relations: { contains: true, targets: true, supports: true },
    viewMode: "topics",
  },
);
assert(
  topicsOnly.nodes.every((n) => n.type === "topic" || n.type === "concept"),
  "topics view mode",
);

const hits = searchGraphNodes(nodes, edges, "Product");
assert(hits.some((n) => n.id === "b"), "search by label");
const relHits = searchGraphNodes(nodes, edges, "targets");
assert(relHits.some((n) => n.id === "b") && relHits.some((n) => n.id === "c"), "search by relation");

console.log("test-graph-ui: ok");
