/**
 * =============================================================================
 * File: structuredLayout.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Deterministic hierarchical placement for a focused Knowledge Graph.
 * Responsibilities:
 *   - Place the focus node, semantic group frames, members, and overflow chips
 *   - Keep sibling nodes in compact columns and unrelated components apart
 *   - Choose edge handles that avoid cutting through columns
 * Dependencies:
 *   - graph-pipeline, graph-style, types/knowledge-graph
 * Public Exports:
 *   - layoutPreparedStructure, edgeHandlesFor
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: No physics. Same input always yields the same coordinates.
 * =============================================================================
 */

import type {
  PreparedGroup,
  PreparedStructure,
} from "@/features/graph/graph-pipeline";
import {
  GROUP_METRICS,
  NODE_METRICS,
  type NodeProminence,
} from "@/features/graph/graph-style";
import type { KnowledgeGraphLayoutMode } from "@/types/knowledge-graph";

export type Box = { x: number; y: number; w: number; h: number };

export type PlacedKnowledge = {
  kind: "knowledge";
  id: string;
  position: { x: number; y: number };
  width: number;
  height: number;
  prominence: NodeProminence;
  hop: number;
};

export type PlacedGroup = {
  kind: "group";
  id: string;
  groupKey: string;
  label: string;
  position: { x: number; y: number };
  width: number;
  height: number;
  count: number;
  hiddenCount: number;
  collapsed: boolean;
  accentType: PreparedGroup["accentType"];
};

export type PlacedOverflow = {
  kind: "overflow";
  id: string;
  groupKey: string;
  hiddenCount: number;
  position: { x: number; y: number };
  width: number;
  height: number;
};

export type PlacedComponent = {
  kind: "component";
  id: string;
  focusId: string;
  label: string;
  count: number;
  more: boolean;
  position: { x: number; y: number };
  width: number;
  height: number;
};

export type PlacedVisual =
  | PlacedKnowledge
  | PlacedGroup
  | PlacedOverflow
  | PlacedComponent;

function memberSize(hop: number): { width: number; height: number; prominence: NodeProminence } {
  if (hop <= 1) {
    return { ...NODE_METRICS.primary, prominence: "primary" };
  }
  return { ...NODE_METRICS.secondary, prominence: "secondary" };
}

function columnWidth(): number {
  return NODE_METRICS.primary.width + GROUP_METRICS.padX * 2;
}

function frameHeight(group: PreparedGroup): number {
  if (group.collapsed || group.visible.length === 0) {
    return GROUP_METRICS.padTop + GROUP_METRICS.padBottom;
  }
  let inner = 0;
  group.visible.forEach((member, index) => {
    inner += memberSize(member.hop).height;
    if (index > 0) inner += GROUP_METRICS.memberGap;
  });
  if (group.hiddenCount > 0) {
    inner += GROUP_METRICS.memberGap + GROUP_METRICS.overflowHeight;
  }
  return GROUP_METRICS.padTop + inner + GROUP_METRICS.padBottom;
}

/**
 * Highest-signal group sits under / beside the root; others alternate outward.
 */
export function orderGroupsAroundRoot(groups: PreparedGroup[]): PreparedGroup[] {
  const open = groups.filter((g) => g.members.length > 0);
  if (open.length === 0) return [];
  const ranked = [...open].sort(
    (a, b) => b.maxScore - a.maxScore || a.label.localeCompare(b.label),
  );
  const center = ranked[0];
  if (!center) return [];
  const left: PreparedGroup[] = [];
  const right: PreparedGroup[] = [];
  ranked.slice(1).forEach((group, index) => {
    if (index % 2 === 0) left.push(group);
    else right.push(group);
  });
  return [...left.reverse(), center, ...right];
}

function placeMembers(
  group: PreparedGroup,
  frame: Box,
  visuals: PlacedVisual[],
): number {
  const width = columnWidth();
  let y = frame.y + GROUP_METRICS.padTop;
  group.visible.forEach((member, index) => {
    if (index > 0) y += GROUP_METRICS.memberGap;
    const size = memberSize(member.hop);
    visuals.push({
      kind: "knowledge",
      id: member.node.id,
      position: {
        x: frame.x + (width - size.width) / 2,
        y,
      },
      width: size.width,
      height: size.height,
      prominence: size.prominence,
      hop: member.hop,
    });
    y += size.height;
  });
  if (group.hiddenCount > 0 && !group.collapsed) {
    y += GROUP_METRICS.memberGap;
    const overflowWidth = width - GROUP_METRICS.padX * 2;
    visuals.push({
      kind: "overflow",
      id: `overflow:${group.key}`,
      groupKey: group.key,
      hiddenCount: group.hiddenCount,
      position: {
        x: frame.x + GROUP_METRICS.padX,
        y,
      },
      width: overflowWidth,
      height: GROUP_METRICS.overflowHeight,
    });
    y += GROUP_METRICS.overflowHeight;
  }
  return y;
}

function placeComponents(
  structure: PreparedStructure,
  originY: number,
  visuals: PlacedVisual[],
) {
  const comps = structure.components;
  if (comps.length === 0) return;
  const gap = GROUP_METRICS.componentGap;
  const total =
    comps.length * GROUP_METRICS.componentWidth +
    Math.max(0, comps.length - 1) * gap;
  let x = -total / 2;
  for (const comp of comps) {
    visuals.push({
      kind: "component",
      id: comp.id,
      focusId: comp.focusId,
      label: comp.label,
      count: comp.count,
      more: comp.more,
      position: { x, y: originY },
      width: GROUP_METRICS.componentWidth,
      height: GROUP_METRICS.componentHeight,
    });
    x += GROUP_METRICS.componentWidth + gap;
  }
}

function pushGroup(
  group: PreparedGroup,
  x: number,
  y: number,
  visuals: PlacedVisual[],
): number {
  const width = columnWidth();
  const height = frameHeight(group);
  const frame: Box = { x, y, w: width, h: height };
  visuals.push({
    kind: "group",
    id: `group:${group.key}`,
    groupKey: group.key,
    label: group.label,
    position: { x, y },
    width,
    height,
    count: group.members.length,
    hiddenCount: group.hiddenCount,
    collapsed: group.collapsed,
    accentType: group.accentType,
  });
  if (group.collapsed) return y + height;
  return Math.max(y + height, placeMembers(group, frame, visuals));
}

function layoutRow(
  ordered: PreparedGroup[],
  originX: number,
  originY: number,
  visuals: PlacedVisual[],
): number {
  const width = columnWidth();
  let x = originX;
  let maxBottom = originY;
  for (const group of ordered) {
    maxBottom = Math.max(maxBottom, pushGroup(group, x, originY, visuals));
    x += width + GROUP_METRICS.columnGap;
  }
  return maxBottom;
}

function layoutStack(
  groups: PreparedGroup[],
  x: number,
  visuals: PlacedVisual[],
): number {
  const total = groups.reduce(
    (sum, group, index) =>
      sum + frameHeight(group) + (index > 0 ? GROUP_METRICS.memberGap : 0),
    0,
  );
  let y = -total / 2;
  let bottom = y;
  for (const group of groups) {
    bottom = Math.max(bottom, pushGroup(group, x, y, visuals));
    y += frameHeight(group) + GROUP_METRICS.memberGap;
  }
  return bottom;
}

function splitFocusSides(ordered: PreparedGroup[]): {
  left: PreparedGroup[];
  right: PreparedGroup[];
} {
  if (ordered.length === 0) return { left: [], right: [] };
  if (ordered.length === 1) return { left: [], right: [ordered[0]!] };
  const centerIndex = Math.floor((ordered.length - 1) / 2);
  const center = ordered[centerIndex];
  const rest = ordered.filter((_, index) => index !== centerIndex);
  const left: PreparedGroup[] = [];
  const right: PreparedGroup[] = [];
  rest.forEach((group, index) => {
    if (index % 2 === 0) left.push(group);
    else right.push(group);
  });
  if (center) right.unshift(center);
  return { left, right };
}

export function layoutPreparedStructure(
  structure: PreparedStructure,
  mode: Extract<KnowledgeGraphLayoutMode, "structured" | "focus">,
): PlacedVisual[] {
  const visuals: PlacedVisual[] = [];
  const focus = structure.focus;
  if (!focus) {
    placeComponents(structure, 0, visuals);
    return visuals;
  }

  const ordered = orderGroupsAroundRoot(structure.groups);
  const width = columnWidth();
  const rootW = NODE_METRICS.root.width;
  const rootH = NODE_METRICS.root.height;

  if (mode === "focus") {
    const { left, right } = splitFocusSides(ordered);
    const leftX = -(rootW / 2 + GROUP_METRICS.columnGap + width);
    const rightX = rootW / 2 + GROUP_METRICS.columnGap;
    const leftBottom = layoutStack(left, leftX, visuals);
    const rightBottom = layoutStack(right, rightX, visuals);
    visuals.push({
      kind: "knowledge",
      id: focus.id,
      position: { x: -rootW / 2, y: -rootH / 2 },
      width: rootW,
      height: rootH,
      prominence: "root",
      hop: 0,
    });
    const maxBottom = Math.max(leftBottom, rightBottom, rootH / 2);
    placeComponents(structure, maxBottom + 48, visuals);
    return visuals;
  }

  const rowWidth =
    ordered.length * width + Math.max(0, ordered.length - 1) * GROUP_METRICS.columnGap;
  const originX = -rowWidth / 2;
  visuals.push({
    kind: "knowledge",
    id: focus.id,
    position: { x: -rootW / 2, y: 0 },
    width: rootW,
    height: rootH,
    prominence: "root",
    hop: 0,
  });
  const columnsBottom = layoutRow(
    ordered,
    originX,
    rootH + GROUP_METRICS.rootGap,
    visuals,
  );
  placeComponents(structure, columnsBottom + 48, visuals);
  return visuals;
}

export function edgeHandlesFor(
  source: Box,
  target: Box,
  mode: Extract<KnowledgeGraphLayoutMode, "structured" | "focus">,
  sourceIsFocus: boolean,
  targetIsFocus: boolean,
  sameGroup: boolean,
): { sourceHandle: string; targetHandle: string } {
  if (sourceIsFocus || targetIsFocus) {
    const from = sourceIsFocus ? source : target;
    const to = sourceIsFocus ? target : source;
    const dx = to.x + to.w / 2 - (from.x + from.w / 2);
    const dy = to.y + to.h / 2 - (from.y + from.h / 2);
    const vertical = mode === "structured" || Math.abs(dy) > Math.abs(dx) * 0.75;
    if (vertical) {
      if (dy >= 0) {
        return sourceIsFocus
          ? { sourceHandle: "source-bottom", targetHandle: "target-top" }
          : { sourceHandle: "source-top", targetHandle: "target-bottom" };
      }
      return sourceIsFocus
        ? { sourceHandle: "source-top", targetHandle: "target-bottom" }
        : { sourceHandle: "source-bottom", targetHandle: "target-top" };
    }
    if (dx >= 0) {
      return sourceIsFocus
        ? { sourceHandle: "source-right", targetHandle: "target-left" }
        : { sourceHandle: "source-left", targetHandle: "target-right" };
    }
    return sourceIsFocus
      ? { sourceHandle: "source-left", targetHandle: "target-right" }
      : { sourceHandle: "source-right", targetHandle: "target-left" };
  }
  if (sameGroup) {
    if (source.y <= target.y) {
      return { sourceHandle: "source-bottom", targetHandle: "target-top" };
    }
    return { sourceHandle: "source-top", targetHandle: "target-bottom" };
  }
  // Cross-column relationships route underneath the cards.
  return { sourceHandle: "source-bottom", targetHandle: "target-bottom" };
}
