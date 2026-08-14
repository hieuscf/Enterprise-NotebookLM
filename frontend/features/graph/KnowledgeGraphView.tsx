/**
 * =============================================================================
 * File: KnowledgeGraphView.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Full Knowledge Graph exploration workspace for a single Workspace.
 * Responsibilities:
 *   - Load workspace-scoped graph data; compose filters / canvas / inspectors
 *   - Path highlighting, search, keyboard shortcuts, responsive drawers
 * Dependencies:
 *   - AppShell, GraphCanvas, GraphFilters, GraphSearch, inspectors, graph.api
 * Public Exports:
 *   - KnowledgeGraphView
 * Database/Table: entities, entity_relations, topics (via graph.api)
 * Related Modules: app/workspaces/[id]/graph/page.tsx
 * Important Notes: Always scoped by workspaceId; never mix workspaces.
 * =============================================================================
 */

"use client";

import { PanelLeft, PanelRight, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  GraphEmptyState,
  GraphErrorState,
  GraphLoadingState,
} from "@/features/graph/GraphEmptyState";
import {
  GraphCanvas,
  type GraphCanvasHandle,
} from "@/features/graph/GraphCanvas";
import { GraphFilters } from "@/features/graph/GraphFilters";
import { GraphSearch } from "@/features/graph/GraphSearch";
import { GraphStatusBar } from "@/features/graph/GraphStatusBar";
import { fetchKnowledgeGraph } from "@/features/graph/graph.api";
import { relationLabel } from "@/features/graph/graph-style";
import {
  computeNeighborhood,
  filterGraphPayload,
  resolveVisibleGraph,
  searchGraphNodes,
} from "@/features/graph/graph-selection";
import { layoutKnowledgeGraph } from "@/features/graph/layout/hierarchicalLayout";
import { NodeInspector } from "@/features/graph/NodeInspector";
import { RelationshipInspector } from "@/features/graph/RelationshipInspector";
import type { KnowledgeFlowEdge } from "@/features/graph/edges/KnowledgeEdge";
import type { KnowledgeFlowNode } from "@/features/graph/nodes/KnowledgeNode";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import {
  DEFAULT_NODE_TYPE_FILTERS,
  DEFAULT_RELATION_FILTERS,
  type KnowledgeGraphEdge,
  type KnowledgeGraphFilters,
  type KnowledgeGraphNode,
  type KnowledgeGraphPayload,
} from "@/types/knowledge-graph";

type Props = {
  workspaceId: string;
};

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; payload: KnowledgeGraphPayload; source: "api" | "demo" };

function emphasisForNode(
  nodeId: string,
  selectedNodeId: string | null,
  neighborhood: ReturnType<typeof computeNeighborhood>,
  matchIds: Set<string>,
): NonNullable<KnowledgeFlowNode["data"]>["emphasis"] {
  if (selectedNodeId) {
    if (nodeId === selectedNodeId) return "selected";
    if (neighborhood.nodeIds.has(nodeId)) return "neighbor";
    return "dimmed";
  }
  if (matchIds.size > 0) {
    return matchIds.has(nodeId) ? "match" : "dimmed";
  }
  return "default";
}

function emphasisForEdge(
  edge: KnowledgeGraphEdge,
  selectedNodeId: string | null,
  selectedEdgeId: string | null,
  neighborhood: ReturnType<typeof computeNeighborhood>,
  matchIds: Set<string>,
): NonNullable<KnowledgeFlowEdge["data"]>["emphasis"] {
  if (selectedEdgeId && edge.id === selectedEdgeId) return "selected";
  if (selectedNodeId) {
    return neighborhood.edgeIds.has(edge.id) ? "path" : "dimmed";
  }
  if (matchIds.size > 0) {
    if (matchIds.has(edge.source) && matchIds.has(edge.target)) return "path";
    if (matchIds.has(edge.source) || matchIds.has(edge.target)) return "default";
    return "dimmed";
  }
  return "default";
}

export function KnowledgeGraphView({ workspaceId }: Props) {
  const { user } = useAuth();
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [filters, setFilters] = useState<KnowledgeGraphFilters>({
    nodeTypes: { ...DEFAULT_NODE_TYPE_FILTERS },
    relations: { ...DEFAULT_RELATION_FILTERS },
    depth: 2,
    scope: "workspace",
    viewMode: "overview",
  });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showLabels, setShowLabels] = useState(false);
  const [showRelations, setShowRelations] = useState(true);
  const [layoutSeed, setLayoutSeed] = useState(0);
  const [flowNodes, setFlowNodes] = useState<KnowledgeFlowNode[]>([]);
  const [flowEdges, setFlowEdges] = useState<KnowledgeFlowEdge[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  const reload = useCallback(() => {
    setLoadState({ status: "loading" });
    let cancelled = false;
    fetchKnowledgeGraph(workspaceId)
      .then(({ data, source }) => {
        if (cancelled) return;
        setLoadState({ status: "ready", payload: data, source });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Không thể tải đồ thị tri thức.";
        setLoadState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  useEffect(() => {
    const cancel = reload();
    return cancel;
  }, [reload]);

  const payload =
    loadState.status === "ready" ? loadState.payload : null;
  const dataSource =
    loadState.status === "ready" ? loadState.source : undefined;

  const filtered = useMemo(() => {
    if (!payload) return { nodes: [] as KnowledgeGraphNode[], edges: [] as KnowledgeGraphEdge[] };
    return filterGraphPayload(payload, filters);
  }, [payload, filters]);

  const visible = useMemo(
    () =>
      resolveVisibleGraph(filtered.nodes, filtered.edges, {
        selectedNodeId,
        depth: filters.depth,
        expandedIds,
      }),
    [filtered.nodes, filtered.edges, selectedNodeId, filters.depth, expandedIds],
  );

  const nodesById = useMemo(() => {
    const map = new Map<string, KnowledgeGraphNode>();
    for (const n of filtered.nodes) map.set(n.id, n);
    return map;
  }, [filtered.nodes]);

  const searchResults = useMemo(
    () => searchGraphNodes(filtered.nodes, filtered.edges, query),
    [filtered.nodes, filtered.edges, query],
  );

  const matchIds = useMemo(
    () => new Set(query.trim() ? searchResults.map((n) => n.id) : []),
    [query, searchResults],
  );

  // Layout when visible set / seed changes (preserve drag positions otherwise)
  useEffect(() => {
    if (!payload) {
      setFlowNodes([]);
      setFlowEdges([]);
      return;
    }
    const neighborhood = computeNeighborhood(
      visible.edges,
      selectedNodeId,
      filters.depth,
    );
    const positioned = layoutKnowledgeGraph(visible.nodes, visible.edges);
    setFlowNodes(
      positioned.map((n) => ({
        id: n.id,
        type: "knowledge" as const,
        position: n.position,
        selected: n.id === selectedNodeId,
        data: {
          label: n.label,
          nodeType: n.type,
          subtype: n.subtype,
          connectionCount: n.connection_count,
          emphasis: emphasisForNode(n.id, selectedNodeId, neighborhood, matchIds),
        },
      })),
    );
    setFlowEdges(
      visible.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: "knowledge" as const,
        selected: e.id === selectedEdgeId,
        data: {
          relation: e.relation,
          emphasis: emphasisForEdge(
            e,
            selectedNodeId,
            selectedEdgeId,
            neighborhood,
            matchIds,
          ),
          showLabel: false,
        },
      })),
    );
    // Intentionally omit selection from deps for layout — handled below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, visible.nodes, visible.edges, layoutSeed]);

  // Update emphasis / selection without recomputing layout
  useEffect(() => {
    const neighborhood = computeNeighborhood(
      visible.edges,
      selectedNodeId,
      filters.depth,
    );
    setFlowNodes((prev) =>
      prev.map((n) => ({
        ...n,
        selected: n.id === selectedNodeId,
        data: {
          ...n.data,
          emphasis: emphasisForNode(
            n.id,
            selectedNodeId,
            neighborhood,
            matchIds,
          ),
        },
      })),
    );
    setFlowEdges((prev) =>
      prev.map((e) => {
        const src = visible.edges.find((x) => x.id === e.id);
        if (!src) return e;
        return {
          ...e,
          selected: e.id === selectedEdgeId,
          data: {
            ...e.data!,
            emphasis: emphasisForEdge(
              src,
              selectedNodeId,
              selectedEdgeId,
              neighborhood,
              matchIds,
            ),
          },
        };
      }),
    );
  }, [
    selectedNodeId,
    selectedEdgeId,
    matchIds,
    filters.depth,
    visible.edges,
  ]);

  const selectedNode = selectedNodeId
    ? nodesById.get(selectedNodeId) ?? null
    : null;
  const selectedEdge = selectedEdgeId
    ? filtered.edges.find((e) => e.id === selectedEdgeId) ?? null
    : null;

  const pathLabel = useMemo(() => {
    if (selectedNode) return selectedNode.label;
    if (selectedEdge) {
      const s = nodesById.get(selectedEdge.source)?.label ?? selectedEdge.source;
      const t = nodesById.get(selectedEdge.target)?.label ?? selectedEdge.target;
      return `${s} → ${relationLabel(selectedEdge.relation)} → ${t}`;
    }
    return null;
  }, [selectedNode, selectedEdge, nodesById]);

  const selectNode = useCallback(
    (nodeId: string | null) => {
      setSelectedNodeId(nodeId);
      setSelectedEdgeId(null);
      if (nodeId) setInspectorOpen(true);
    },
    [],
  );

  const selectEdge = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
    setSelectedNodeId(null);
    if (edgeId) setInspectorOpen(true);
  }, []);

  const centerOnNode = useCallback((nodeId: string) => {
    selectNode(nodeId);
    requestAnimationFrame(() => canvasRef.current?.centerNode(nodeId));
  }, [selectNode]);

  const expandNode = useCallback((nodeId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.add(nodeId);
      return next;
    });
    selectNode(nodeId);
    requestAnimationFrame(() => canvasRef.current?.centerNode(nodeId));
  }, [selectNode]);

  const collapseCluster = useCallback(() => {
    setExpandedIds(new Set());
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setLayoutSeed((s) => s + 1);
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing) return;

      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        canvasRef.current?.zoomIn();
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        canvasRef.current?.zoomOut();
      } else if (e.key === "0") {
        e.preventDefault();
        canvasRef.current?.fitView();
      } else if (e.key === "Escape") {
        setSelectedNodeId(null);
        setSelectedEdgeId(null);
        setQuery("");
        setFiltersOpen(false);
        setInspectorOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const stats = payload?.stats ?? {
    entities: 0,
    relationships: 0,
    topics: 0,
    documents: 0,
    concepts: 0,
  };

  const isEmpty =
    loadState.status === "ready" &&
    payload !== null &&
    payload.nodes.length === 0;

  return (
    <AppShell active="graph" user={user} workspaceId={workspaceId}>
      <div className="flex h-full min-h-0 flex-1 flex-col bg-base">
        {/* Context + search */}
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border-default bg-surface px-4 py-2.5 sm:px-5">
          <div className="min-w-0 flex-1">
            <nav
              aria-label="Đường dẫn"
              className="flex flex-wrap items-center gap-1.5 text-caption text-tertiary"
            >
              <Link
                href={`/workspaces/${workspaceId}`}
                className="hover:text-secondary"
              >
                Workspace
              </Link>
              <span aria-hidden>/</span>
              <span className="text-secondary">Tri thức</span>
              <span aria-hidden>/</span>
              <span className="font-medium text-primary">Đồ thị tri thức</span>
            </nav>
            <p className="mt-0.5 text-[11px] font-medium text-accent-secondary">
              LightRAG · Thực thể · Quan hệ · Nguồn
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-md border border-border-default text-secondary hover:bg-elevated lg:hidden"
              aria-label="Mở bộ lọc"
              onClick={() => setFiltersOpen(true)}
            >
              <PanelLeft className="h-4 w-4" aria-hidden />
            </button>
            <GraphSearch
              ref={searchRef}
              query={query}
              results={searchResults}
              onQueryChange={setQuery}
              onSelectResult={centerOnNode}
              className="w-[min(100vw-8rem,22rem)]"
            />
            <button
              type="button"
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-md border border-border-default text-secondary hover:bg-elevated lg:hidden"
              aria-label="Mở chi tiết"
              onClick={() => setInspectorOpen(true)}
            >
              <PanelRight className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>

        {/* Main 3-pane */}
        <div className="relative flex min-h-0 flex-1">
          {/* Desktop filters */}
          <div className="hidden w-[220px] shrink-0 lg:block">
            <GraphFilters filters={filters} onChange={setFilters} />
          </div>

          {/* Canvas */}
          <div className="relative min-w-0 flex-1">
            {loadState.status === "loading" ? (
              <GraphLoadingState />
            ) : loadState.status === "error" ? (
              <GraphErrorState
                message={loadState.message}
                onRetry={() => {
                  reload();
                }}
              />
            ) : isEmpty ? (
              <GraphEmptyState workspaceId={workspaceId} />
            ) : (
              <GraphCanvas
                ref={canvasRef}
                nodes={flowNodes}
                edges={flowEdges}
                onNodesChange={setFlowNodes}
                onEdgesChange={setFlowEdges}
                onSelectNode={selectNode}
                onSelectEdge={selectEdge}
                onNodeDoubleClick={expandNode}
                onResetLayout={() => {
                  collapseCluster();
                  setLayoutSeed((s) => s + 1);
                }}
                showLabels={showLabels}
                showRelations={showRelations}
                onToggleLabels={() => setShowLabels((v) => !v)}
                onToggleRelations={() => setShowRelations((v) => !v)}
              />
            )}
          </div>

          {/* Desktop inspector */}
          <div className="hidden w-[280px] shrink-0 xl:block">
            {selectedEdge ? (
              <RelationshipInspector
                workspaceId={workspaceId}
                edge={selectedEdge}
                sourceNode={nodesById.get(selectedEdge.source) ?? null}
                targetNode={nodesById.get(selectedEdge.target) ?? null}
                onSelectNode={centerOnNode}
              />
            ) : (
              <NodeInspector
                workspaceId={workspaceId}
                node={selectedNode}
                edges={filtered.edges}
                nodesById={nodesById}
                onSelectConnected={centerOnNode}
              />
            )}
          </div>

          {/* Tablet/mobile filters drawer */}
          {filtersOpen ? (
            <div className="absolute inset-0 z-30 flex lg:hidden">
              <button
                type="button"
                className="absolute inset-0 cursor-pointer bg-slate-950/30"
                aria-label="Đóng bộ lọc"
                onClick={() => setFiltersOpen(false)}
              />
              <div className="relative z-10 flex h-full w-[min(100%,260px)] flex-col bg-surface shadow-lg">
                <div className="flex items-center justify-between border-b border-border-default px-3 py-2">
                  <p className="text-body-sm font-medium text-primary">Điều khiển</p>
                  <button
                    type="button"
                    onClick={() => setFiltersOpen(false)}
                    className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-secondary hover:bg-elevated"
                    aria-label="Đóng"
                  >
                    <X className="h-4 w-4" aria-hidden />
                  </button>
                </div>
                <GraphFilters
                  filters={filters}
                  onChange={setFilters}
                  className="border-r-0"
                />
              </div>
            </div>
          ) : null}

          {/* Tablet/mobile inspector sheet */}
          {inspectorOpen ? (
            <div className="absolute inset-0 z-30 flex justify-end xl:hidden">
              <button
                type="button"
                className="absolute inset-0 cursor-pointer bg-slate-950/30"
                aria-label="Đóng chi tiết"
                onClick={() => setInspectorOpen(false)}
              />
              <div
                className={cn(
                  "relative z-10 flex h-full w-[min(100%,320px)] flex-col bg-surface shadow-lg",
                  "max-md:mt-auto max-md:h-[min(72vh,560px)] max-md:w-full max-md:rounded-t-xl",
                )}
              >
                <div className="flex items-center justify-between border-b border-border-default px-3 py-2">
                  <p className="text-body-sm font-medium text-primary">Chi tiết</p>
                  <button
                    type="button"
                    onClick={() => setInspectorOpen(false)}
                    className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-secondary hover:bg-elevated"
                    aria-label="Đóng"
                  >
                    <X className="h-4 w-4" aria-hidden />
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-hidden">
                  {selectedEdge ? (
                    <RelationshipInspector
                      workspaceId={workspaceId}
                      edge={selectedEdge}
                      sourceNode={nodesById.get(selectedEdge.source) ?? null}
                      targetNode={nodesById.get(selectedEdge.target) ?? null}
                      onSelectNode={centerOnNode}
                      className="border-l-0"
                    />
                  ) : (
                    <NodeInspector
                      workspaceId={workspaceId}
                      node={selectedNode}
                      edges={filtered.edges}
                      nodesById={nodesById}
                      onSelectConnected={centerOnNode}
                      className="border-l-0"
                    />
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <GraphStatusBar
          stats={stats}
          selectedPathLabel={pathLabel}
          dataSource={dataSource}
        />
      </div>
    </AppShell>
  );
}
