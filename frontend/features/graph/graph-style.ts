/**
 * =============================================================================
 * File: graph-style.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Restrained visual tokens for node types and selection states.
 * Responsibilities:
 *   - Map node types to Scholarly Precision accent tokens
 *   - Provide label helpers for relations / types
 * Dependencies:
 *   - types/knowledge-graph
 * Public Exports:
 *   - nodeTypeLabel, relationLabel, nodeTypeStyles
 * Database/Table: N/A
 * Related Modules: features/graph/nodes/KnowledgeNode.tsx
 * Important Notes: Keep differentiation subtle — no rainbow graph.
 * =============================================================================
 */

import type { KnowledgeGraphNodeType } from "@/types/knowledge-graph";

export type NodeVisualStyle = {
  border: string;
  borderSelected: string;
  fill: string;
  accent: string;
  chip: string;
};

export const nodeTypeStyles: Record<KnowledgeGraphNodeType, NodeVisualStyle> = {
  topic: {
    border: "border-accent-secondary/35",
    borderSelected: "border-accent-secondary",
    fill: "bg-surface",
    accent: "text-accent-secondary",
    chip: "bg-accent-secondary-soft text-accent-secondary",
  },
  entity: {
    border: "border-accent-primary/35",
    borderSelected: "border-accent-primary",
    fill: "bg-surface",
    accent: "text-accent-primary",
    chip: "bg-accent-primary-soft text-accent-primary",
  },
  document: {
    border: "border-citation/40",
    borderSelected: "border-citation",
    fill: "bg-surface",
    accent: "text-citation",
    chip: "bg-citation-soft text-citation",
  },
  concept: {
    border: "border-border-strong",
    borderSelected: "border-secondary",
    fill: "bg-surface",
    accent: "text-secondary",
    chip: "bg-elevated text-secondary",
  },
};

export function nodeTypeLabel(type: KnowledgeGraphNodeType): string {
  switch (type) {
    case "topic":
      return "Chủ đề";
    case "entity":
      return "Thực thể";
    case "document":
      return "Tài liệu";
    case "concept":
      return "Khái niệm";
    default:
      return type;
  }
}

const RELATION_LABELS: Record<string, string> = {
  supports: "Hỗ trợ",
  contains: "Chứa",
  related_to: "Liên quan",
  mentions: "Đề cập",
  depends_on: "Phụ thuộc",
  targets: "Nhắm tới",
  owns: "Sở hữu",
  manages: "Quản lý",
};

export function relationLabel(relation: string): string {
  if (RELATION_LABELS[relation]) return RELATION_LABELS[relation];
  return relation
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
