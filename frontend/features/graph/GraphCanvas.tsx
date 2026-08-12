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
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forwardRef,
  useCallback,
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
  KnowledgeNode,
  type KnowledgeFlowNode,
} from "@/features/graph/nodes/KnowledgeNode";
import { cn } from "@/lib/utils";

const nodeTypes: NodeTypes = {
  knowledge: KnowledgeNode,
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
  nodes: KnowledgeFlowNode[];
  edges: KnowledgeFlowEdge[];
  onNodesChange: (
    updater:
      | KnowledgeFlowNode[]
      | ((prev: KnowledgeFlowNode[]) => KnowledgeFlowNode[]),
  ) => void;
  onEdgesChange: (
    updater:
      | KnowledgeFlowEdge[]
      | ((prev: KnowledgeFlowEdge[]) => KnowledgeFlowEdge[]),
  ) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onNodeDoubleClick?: (nodeId: string) => void;
  onResetLayout: () => void;
  showLabels: boolean;
  showRelations: boolean;
  onToggleLabels: () => void;
  onToggleRelations: () => void;
  className?: string;
};

function GraphCanvasInner(
  {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onSelectNode,
    onSelectEdge,
    onNodeDoubleClick,
    onResetLayout,
    showLabels,
    showRelations,
    onToggleLabels,
    onToggleRelations,
    className,
  }: Props,
  ref: React.Ref<GraphCanvasHandle>,
) {
  const rf = useReactFlow<KnowledgeFlowNode, KnowledgeFlowEdge>();
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
      rf.fitView({ padding: 0.22, duration: 400 });
    }, 60);
    return () => window.clearTimeout(id);
  }, [ready, nodes.length, rf]);

  const onSelectionChange = useCallback(
    ({ nodes: selNodes, edges: selEdges }: OnSelectionChangeParams) => {
      if (selNodes[0]) {
        onSelectNode(selNodes[0].id);
        onSelectEdge(null);
        return;
      }
      if (selEdges[0]) {
        onSelectEdge(selEdges[0].id);
        onSelectNode(null);
        return;
      }
      onSelectNode(null);
      onSelectEdge(null);
    },
    [onSelectEdge, onSelectNode],
  );

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
        onNodesChange={(changes: NodeChange<KnowledgeFlowNode>[]) => {
          onNodesChange((prev) => applyNodeChanges(changes, prev));
        }}
        onEdgesChange={(changes: EdgeChange<KnowledgeFlowEdge>[]) => {
          onEdgesChange((prev) => applyEdgeChanges(changes, prev));
        }}
        onSelectionChange={onSelectionChange}
        onNodeDoubleClick={(_, node) => onNodeDoubleClick?.(node.id)}
        onInit={() => setReady(true)}
        onPaneClick={() => {
          onSelectNode(null);
          onSelectEdge(null);
        }}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        minZoom={0.25}
        maxZoom={1.75}
        onlyRenderVisibleElements
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
            const t = (n.data as KnowledgeFlowNode["data"] | undefined)
              ?.nodeType;
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
        onZoomIn={() => rf.zoomIn({ duration: 180 })}
        onZoomOut={() => rf.zoomOut({ duration: 180 })}
        onFit={() => rf.fitView({ padding: 0.2, duration: 260 })}
        onCenterSelected={() => {
          const selected = nodes.find(
            (n) => n.selected || n.data.emphasis === "selected",
          );
          if (!selected) {
            rf.fitView({ padding: 0.2, duration: 260 });
            return;
          }
          const w = selected.measured?.width ?? 168;
          const h = selected.measured?.height ?? 56;
          rf.setCenter(
            selected.position.x + w / 2,
            selected.position.y + h / 2,
            { zoom: Math.max(rf.getZoom(), 1), duration: 300 },
          );
        }}
        onResetLayout={onResetLayout}
        onToggleLabels={onToggleLabels}
        onToggleRelations={onToggleRelations}
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
