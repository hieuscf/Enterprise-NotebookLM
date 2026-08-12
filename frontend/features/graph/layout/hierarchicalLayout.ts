/**
 * =============================================================================
 * File: hierarchicalLayout.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Layered hierarchical layout for Knowledge Graph nodes.
 * Responsibilities:
 *   - Assign calm top-down positions by node type + connectivity
 *   - Keep generous spacing for scholarly diagram rhythm
 * Dependencies:
 *   - types/knowledge-graph
 * Public Exports:
 *   - layoutKnowledgeGraph, NODE_WIDTH, NODE_HEIGHT
 * Database/Table: N/A
 * Related Modules: features/graph/GraphCanvas.tsx
 * Important Notes: Deterministic layout — not a physics simulation.
 * =============================================================================
 */

import type {
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphNodeType,
} from "@/types/knowledge-graph";

export const NODE_WIDTH = 168;
export const NODE_HEIGHT = 56;

const LAYER_ORDER: KnowledgeGraphNodeType[] = [
  "topic",
  "entity",
  "concept",
  "document",
];

const H_GAP = 48;
const V_GAP = 110;
const ORIGIN_X = 80;
const ORIGIN_Y = 48;

export type PositionedNode = KnowledgeGraphNode & {
  position: { x: number; y: number };
};

function layerIndex(type: KnowledgeGraphNodeType): number {
  const idx = LAYER_ORDER.indexOf(type);
  return idx >= 0 ? idx : LAYER_ORDER.length - 1;
}

/**
 * Simple layered layout: group by type, sort by degree then label, space evenly.
 * Cross-layer edges remain free (multi-parent OK).
 */
export function layoutKnowledgeGraph(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
): PositionedNode[] {
  const degree = new Map<string, number>();
  for (const n of nodes) degree.set(n.id, 0);
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }

  const layers = new Map<number, KnowledgeGraphNode[]>();
  for (const n of nodes) {
    const li = layerIndex(n.type);
    const bucket = layers.get(li) ?? [];
    bucket.push(n);
    layers.set(li, bucket);
  }

  for (const [, bucket] of layers) {
    bucket.sort((a, b) => {
      const da = degree.get(a.id) ?? 0;
      const db = degree.get(b.id) ?? 0;
      if (db !== da) return db - da;
      return a.label.localeCompare(b.label);
    });
  }

  // Prefer centering children under parent barycenters when possible.
  const parentOf = new Map<string, string[]>();
  for (const e of edges) {
    const list = parentOf.get(e.target) ?? [];
    list.push(e.source);
    parentOf.set(e.target, list);
  }

  const positions = new Map<string, { x: number; y: number }>();

  const sortedLayers = [...layers.keys()].sort((a, b) => a - b);
  for (const li of sortedLayers) {
    const bucket = layers.get(li) ?? [];
    const y = ORIGIN_Y + li * (NODE_HEIGHT + V_GAP);

    // Initial even spacing
    const rowWidth =
      bucket.length * NODE_WIDTH + Math.max(0, bucket.length - 1) * H_GAP;
    let startX = ORIGIN_X;
    // Center denser lower layers a bit
    if (bucket.length > 0) {
      const preferred = Math.max(ORIGIN_X, 120);
      startX = preferred;
    }

    bucket.forEach((n, i) => {
      const parents = parentOf.get(n.id) ?? [];
      const parentXs = parents
        .map((pid) => positions.get(pid)?.x)
        .filter((x): x is number => typeof x === "number");

      let x = startX + i * (NODE_WIDTH + H_GAP);
      if (parentXs.length > 0) {
        const avg =
          parentXs.reduce((s, v) => s + v, 0) / parentXs.length -
          NODE_WIDTH / 2;
        // Blend even index with parent barycenter for hierarchy feel
        x = avg * 0.55 + x * 0.45;
      }
      positions.set(n.id, { x, y });
    });

    // Resolve overlaps within the layer (left → right sweep)
    const ordered = [...bucket].sort(
      (a, b) => (positions.get(a.id)?.x ?? 0) - (positions.get(b.id)?.x ?? 0),
    );
    let minX = ORIGIN_X;
    for (const n of ordered) {
      const p = positions.get(n.id)!;
      if (p.x < minX) p.x = minX;
      minX = p.x + NODE_WIDTH + H_GAP;
      positions.set(n.id, p);
    }

    // Re-center the layer around ORIGIN for visual balance
    if (ordered.length > 0) {
      const first = positions.get(ordered[0].id)!.x;
      const last = positions.get(ordered[ordered.length - 1].id)!.x;
      const span = last - first + NODE_WIDTH;
      const shift = Math.max(0, (rowWidth > 0 ? 40 : 0) - first);
      // Pull left edge near ORIGIN_X when layer drifted far right
      if (first > ORIGIN_X + 200) {
        const pull = first - ORIGIN_X - 40;
        for (const n of ordered) {
          const p = positions.get(n.id)!;
          p.x -= pull;
          positions.set(n.id, p);
        }
      } else if (shift > 0 && span < 900) {
        void span;
      }
    }
  }

  return nodes.map((n) => ({
    ...n,
    position: positions.get(n.id) ?? { x: ORIGIN_X, y: ORIGIN_Y },
  }));
}
