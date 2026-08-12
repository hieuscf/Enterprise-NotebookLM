/**
 * =============================================================================
 * File: NodeInspector.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Right-rail inspector for selected Knowledge Graph nodes.
 * Responsibilities:
 *   - Empty state when nothing selected
 *   - Show type, description, confidence, relations, sources
 *   - Deep-link into document viewer for citations
 * Dependencies:
 *   - next/link, lucide-react, graph-style, search-navigation
 * Public Exports:
 *   - NodeInspector
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Sources use buildDocumentViewerHref (?page=&chunk=).
 * =============================================================================
 */

"use client";

import { ExternalLink, FileText, Network } from "lucide-react";
import Link from "next/link";

import { nodeTypeLabel, nodeTypeStyles, relationLabel } from "@/features/graph/graph-style";
import { buildDocumentViewerHref } from "@/lib/search-navigation";
import { cn } from "@/lib/utils";
import type {
  CitationReference,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
} from "@/types/knowledge-graph";

type Props = {
  workspaceId: string;
  node: KnowledgeGraphNode | null;
  edges: KnowledgeGraphEdge[];
  nodesById: Map<string, KnowledgeGraphNode>;
  onSelectConnected: (nodeId: string) => void;
  className?: string;
};

function sourceHref(workspaceId: string, citation: CitationReference): string {
  return buildDocumentViewerHref(workspaceId, {
    document_id: citation.document_id,
    chunk_id: citation.chunk_id ?? null,
    page_number: citation.page_number ?? null,
    location: null,
  });
}

export function NodeInspector({
  workspaceId,
  node,
  edges,
  nodesById,
  onSelectConnected,
  className,
}: Props) {
  if (!node) {
    return (
      <aside
        className={cn(
          "flex h-full flex-col justify-center border-l border-border-default bg-surface px-6 py-8",
          className,
        )}
        aria-label="Chi tiết nút"
      >
        <div className="mx-auto max-w-[220px] text-center">
          <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-md bg-accent-secondary-soft">
            <Network className="h-4 w-4 text-accent-secondary" aria-hidden />
          </span>
          <h2 className="mt-4 text-h3 text-primary">Khám phá đồ thị tri thức</h2>
          <p className="mt-2 text-body-sm text-secondary">
            Chọn một nút để xem quan hệ, nguồn tài liệu và ngữ cảnh.
          </p>
        </div>
      </aside>
    );
  }

  const styles = nodeTypeStyles[node.type];
  const connectedEdges = edges.filter(
    (e) => e.source === node.id || e.target === node.id,
  );
  const connectedEntities = connectedEdges
    .map((e) => {
      const otherId = e.source === node.id ? e.target : e.source;
      return nodesById.get(otherId);
    })
    .filter((n): n is KnowledgeGraphNode => Boolean(n));

  const documents = connectedEntities.filter((n) => n.type === "document");
  const entities = connectedEntities.filter((n) => n.type !== "document");
  const sources =
    node.citations?.length
      ? node.citations
      : documents.flatMap((d) => d.citations ?? []);

  const primaryDocId =
    (node.metadata?.document_id as string | undefined) ??
    sources[0]?.document_id ??
    null;

  return (
    <aside
      className={cn(
        "flex h-full flex-col overflow-y-auto border-l border-border-default bg-surface",
        className,
      )}
      aria-label="Chi tiết nút"
    >
      <div className="border-b border-border-default px-5 py-4">
        <span
          className={cn(
            "inline-flex rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
            styles.chip,
          )}
        >
          {nodeTypeLabel(node.type)}
        </span>
        <h2 className="mt-2 text-h2 text-primary">{node.label}</h2>
        {node.subtype ? (
          <p className="mt-1 text-body-sm text-secondary">{node.subtype}</p>
        ) : null}
        {typeof node.confidence === "number" ? (
          <p className="mt-2 text-caption text-tertiary">
            Độ tin cậy{" "}
            <span className="tabular-nums text-secondary">
              {node.confidence.toFixed(2)}
            </span>
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-5 px-5 py-4">
        {node.description ? (
          <section>
            <h3 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
              Mô tả
            </h3>
            <p className="mt-1.5 text-body-sm leading-relaxed text-secondary">
              {node.description}
            </p>
          </section>
        ) : null}

        <section>
          <h3 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
            Quan hệ
          </h3>
          <p className="mt-1.5 text-body-sm text-secondary">
            <span className="tabular-nums text-primary">{entities.length}</span>{" "}
            thực thể liên kết
          </p>
          <p className="text-body-sm text-secondary">
            <span className="tabular-nums text-primary">{documents.length}</span>{" "}
            tài liệu hỗ trợ
          </p>
          <ul className="mt-3 flex flex-col gap-1">
            {connectedEdges.slice(0, 8).map((edge) => {
              const otherId =
                edge.source === node.id ? edge.target : edge.source;
              const other = nodesById.get(otherId);
              if (!other) return null;
              return (
                <li key={edge.id}>
                  <button
                    type="button"
                    onClick={() => onSelectConnected(other.id)}
                    className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left hover:bg-elevated"
                  >
                    <span className="min-w-0 truncate text-body-sm text-primary">
                      {other.label}
                    </span>
                    <span className="shrink-0 text-[10px] tracking-wide text-tertiary">
                      {relationLabel(edge.relation)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section>
          <h3 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
            Nguồn
          </h3>
          {sources.length === 0 ? (
            <p className="mt-1.5 text-body-sm text-secondary">
              Chưa có trích dẫn nguồn cho nút này.
            </p>
          ) : (
            <ul className="mt-2 flex flex-col gap-2">
              {sources.map((citation, idx) => (
                <li key={`${citation.document_id}-${idx}`}>
                  <Link
                    href={sourceHref(workspaceId, citation)}
                    className="group flex items-start gap-2 rounded-md border border-transparent px-2 py-1.5 hover:border-border-default hover:bg-elevated"
                  >
                    <FileText
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-citation"
                      aria-hidden
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-body-sm font-medium text-primary group-hover:text-accent-primary">
                        {citation.document_title}
                      </span>
                      {citation.page_number != null ? (
                        <span className="text-caption text-tertiary">
                          Trang {citation.page_number}
                        </span>
                      ) : null}
                      {citation.snippet ? (
                        <span className="mt-0.5 block text-caption text-secondary line-clamp-2">
                          {citation.snippet}
                        </span>
                      ) : null}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {primaryDocId ? (
            <Link
              href={buildDocumentViewerHref(workspaceId, {
                document_id: primaryDocId,
                chunk_id: null,
                page_number: sources[0]?.page_number ?? null,
                location: null,
              })}
              className="mt-3 inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-default bg-base px-3 py-1.5 text-body-sm font-medium text-secondary transition-colors hover:border-accent-primary/40 hover:text-accent-primary"
            >
              Mở nguồn
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </Link>
          ) : null}
        </section>
      </div>
    </aside>
  );
}
