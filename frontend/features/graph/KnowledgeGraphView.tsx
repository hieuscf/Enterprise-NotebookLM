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

import { PanelLeft, PanelRight, Sparkles, X } from "lucide-react";
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
  type GraphFlowNode,
} from "@/features/graph/GraphCanvas";
import { GraphFilters } from "@/features/graph/GraphFilters";
import { GraphSearch } from "@/features/graph/GraphSearch";
import { GraphStatusBar } from "@/features/graph/GraphStatusBar";
import { fetchKnowledgeGraph } from "@/features/graph/graph.api";
import {
  GROUP_PAGE,
  prepareKnowledgeStructure,
  resolveOpenedNodeId,
  selectDisplayEdges,
  type GroupOverride,
} from "@/features/graph/graph-pipeline";
import { relationLabel } from "@/features/graph/graph-style";
import {
  computeNeighborhood,
  filterGraphPayload,
  resolveVisibleGraph,
  searchGraphNodes,
} from "@/features/graph/graph-selection";
import { layoutKnowledgeGraph } from "@/features/graph/layout/hierarchicalLayout";
import { layoutPreparedStructure } from "@/features/graph/layout/structuredLayout";
import { exploreToFlow, structuredToFlow } from "@/features/graph/layout/toFlow";
import { NodeInspector } from "@/features/graph/NodeInspector";
import { RelationshipInspector } from "@/features/graph/RelationshipInspector";
import type { KnowledgeFlowEdge } from "@/features/graph/edges/KnowledgeEdge";
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
  /** Document the user had open before navigating here. */
  openedDocumentId?: string | null;
  /** Explicit node id from a deep link. */
  openedNodeId?: string | null;
};

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; payload: KnowledgeGraphPayload; source: "api" | "demo" };

function emphasisForNode(
  nodeId: string,
  focusId: string | null,
  hoverId: string | null,
  edges: KnowledgeGraphEdge[],
  matchIds: Set<string>,
): "selected" | "neighbor" | "match" | "dimmed" | "default" {
  if (hoverId) {
    const neighborhood = computeNeighborhood(edges, hoverId, 1);
    if (nodeId === hoverId) return "selected";
    if (neighborhood.nodeIds.has(nodeId)) return "neighbor";
    return "dimmed";
  }
  if (matchIds.size > 0) {
    return matchIds.has(nodeId) ? "match" : "dimmed";
  }
  if (focusId && nodeId === focusId) return "selected";
  return "default";
}

function emphasisForEdge(
  edge: KnowledgeGraphEdge,
  hoverId: string | null,
  selectedEdgeId: string | null,
  edges: KnowledgeGraphEdge[],
): NonNullable<KnowledgeFlowEdge["data"]>["emphasis"] {
  if (selectedEdgeId && edge.id === selectedEdgeId) return "selected";
  if (hoverId) {
    const neighborhood = computeNeighborhood(edges, hoverId, 1);
    return neighborhood.edgeIds.has(edge.id) ? "path" : "dimmed";
  }
  return "default";
}

export function KnowledgeGraphView({
  workspaceId,
  openedDocumentId = null,
  openedNodeId = null,
}: Props) {
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
    layoutMode: "structured",
  });
  const [explicitFocusId, setExplicitFocusId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showLabels, setShowLabels] = useState(false);
  const [showRelations, setShowRelations] = useState(true);
  const [showAllEdges, setShowAllEdges] = useState(false);
  const [layoutSeed, setLayoutSeed] = useState(0);
  const [flowNodes, setFlowNodes] = useState<GraphFlowNode[]>([]);
  const [flowEdges, setFlowEdges] = useState<KnowledgeFlowEdge[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [groupOverrides, setGroupOverrides] = useState<
    Record<string, GroupOverride>
  >({});
  const [groupReveal, setGroupReveal] = useState<Record<string, number>>({});
  const [showAllComponents, setShowAllComponents] = useState(false);

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

  const nodesById = useMemo(() => {
    const map = new Map<string, KnowledgeGraphNode>();
    for (const n of filtered.nodes) map.set(n.id, n);
    return map;
  }, [filtered.nodes]);

  const openedResolved = useMemo(
    () =>
      resolveOpenedNodeId(
        filtered.nodes,
        openedNodeId,
        openedDocumentId,
      ),
    [filtered.nodes, openedNodeId, openedDocumentId],
  );

  const structured = filters.layoutMode !== "explore";

  const structure = useMemo(() => {
    if (!structured) return null;
    return prepareKnowledgeStructure(filtered.nodes, filtered.edges, {
      explicitFocusId,
      openedNodeId: openedResolved,
      depth: filters.depth,
      expandedIds,
      groupOverrides,
      groupReveal,
      showAllComponents,
    });
  }, [
    structured,
    filtered.nodes,
    filtered.edges,
    explicitFocusId,
    openedResolved,
    filters.depth,
    expandedIds,
    groupOverrides,
    groupReveal,
    showAllComponents,
  ]);

  const visuals = useMemo(() => {
    if (!structure || filters.layoutMode === "explore") return [];
    return layoutPreparedStructure(structure, filters.layoutMode);
  }, [structure, filters.layoutMode]);

  const edgePick = useMemo(() => {
    if (!structure) return { edges: [] as KnowledgeGraphEdge[], hiddenCount: 0 };
    return selectDisplayEdges(structure, showAllEdges || filters.layoutMode === "explore");
  }, [structure, showAllEdges, filters.layoutMode]);

  const exploreVisible = useMemo(() => {
    if (structured) return null;
    return resolveVisibleGraph(filtered.nodes, filtered.edges, {
      selectedNodeId: explicitFocusId,
      depth: filters.depth,
      expandedIds,
    });
  }, [
    structured,
    filtered.nodes,
    filtered.edges,
    explicitFocusId,
    filters.depth,
    expandedIds,
  ]);

  const focusId = structured
    ? structure?.focus?.id ?? null
    : explicitFocusId ?? openedResolved;

  const searchResults = useMemo(
    () => searchGraphNodes(filtered.nodes, filtered.edges, query),
    [filtered.nodes, filtered.edges, query],
  );

  const matchIds = useMemo(
    () => new Set(query.trim() ? searchResults.map((n) => n.id) : []),
    [query, searchResults],
  );

  const emphasisEdges = structured ? edgePick.edges : exploreVisible?.edges ?? [];

  const nodeModel = useMemo(() => {
    if (!payload) return [] as GraphFlowNode[];
    const nodeEmphasis = (id: string) =>
      emphasisForNode(id, focusId, null, emphasisEdges, matchIds);
    const edgeEmphasis = (edge: KnowledgeGraphEdge) =>
      emphasisForEdge(edge, null, selectedEdgeId, emphasisEdges);
    if (structured && structure && filters.layoutMode !== "explore") {
      return structuredToFlow(
        visuals,
        edgePick.edges,
        structure,
        filters.layoutMode,
        nodeEmphasis,
        edgeEmphasis,
      ).nodes;
    }
    const positioned = layoutKnowledgeGraph(
      exploreVisible?.nodes ?? [],
      exploreVisible?.edges ?? [],
    );
    return exploreToFlow(
      positioned,
      exploreVisible?.edges ?? [],
      nodeEmphasis,
      edgeEmphasis,
    ).nodes;
    // layoutSeed forces a fresh placement after reset without changing data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    payload,
    structured,
    structure,
    visuals,
    filters.layoutMode,
    edgePick.edges,
    exploreVisible,
    focusId,
    matchIds,
    selectedEdgeId,
    layoutSeed,
  ]);

  const edgeModel = useMemo(() => {
    if (!payload) return [] as KnowledgeFlowEdge[];
    const nodeEmphasis = (id: string) =>
      emphasisForNode(id, focusId, null, emphasisEdges, matchIds);
    const edgeEmphasis = (edge: KnowledgeGraphEdge) =>
      emphasisForEdge(edge, null, selectedEdgeId, emphasisEdges);
    if (structured && structure && filters.layoutMode !== "explore") {
      return structuredToFlow(
        visuals,
        edgePick.edges,
        structure,
        filters.layoutMode,
        nodeEmphasis,
        edgeEmphasis,
      ).edges;
    }
    const positioned = layoutKnowledgeGraph(
      exploreVisible?.nodes ?? [],
      exploreVisible?.edges ?? [],
    );
    return exploreToFlow(
      positioned,
      exploreVisible?.edges ?? [],
      nodeEmphasis,
      edgeEmphasis,
    ).edges;
  }, [
    payload,
    structured,
    structure,
    visuals,
    filters.layoutMode,
    edgePick.edges,
    exploreVisible,
    focusId,
    matchIds,
    selectedEdgeId,
    emphasisEdges,
  ]);

  const layoutKey = useMemo(() => {
    const ids = nodeModel.map((node) => node.id).join(",");
    return `${filters.layoutMode}:${filters.depth}:${focusId ?? ""}:${ids}:${layoutSeed}`;
  }, [nodeModel, filters.layoutMode, filters.depth, focusId, layoutSeed]);

  useEffect(() => {
    setFlowNodes(nodeModel);
  }, [nodeModel]);

  useEffect(() => {
    setFlowEdges(edgeModel);
  }, [edgeModel]);

  useEffect(() => {
    setFlowNodes((prev) =>
      prev.map((node) => {
        if (node.type !== "knowledge") return node;
        return {
          ...node,
          selected: node.id === focusId,
          data: {
            ...node.data,
            emphasis: emphasisForNode(
              node.id,
              focusId,
              hoveredNodeId,
              emphasisEdges,
              matchIds,
            ),
          },
        };
      }),
    );
    setFlowEdges((prev) =>
      prev.map((edge) => {
        const src = emphasisEdges.find((item) => item.id === edge.id);
        if (!src || !edge.data) return edge;
        return {
          ...edge,
          selected: edge.id === selectedEdgeId,
          data: {
            ...edge.data,
            emphasis: emphasisForEdge(
              src,
              hoveredNodeId,
              selectedEdgeId,
              emphasisEdges,
            ),
          },
        };
      }),
    );
  }, [focusId, hoveredNodeId, selectedEdgeId, matchIds, emphasisEdges]);

  const selectedNode = focusId ? nodesById.get(focusId) ?? null : null;
  const selectedEdge = selectedEdgeId
    ? filtered.edges.find((e) => e.id === selectedEdgeId) ?? null
    : null;

  const hiddenMembers =
    structure?.groups.reduce((sum, group) => sum + group.hiddenCount, 0) ?? 0;
  const visibleMembers = structure
    ? 1 + structure.groups.reduce((sum, group) => sum + group.visible.length, 0)
    : exploreVisible?.nodes.length ?? 0;
  const viewSummary = selectedNode
    ? `${selectedNode.label} · ${filters.depth} bước · ${visibleMembers} nút${
        hiddenMembers > 0 ? ` · ${hiddenMembers} đang ẩn` : ""
      }`
    : `${visibleMembers} nút · độ sâu ${filters.depth}`;

  const pathLabel = useMemo(() => {
    if (selectedNode) return selectedNode.label;
    if (selectedEdge) {
      const s = nodesById.get(selectedEdge.source)?.label ?? selectedEdge.source;
      const t = nodesById.get(selectedEdge.target)?.label ?? selectedEdge.target;
      return `${s} → ${relationLabel(selectedEdge.relation)} → ${t}`;
    }
    return null;
  }, [selectedNode, selectedEdge, nodesById]);

  const selectNode = useCallback((nodeId: string | null) => {
    if (!nodeId) return;
    setExplicitFocusId(nodeId);
    setSelectedEdgeId(null);
    setInspectorOpen(true);
  }, []);

  const selectEdge = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
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

  const toggleGroup = useCallback((groupKey: string, collapsed: boolean) => {
    setGroupOverrides((prev) => ({
      ...prev,
      [groupKey]: collapsed ? "open" : "closed",
    }));
  }, []);

  const revealGroup = useCallback((groupKey: string) => {
    setGroupReveal((prev) => ({
      ...prev,
      [groupKey]: (prev[groupKey] ?? 0) + GROUP_PAGE,
    }));
  }, []);

  const openComponent = useCallback((nextFocusId: string, more: boolean) => {
    if (more) {
      setShowAllComponents(true);
      return;
    }
    setExplicitFocusId(nextFocusId);
    setSelectedEdgeId(null);
    setInspectorOpen(true);
  }, []);

  const resetView = useCallback(() => {
    setExplicitFocusId(null);
    setSelectedEdgeId(null);
    setHoveredNodeId(null);
    setExpandedIds(new Set());
    setGroupOverrides({});
    setGroupReveal({});
    setShowAllComponents(false);
    setShowAllEdges(false);
    setQuery("");
    setLayoutSeed((seed) => seed + 1);
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
        setSelectedEdgeId(null);
        setHoveredNodeId(null);
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
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border-default bg-surface/95 px-4 py-2.5 backdrop-blur-md sm:px-5">
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
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-border-default bg-base text-secondary shadow-xs transition-colors hover:bg-elevated lg:hidden"
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
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-border-default bg-base text-secondary shadow-xs transition-colors hover:bg-elevated lg:hidden"
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
          <div className="hidden w-[230px] shrink-0 lg:block">
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
                layoutKey={layoutKey}
                layoutMode={filters.layoutMode}
                depth={filters.depth}
                showAllEdges={showAllEdges}
                hiddenEdgeCount={edgePick.hiddenCount}
                onNodesChange={setFlowNodes}
                onEdgesChange={setFlowEdges}
                onSelectNode={selectNode}
                onSelectEdge={selectEdge}
                onToggleGroup={toggleGroup}
                onRevealGroup={revealGroup}
                onOpenComponent={openComponent}
                onNodeDoubleClick={expandNode}
                onHoverNode={setHoveredNodeId}
                onResetLayout={resetView}
                onLayoutMode={(layoutMode) =>
                  setFilters((current) => ({ ...current, layoutMode }))
                }
                onDepth={(depth) =>
                  setFilters((current) => ({ ...current, depth }))
                }
                showLabels={showLabels}
                showRelations={showRelations}
                onToggleLabels={() => setShowLabels((value) => !value)}
                onToggleRelations={() => setShowRelations((value) => !value)}
                onToggleAllEdges={() => setShowAllEdges((value) => !value)}
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
                onExpandNeighbors={
                  selectedNode ? () => expandNode(selectedNode.id) : undefined
                }
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
              <div className="relative z-10 flex h-full w-[min(100%,260px)] flex-col bg-surface shadow-xl">
                <div className="flex items-center justify-between border-b border-border-default bg-elevated/30 px-3 py-2">
                  <p className="flex items-center gap-2 text-body-sm font-semibold text-primary">
                    <PanelLeft className="h-4 w-4 text-accent-secondary" aria-hidden />
                    Điều khiển
                  </p>
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
                  "relative z-10 flex h-full w-[min(100%,320px)] flex-col bg-surface shadow-xl",
                  "max-md:mt-auto max-md:h-[min(72vh,560px)] max-md:w-full max-md:rounded-t-xl",
                )}
              >
                <div className="flex items-center justify-between border-b border-border-default bg-elevated/30 px-3 py-2">
                  <p className="flex items-center gap-2 text-body-sm font-semibold text-primary">
                    <PanelRight className="h-4 w-4 text-accent-secondary" aria-hidden />
                    Chi tiết
                  </p>
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
                      onExpandNeighbors={
                        selectedNode ? () => expandNode(selectedNode.id) : undefined
                      }
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
          viewSummary={viewSummary}
          dataSource={dataSource}
        />
      </div>
    </AppShell>
  );
}
