/**
 * =============================================================================
 * File: test-graph-layout.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Check focus selection, grouping, disclosure, and structured placement.
 * Responsibilities:
 *   - Assert small, medium, large, dense, and disconnected graphs stay readable
 *   - Confirm layout is deterministic and does not invent relationships
 * Dependencies:
 *   - graph-pipeline, structuredLayout
 * Public Exports:
 *   - N/A (script)
 * Database/Table: N/A
 * Related Modules: features/graph/graph-pipeline.ts
 * Important Notes: Run via the frontend test script. Presentation logic only.
 * =============================================================================
 */

import { buildDemoKnowledgeGraph } from "../features/graph/data/demo-graph";
import {
  GROUP_PAGE,
  MAX_OPEN_GROUPS,
  pickCentralNode,
  prepareKnowledgeStructure,
  selectDisplayEdges,
  semanticGroupKey,
} from "../features/graph/graph-pipeline";
import { layoutPreparedStructure } from "../features/graph/layout/structuredLayout";
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphNodeType,
} from "../types/knowledge-graph";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

function node(
  id: string,
  type: KnowledgeGraphNodeType,
  label: string,
  subtype?: string,
  confidence = 0.8,
): KnowledgeGraphNode {
  return {
    id,
    type,
    label,
    subtype,
    confidence,
    connection_count: 0,
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  relation = "related_to",
  confidence = 0.6,
): KnowledgeGraphEdge {
  return { id, source, target, relation, confidence };
}

function chainGraph(count: number, extraEdges = 0) {
  const types: KnowledgeGraphNodeType[] = ["topic", "entity", "document", "concept"];
  const subtypes = ["Person", "Organization", "Project", "Product", "Concept"];
  const nodes: KnowledgeGraphNode[] = [];
  const edges: KnowledgeGraphEdge[] = [];
  for (let i = 0; i < count; i += 1) {
    const type = types[i % types.length] ?? "entity";
    const subtype = type === "entity" ? subtypes[i % subtypes.length] : type;
    nodes.push(
      node(
        `n${i}`,
        type,
        i === 3 ? "A very long entity name that should stay inside its card" : `Node ${i}`,
        subtype,
        0.5 + (i % 5) * 0.1,
      ),
    );
    if (i > 0) {
      edges.push(edge(`e${i}`, "n0", `n${i}`, i % 2 === 0 ? "contains" : "mentions", 0.7));
    }
  }
  for (let i = 0; i < extraEdges; i += 1) {
    const a = 1 + (i % Math.max(1, count - 1));
    const b = 1 + ((i * 3) % Math.max(1, count - 1));
    if (a === b) continue;
    edges.push(edge(`x${i}`, `n${a}`, `n${b}`, "related_to", 0.4));
  }
  return { nodes, edges };
}

function boxesOverlap(
  a: { x: number; y: number; w: number; h: number },
  b: { x: number; y: number; w: number; h: number },
  gap = 2,
) {
  return (
    a.x < b.x + b.w + gap &&
    a.x + a.w + gap > b.x &&
    a.y < b.y + b.h + gap &&
    a.y + a.h + gap > b.y
  );
}

function layoutOf(nodes: KnowledgeGraphNode[], edges: KnowledgeGraphEdge[], depth = 2) {
  const structure = prepareKnowledgeStructure(nodes, edges, {
    explicitFocusId: null,
    openedNodeId: null,
    depth,
    expandedIds: new Set(),
    groupOverrides: {},
    groupReveal: {},
    showAllComponents: false,
  });
  const visuals = layoutPreparedStructure(structure, "structured");
  return { structure, visuals };
}

const centralNodes = [
  node("root", "topic", "Enterprise Strategy", "Root topic", 0.9),
  node("leaf", "entity", "Alice", "Person", 0.4),
];
const centralEdges = [edge("r", "root", "leaf", "contains", 0.9)];
assert(pickCentralNode(centralNodes, centralEdges) === "root", "central node prefers root topic");

const depthNodes = [
  node("a", "topic", "Root", "Root topic"),
  node("b", "entity", "Alice", "Person"),
  node("c", "concept", "RAG", "Concept"),
];
const depthEdges = [
  edge("ab", "a", "b", "contains", 0.9),
  edge("bc", "b", "c", "mentions", 0.5),
];
const hop1 = prepareKnowledgeStructure(depthNodes, depthEdges, {
  explicitFocusId: "a",
  openedNodeId: null,
  depth: 1,
  expandedIds: new Set(),
  groupOverrides: {},
  groupReveal: {},
  showAllComponents: false,
});
const hop1Ids = new Set(hop1.groups.flatMap((group) => group.members.map((m) => m.node.id)));
assert(hop1Ids.has("b") && !hop1Ids.has("c"), "depth 1 stops at direct neighbors");
const hop2 = prepareKnowledgeStructure(depthNodes, depthEdges, {
  explicitFocusId: "a",
  openedNodeId: null,
  depth: 2,
  expandedIds: new Set(),
  groupOverrides: {},
  groupReveal: {},
  showAllComponents: false,
});
const hop2Ids = new Set(hop2.groups.flatMap((group) => group.members.map((m) => m.node.id)));
assert(hop2Ids.has("c"), "depth 2 reaches the next hop");
assert(semanticGroupKey(depthNodes[1]!) === "entity:Person", "entities group by subtype");

const wide = chainGraph(40, 0);
const wideView = layoutOf(wide.nodes, wide.edges, 2);
for (const group of wideView.structure.groups) {
  if (!group.collapsed) {
    assert(
      group.visible.length <= GROUP_PAGE,
      `group ${group.label} shows at most ${GROUP_PAGE} nodes`,
    );
  }
}
const openGroups = wideView.structure.groups.filter((group) => !group.collapsed);
assert(openGroups.length <= MAX_OPEN_GROUPS, "open groups stay bounded");

const revealed = prepareKnowledgeStructure(wide.nodes, wide.edges, {
  explicitFocusId: "n0",
  openedNodeId: null,
  depth: 2,
  expandedIds: new Set(),
  groupOverrides: {},
  groupReveal: { [wideView.structure.groups[0]?.key ?? "topic"]: GROUP_PAGE },
  showAllComponents: false,
});
const first = revealed.groups.find((group) => group.key === wideView.structure.groups[0]?.key);
assert((first?.visible.length ?? 0) > (wideView.structure.groups[0]?.visible.length ?? 0) || (first?.members.length ?? 0) <= GROUP_PAGE, "reveal adds another page when the group has more members");

const island = node("z", "document", "Orphan.pdf", "PDF");
const withIsland = layoutOf([...wide.nodes, island], wide.edges, 2);
assert(
  withIsland.structure.components.some((comp) => comp.focusId === "z"),
  "disconnected node becomes a collapsed component",
);
assert(
  !withIsland.structure.candidateEdges.some((item) => item.source === "z" || item.target === "z"),
  "no fabricated edge to a disconnected node",
);

function assertReadable(label: string, count: number, extraEdges: number) {
  const graph = chainGraph(count, extraEdges);
  const placed = layoutOf(graph.nodes, graph.edges, 2);
  const again = layoutOf(graph.nodes, graph.edges, 2);
  const knowledge = placed.visuals.filter((item) => item.kind === "knowledge");
  assert(knowledge.length > 0, `${label}: has a focus`);
  assert(knowledge.some((item) => item.kind === "knowledge" && item.prominence === "root"), `${label}: root is marked`);
  assert(knowledge.length <= 1 + MAX_OPEN_GROUPS * GROUP_PAGE + 8, `${label}: default view stays bounded`);
  for (let i = 0; i < knowledge.length; i += 1) {
    for (let j = i + 1; j < knowledge.length; j += 1) {
      const a = knowledge[i]!;
      const b = knowledge[j]!;
      const overlap = boxesOverlap(
        { x: a.position.x, y: a.position.y, w: a.width, h: a.height },
        { x: b.position.x, y: b.position.y, w: b.width, h: b.height },
      );
      assert(!overlap, `${label}: nodes ${a.id} and ${b.id} overlap`);
    }
  }
  const signature = placed.visuals.map((item) => `${item.kind}:${item.id}:${item.position.x}:${item.position.y}`).join("|");
  const signature2 = again.visuals.map((item) => `${item.kind}:${item.id}:${item.position.x}:${item.position.y}`).join("|");
  assert(signature === signature2, `${label}: layout is deterministic`);
  const long = knowledge.find((item) => item.kind === "knowledge" && item.id === "n3");
  if (long && long.kind === "knowledge") {
    assert(long.width <= 200, `${label}: long names do not stretch the card`);
  }
}

assertReadable("5 nodes", 5, 0);
assertReadable("20 nodes", 20, 10);
assertReadable("50 nodes", 50, 40);
assertReadable("100 nodes", 100, 80);

const dense = chainGraph(18, 40);
const denseStructure = prepareKnowledgeStructure(dense.nodes, dense.edges, {
  explicitFocusId: "n0",
  openedNodeId: null,
  depth: 2,
  expandedIds: new Set(),
  groupOverrides: {},
  groupReveal: {},
  showAllComponents: true,
});
const primary = selectDisplayEdges(denseStructure, false);
const all = selectDisplayEdges(denseStructure, true);
assert(all.edges.length >= primary.edges.length, "show-all includes the primary edges");
assert(all.hiddenCount === 0, "show-all hides nothing");
if (denseStructure.candidateEdges.length > 16) {
  assert(primary.hiddenCount > 0, "dense graphs hide low-value edges until requested");
}

const people = [node("hub", "topic", "Directory", "Root topic", 0.99)];
const peopleEdges: KnowledgeGraphEdge[] = [];
for (let i = 0; i < 12; i += 1) {
  people.push(node(`p${i}`, "entity", `Person ${i}`, "Person", 0.55));
  peopleEdges.push(edge(`pe${i}`, "hub", `p${i}`, "contains", 0.85));
}
const peopleOpts = {
  explicitFocusId: "hub",
  openedNodeId: null,
  depth: 1 as const,
  expandedIds: new Set<string>(),
  groupOverrides: {},
  showAllComponents: false,
};
const peoplePage = prepareKnowledgeStructure(people, peopleEdges, {
  ...peopleOpts,
  groupReveal: {},
});
const personGroup = peoplePage.groups.find((group) => group.key === "entity:Person");
assert(personGroup?.visible.length === GROUP_PAGE, "person group starts with one page");
assert(personGroup?.hiddenCount === 7, "remaining people stay hidden");
const peopleMore = prepareKnowledgeStructure(people, peopleEdges, {
  ...peopleOpts,
  groupReveal: { "entity:Person": GROUP_PAGE },
});
assert(
  peopleMore.groups.find((group) => group.key === "entity:Person")?.visible.length === 10,
  "expanding a group reveals the next page",
);

const demo = buildDemoKnowledgeGraph("ws-demo");
const demoView = layoutOf(demo.nodes, demo.edges, 2);
assert(demoView.structure.focus?.id === "t-enterprise", "demo graph focuses the root topic");
const demoNodes = demoView.visuals.filter((item) => item.kind === "knowledge");
for (let i = 0; i < demoNodes.length; i += 1) {
  for (let j = i + 1; j < demoNodes.length; j += 1) {
    const a = demoNodes[i]!;
    const b = demoNodes[j]!;
    assert(
      !boxesOverlap(
        { x: a.position.x, y: a.position.y, w: a.width, h: a.height },
        { x: b.position.x, y: b.position.y, w: b.width, h: b.height },
      ),
      `demo overlap ${a.id} ${b.id}`,
    );
  }
}
const demoKeys = new Set(demoView.structure.groups.map((group) => group.key));
assert(demoKeys.has("topic"), "demo keeps sibling topics in a topic group");
assert(demoKeys.has("entity:Product"), "demo groups products by subtype");
assert(demoKeys.has("document"), "demo groups supporting documents together");
assert(!demoKeys.has("entity:Person"), "depth 2 does not pull in people three hops away");

const focusLayout = layoutPreparedStructure(denseStructure, "focus");
const focusNodes = focusLayout.filter((item) => item.kind === "knowledge");
for (let i = 0; i < focusNodes.length; i += 1) {
  for (let j = i + 1; j < focusNodes.length; j += 1) {
    const a = focusNodes[i]!;
    const b = focusNodes[j]!;
    assert(
      !boxesOverlap(
        { x: a.position.x, y: a.position.y, w: a.width, h: a.height },
        { x: b.position.x, y: b.position.y, w: b.width, h: b.height },
      ),
      `focus layout overlap ${a.id} ${b.id}`,
    );
  }
}

console.log("test-graph-layout: ok");
