/**
 * =============================================================================
 * File: GraphCanvas.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: React Flow canvas for workspace Knowledge Graph exploration.
 * Responsibilities:
 *   - Pan / zoom / fit / select nodes & edges
 *   - Custom editorial nodes, curved edges, minimap
 *   - Expose imperative view controls to parent toolbar
 * Dependencies:
 *   - @xyflow/react, KnowledgeNode, KnowledgeEdge, GraphToolbar
 * Public Exports:
 *   - GraphCanvas, GraphCanvasHandle
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Dot-grid canvas; minimap low-contrast; no physics chaos.
 * =============================================================================
 */

"use client";

import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  SelectionMode,
  useReactFlow,
  type EdgeChange,
  type EdgeTypes,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from "react";

import {
  KnowledgeEdge,
  type KnowledgeFlowEdge,
} from "@/features/graph/edges/KnowledgeEdge";
import { GraphToolbar } from "@/features/graph/GraphToolbar";
import {
  ComponentNode,
  GroupFrameNode,
  OverflowNode,
  type ComponentFlowNode,
  type GroupFlowNode,
  type OverflowFlowNode,
} from "@/features/graph/nodes/GraphChromeNodes";
import {
  KnowledgeNode,
  type KnowledgeFlowNode,
} from "@/features/graph/nodes/KnowledgeNode";
import { cn } from "@/lib/utils";
import type { KnowledgeGraphLayoutMode } from "@/types/knowledge-graph";

export type GraphFlowNode =
  | KnowledgeFlowNode
  | GroupFlowNode
  | OverflowFlowNode
  | ComponentFlowNode;

const nodeTypes: NodeTypes = {
  knowledge: KnowledgeNode,
  group: GroupFrameNode,
  overflow: OverflowNode,
  component: ComponentNode,
};

const edgeTypes: EdgeTypes = {
  knowledge: KnowledgeEdge,
};

export type GraphCanvasHandle = {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  centerNode: (nodeId: string) => void;
};

type Props = {
  nodes: GraphFlowNode[];
  edges: KnowledgeFlowEdge[];
  layoutKey: string;
  layoutMode: KnowledgeGraphLayoutMode;
  depth: number;
  showAllEdges: boolean;
  hiddenEdgeCount: number;
  onNodesChange: (
    updater: GraphFlowNode[] | ((prev: GraphFlowNode[]) => GraphFlowNode[]),
  ) => void;
  onEdgesChange: (
    updater:
      | KnowledgeFlowEdge[]
      | ((prev: KnowledgeFlowEdge[]) => KnowledgeFlowEdge[]),
  ) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onToggleGroup: (groupKey: string, collapsed: boolean) => void;
  onRevealGroup: (groupKey: string) => void;
  onOpenComponent: (focusId: string, more: boolean) => void;
  onNodeDoubleClick?: (nodeId: string) => void;
  onHoverNode?: (nodeId: string | null) => void;
  onResetLayout: () => void;
  onLayoutMode: (mode: KnowledgeGraphLayoutMode) => void;
  onDepth: (depth: number) => void;
  showLabels: boolean;
  showRelations: boolean;
  onToggleLabels: () => void;
  onToggleRelations: () => void;
  onToggleAllEdges: () => void;
  className?: string;
};

function GraphCanvasInner(
  {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    layoutKey,
    layoutMode,
    depth,
    showAllEdges,
    hiddenEdgeCount,
    onSelectNode,
    onSelectEdge,
    onToggleGroup,
    onRevealGroup,
    onOpenComponent,
    onNodeDoubleClick,
    onHoverNode,
    onResetLayout,
    onLayoutMode,
    onDepth,
    showLabels,
    showRelations,
    onToggleLabels,
    onToggleRelations,
    onToggleAllEdges,
    className,
  }: Props,
  ref: React.Ref<GraphCanvasHandle>,
) {
  const rf = useReactFlow<GraphFlowNode, KnowledgeFlowEdge>();
  const [ready, setReady] = useState(false);

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => rf.zoomIn({ duration: 200 }),
      zoomOut: () => rf.zoomOut({ duration: 200 }),
      fitView: () => rf.fitView({ padding: 0.2, duration: 280 }),
      centerNode: (nodeId: string) => {
        const node = rf.getNode(nodeId);
        if (!node) return;
        const w = node.measured?.width ?? 168;
        const h = node.measured?.height ?? 56;
        rf.setCenter(node.position.x + w / 2, node.position.y + h / 2, {
          zoom: Math.max(rf.getZoom(), 1),
          duration: 320,
        });
      },
    }),
    [rf],
  );

  useEffect(() => {
    if (!ready || nodes.length === 0) return;
    const id = window.setTimeout(() => {
      rf.fitView({ padding: 0.2, duration: 360 });
    }, 50);
    return () => window.clearTimeout(id);
  }, [ready, layoutKey, rf, nodes.length]);

  const visibleEdges = useMemo(
    () => (showRelations ? edges : []),
    [edges, showRelations],
  );

  const labeledEdges = useMemo(
    () =>
      visibleEdges.map((e) => ({
        ...e,
        data: {
          ...e.data!,
          showLabel:
            showLabels ||
            Boolean(e.data?.showLabel) ||
            e.data?.emphasis === "path" ||
            e.data?.emphasis === "selected",
        },
      })),
    [visibleEdges, showLabels],
  );

  return (
    <div className={cn("relative h-full w-full", className)}>
      <ReactFlow
        nodes={nodes}
        edges={labeledEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={(changes: NodeChange<GraphFlowNode>[]) => {
          onNodesChange((prev) => applyNodeChanges(changes, prev));
        }}
        onEdgesChange={(changes: EdgeChange<KnowledgeFlowEdge>[]) => {
          onEdgesChange((prev) => applyEdgeChanges(changes, prev));
        }}
        onNodeClick={(_, node) => {
          if (node.type === "group") {
            const data = node.data as GroupFlowNode["data"];
            onToggleGroup(data.groupKey, data.collapsed);
            return;
          }
          if (node.type === "overflow") {
            onRevealGroup((node.data as OverflowFlowNode["data"]).groupKey);
            return;
          }
          if (node.type === "component") {
            const data = node.data as ComponentFlowNode["data"];
            onOpenComponent(data.focusId, data.more);
            return;
          }
          onSelectNode(node.id);
          onSelectEdge(null);
        }}
        onNodeDoubleClick={(_, node) => {
          if (node.type === "knowledge") onNodeDoubleClick?.(node.id);
        }}
        onNodeMouseEnter={(_, node) => {
          if (node.type === "knowledge") onHoverNode?.(node.id);
        }}
        onNodeMouseLeave={() => onHoverNode?.(null)}
        onEdgeClick={(_, edge) => {
          onSelectEdge(edge.id);
        }}
        onInit={() => setReady(true)}
        onPaneClick={() => {
          onSelectEdge(null);
          onHoverNode?.(null);
        }}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        minZoom={0.2}
        maxZoom={1.6}
        onlyRenderVisibleElements
        nodesConnectable={false}
        panOnScroll
        zoomOnScroll
        preventScrolling
        selectionMode={SelectionMode.Partial}
        multiSelectionKeyCode="Shift"
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "knowledge",
          selectable: true,
        }}
        className="knowledge-graph-canvas bg-base"
      >
        <Background
          id="kg-dots"
          variant={BackgroundVariant.Dots}
          gap={22}
          size={1.1}
          color="var(--border-default)"
        />
        <MiniMap
          pannable
          zoomable
          nodeStrokeWidth={2}
          maskColor="color-mix(in srgb, var(--bg-base) 72%, transparent)"
          className="!bottom-3 !right-3 !m-0 overflow-hidden rounded-md border border-border-default !bg-surface/90 shadow-xs"
          nodeColor={(n) => {
            const data = n.data as {
              nodeType?: string;
              accentType?: string;
            };
            const t = data.nodeType ?? data.accentType;
            if (t === "topic") return "var(--accent-secondary)";
            if (t === "entity") return "var(--accent-primary)";
            if (t === "document") return "var(--citation)";
            return "var(--text-tertiary)";
          }}
        />
      </ReactFlow>

      <GraphToolbar
        className="absolute left-3 top-3 z-10"
        showLabels={showLabels}
        showRelations={showRelations}
        showAllEdges={showAllEdges}
        hiddenEdgeCount={hiddenEdgeCount}
        layoutMode={layoutMode}
        depth={depth}
        onZoomIn={() => rf.zoomIn({ duration: 180 })}
        onZoomOut={() => rf.zoomOut({ duration: 180 })}
        onFit={() => rf.fitView({ padding: 0.2, duration: 260 })}
        onCenterSelected={() => {
          const selected = nodes.find(
            (n) =>
              n.type === "knowledge" &&
              (n.selected || n.data.emphasis === "selected" || n.data.prominence === "root"),
          );
          if (!selected) {
            rf.fitView({ padding: 0.2, duration: 260 });
            return;
          }
          const w = selected.measured?.width ?? selected.width ?? 168;
          const h = selected.measured?.height ?? selected.height ?? 56;
          rf.setCenter(
            selected.position.x + w / 2,
            selected.position.y + h / 2,
            { zoom: Math.max(rf.getZoom(), 1), duration: 300 },
          );
        }}
        onResetLayout={onResetLayout}
        onToggleLabels={onToggleLabels}
        onToggleRelations={onToggleRelations}
        onToggleAllEdges={onToggleAllEdges}
        onLayoutMode={onLayoutMode}
        onDepth={onDepth}
      />
    </div>
  );
}

const GraphCanvasForward = forwardRef(GraphCanvasInner);

export const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(
  function GraphCanvas(props, ref) {
    return (
      <ReactFlowProvider>
        <GraphCanvasForward {...props} ref={ref} />
      </ReactFlowProvider>
    );
  },
);
