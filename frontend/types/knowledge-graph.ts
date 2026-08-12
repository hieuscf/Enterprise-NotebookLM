/**
 * =============================================================================
 * File: knowledge-graph.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: Schema
 * Purpose: Frontend contracts for workspace-scoped Knowledge Graph exploration.
 * Responsibilities:
 *   - Define node / edge / citation / payload shapes for the graph UI
 *   - Stay independent of Neo4j / LightRAG internals
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - KnowledgeGraphNodeType, KnowledgeGraphRelationKind, CitationReference,
 *     KnowledgeGraphNode, KnowledgeGraphEdge, KnowledgeGraphPayload,
 *     KnowledgeGraphViewMode, KnowledgeGraphFilters
 * Database/Table: entities, entity_relations, topics, topic_chunks (conceptual)
 * Related Modules: features/graph/*
 * Important Notes: No dedicated OpenAPI graph-read endpoint yet — UI uses this
 *   contract with a demo adapter until the API is published.
 * =============================================================================
 */

export type KnowledgeGraphNodeType =
  | "topic"
  | "entity"
  | "document"
  | "concept";

export type KnowledgeGraphRelationKind =
  | "supports"
  | "contains"
  | "related_to"
  | "mentions"
  | "depends_on"
  | "targets"
  | "owns"
  | "manages";

export type CitationReference = {
  document_id: string;
  document_title: string;
  page_number?: number | null;
  chunk_id?: string | null;
  snippet?: string | null;
};

export type KnowledgeGraphNode = {
  id: string;
  type: KnowledgeGraphNodeType;
  label: string;
  description?: string;
  confidence?: number;
  /** Entity subtype / topic level / file type, etc. */
  subtype?: string;
  connection_count?: number;
  citations?: CitationReference[];
  metadata?: Record<string, unknown>;
};

export type KnowledgeGraphEdge = {
  id: string;
  source: string;
  target: string;
  relation: KnowledgeGraphRelationKind | string;
  confidence?: number;
  label?: string;
  citations?: CitationReference[];
  metadata?: Record<string, unknown>;
};

export type KnowledgeGraphStats = {
  entities: number;
  relationships: number;
  topics: number;
  documents: number;
  concepts: number;
};

export type KnowledgeGraphPayload = {
  workspace_id: string;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  stats: KnowledgeGraphStats;
  generated_at?: string;
};

export type KnowledgeGraphViewMode =
  | "overview"
  | "topics"
  | "entities"
  | "documents";

export type KnowledgeGraphFilters = {
  nodeTypes: Record<KnowledgeGraphNodeType, boolean>;
  relations: Record<string, boolean>;
  depth: number;
  scope: "workspace" | "all_documents";
  viewMode: KnowledgeGraphViewMode;
};

export const DEFAULT_NODE_TYPE_FILTERS: Record<KnowledgeGraphNodeType, boolean> =
  {
    topic: true,
    entity: true,
    document: true,
    concept: false,
  };

export const DEFAULT_RELATION_FILTERS: Record<string, boolean> = {
  supports: true,
  contains: true,
  related_to: true,
  mentions: true,
  depends_on: false,
  targets: true,
  owns: true,
  manages: true,
};
