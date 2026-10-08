/**
 * =============================================================================
 * File: toFlow.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Map layout results into React Flow nodes and edges.
 * Responsibilities:
 *   - Build knowledge, group, overflow, and component nodes
 *   - Attach orthogonal handles and arrow markers for structured views
 *   - Keep explore mode on the existing layered coordinates
 * Dependencies:
 *   - @xyflow/react, graph-pipeline, structuredLayout, hierarchicalLayout
 * Public Exports:
 *   - structuredToFlow, exploreToFlow
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Does not run a physics simulation.
 * =============================================================================
 */

import { MarkerType } from "@xyflow/react";

import type { KnowledgeFlowEdge } from "@/features/graph/edges/KnowledgeEdge";
import { relationImportance } from "@/features/graph/graph-pipeline";
import type { PreparedStructure } from "@/features/graph/graph-pipeline";
import type { GraphFlowNode } from "@/features/graph/GraphCanvas";
import {
  edgeHandlesFor,
  type Box,
  type PlacedVisual,
} from "@/features/graph/layout/structuredLayout";
import type { PositionedNode } from "@/features/graph/layout/hierarchicalLayout";
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphLayoutMode,
  KnowledgeGraphNode,
} from "@/types/knowledge-graph";

type Emphasis = "selected" | "neighbor" | "match" | "dimmed" | "default";

const ARROW = {
  type: MarkerType.ArrowClosed,
  width: 16,
  height: 16,
  color: "var(--border-strong)",
} as const;

function knowledgeData(
  node: KnowledgeGraphNode,
  prominence: "root" | "primary" | "secondary",
  emphasis: Emphasis,
) {
  return {
    label: node.label,
    nodeType: node.type,
    subtype: node.subtype,
    connectionCount: node.connection_count,
    prominence,
    emphasis,
  };
}

export function structuredToFlow(
  visuals: PlacedVisual[],
  edges: KnowledgeGraphEdge[],
  structure: PreparedStructure,
  mode: Extract<KnowledgeGraphLayoutMode, "structured" | "focus">,
  emphasisFor: (nodeId: string) => Emphasis,
  edgeEmphasis: (edge: KnowledgeGraphEdge) => "path" | "selected" | "dimmed" | "default",
): { nodes: GraphFlowNode[]; edges: KnowledgeFlowEdge[] } {
  const boxes = new Map<string, Box>();
  const nodes: GraphFlowNode[] = [];

  for (const visual of visuals) {
    if (visual.kind === "knowledge") {
      boxes.set(visual.id, {
        x: visual.position.x,
        y: visual.position.y,
        w: visual.width,
        h: visual.height,
      });
      const source = structure.focus?.id === visual.id
        ? structure.focus
        : structure.groups
            .flatMap((group) => group.members)
            .find((member) => member.node.id === visual.id)?.node;
      if (!source) continue;
      nodes.push({
        id: visual.id,
        type: "knowledge",
        position: visual.position,
        width: visual.width,
        height: visual.height,
        zIndex: visual.prominence === "root" ? 3 : 2,
        draggable: true,
        selectable: true,
        data: knowledgeData(source, visual.prominence, emphasisFor(visual.id)),
      });
      continue;
    }
    if (visual.kind === "group") {
      nodes.push({
        id: visual.id,
        type: "group",
        position: visual.position,
        width: visual.width,
        height: visual.height,
        zIndex: 0,
        draggable: false,
        selectable: true,
        style: {
          width: visual.width,
          height: visual.height,
          pointerEvents: "none",
        },
        data: {
          groupKey: visual.groupKey,
          label: visual.label,
          count: visual.count,
          hiddenCount: visual.hiddenCount,
          collapsed: visual.collapsed,
          accentType: visual.accentType,
          width: visual.width,
          height: visual.height,
        },
      });
      continue;
    }
    if (visual.kind === "overflow") {
      nodes.push({
        id: visual.id,
        type: "overflow",
        position: visual.position,
        width: visual.width,
        height: visual.height,
        zIndex: 2,
        draggable: false,
        selectable: true,
        data: {
          groupKey: visual.groupKey,
          hiddenCount: visual.hiddenCount,
          width: visual.width,
          height: visual.height,
        },
      });
      continue;
    }
    nodes.push({
      id: visual.id,
      type: "component",
      position: visual.position,
      width: visual.width,
      height: visual.height,
      zIndex: 2,
      draggable: false,
      selectable: true,
      data: {
        focusId: visual.focusId,
        label: visual.label,
        count: visual.count,
        more: visual.more,
        width: visual.width,
        height: visual.height,
      },
    });
  }

  const focusId = structure.focus?.id ?? null;
  const sparse = edges.length <= 10;
  const flowEdges: KnowledgeFlowEdge[] = [];
  for (const edge of edges) {
    const source = boxes.get(edge.source);
    const target = boxes.get(edge.target);
    if (!source || !target) continue;
    const sameGroup =
      structure.groupOf.get(edge.source) !== undefined &&
      structure.groupOf.get(edge.source) === structure.groupOf.get(edge.target);
    const handles = edgeHandlesFor(
      source,
      target,
      mode,
      edge.source === focusId,
      edge.target === focusId,
      sameGroup,
    );
    const important =
      sparse &&
      relationImportance(edge.relation) >= 0.9 &&
      (edge.confidence ?? 0) >= 0.9;
    flowEdges.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: handles.sourceHandle,
      targetHandle: handles.targetHandle,
      type: "knowledge",
      markerEnd: ARROW,
      zIndex: 1,
      data: {
        relation: edge.relation,
        emphasis: edgeEmphasis(edge),
        showLabel: important,
        routing: "smoothstep",
        important,
      },
    });
  }

  return { nodes, edges: flowEdges };
}

export function exploreToFlow(
  positioned: PositionedNode[],
  edges: KnowledgeGraphEdge[],
  emphasisFor: (nodeId: string) => Emphasis,
  edgeEmphasis: (edge: KnowledgeGraphEdge) => "path" | "selected" | "dimmed" | "default",
): { nodes: GraphFlowNode[]; edges: KnowledgeFlowEdge[] } {
  const nodes: GraphFlowNode[] = positioned.map((node) => ({
    id: node.id,
    type: "knowledge" as const,
    position: node.position,
    zIndex: 2,
    draggable: true,
    data: knowledgeData(node, "primary", emphasisFor(node.id)),
  }));
  const flowEdges: KnowledgeFlowEdge[] = edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "knowledge" as const,
    markerEnd: ARROW,
    data: {
      relation: edge.relation,
      emphasis: edgeEmphasis(edge),
      showLabel: false,
      routing: "bezier" as const,
      important: false,
    },
  }));
  return { nodes, edges: flowEdges };
}
