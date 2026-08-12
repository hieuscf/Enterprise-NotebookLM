/**
 * =============================================================================
 * File: RelationshipInspector.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Explain a selected edge via endpoints, confidence, and sources.
 * Responsibilities:
 *   - Render relationship anatomy (source → relation → target)
 *   - Link supporting document citations
 * Dependencies:
 *   - next/link, graph-style, search-navigation
 * Public Exports:
 *   - RelationshipInspector
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Prefer edge citations; fall back to endpoint node citations.
 * =============================================================================
 */

"use client";

import { ArrowDown, FileText } from "lucide-react";
import Link from "next/link";

import { relationLabel } from "@/features/graph/graph-style";
import { buildDocumentViewerHref } from "@/lib/search-navigation";
import { cn } from "@/lib/utils";
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
} from "@/types/knowledge-graph";

type Props = {
  workspaceId: string;
  edge: KnowledgeGraphEdge;
  sourceNode: KnowledgeGraphNode | null;
  targetNode: KnowledgeGraphNode | null;
  onSelectNode: (nodeId: string) => void;
  className?: string;
};

export function RelationshipInspector({
  workspaceId,
  edge,
  sourceNode,
  targetNode,
  onSelectNode,
  className,
}: Props) {
  const citations =
    edge.citations?.length
      ? edge.citations
      : [
          ...(sourceNode?.citations ?? []),
          ...(targetNode?.citations ?? []),
        ].slice(0, 4);

  return (
    <aside
      className={cn(
        "flex h-full flex-col overflow-y-auto border-l border-border-default bg-surface",
        className,
      )}
      aria-label="Chi tiết quan hệ"
    >
      <div className="border-b border-border-default px-5 py-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-accent-secondary">
          Quan hệ
        </p>
        <div className="mt-4 flex flex-col items-center gap-2 text-center">
          <button
            type="button"
            onClick={() => sourceNode && onSelectNode(sourceNode.id)}
            className="cursor-pointer text-body-sm font-semibold text-primary hover:text-accent-secondary"
          >
            {sourceNode?.label ?? edge.source}
          </button>
          <ArrowDown className="h-3.5 w-3.5 text-tertiary" aria-hidden />
          <span className="rounded-sm border border-border-default bg-elevated px-2 py-0.5 text-caption font-medium text-secondary">
            {relationLabel(edge.relation)}
          </span>
          <ArrowDown className="h-3.5 w-3.5 text-tertiary" aria-hidden />
          <button
            type="button"
            onClick={() => targetNode && onSelectNode(targetNode.id)}
            className="cursor-pointer text-body-sm font-semibold text-primary hover:text-accent-secondary"
          >
            {targetNode?.label ?? edge.target}
          </button>
        </div>
        {typeof edge.confidence === "number" ? (
          <p className="mt-4 text-center text-caption text-tertiary">
            Độ tin cậy{" "}
            <span className="tabular-nums text-secondary">
              {edge.confidence.toFixed(2)}
            </span>
          </p>
        ) : null}
      </div>

      <div className="px-5 py-4">
        <h3 className="text-caption font-semibold uppercase tracking-wider text-tertiary">
          Nguồn hỗ trợ
        </h3>
        <div className="mt-2 h-px w-full bg-border-default" aria-hidden />
        {citations.length === 0 ? (
          <p className="mt-3 text-body-sm text-secondary">
            Chưa có nguồn hỗ trợ cho quan hệ này.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {citations.map((citation, idx) => (
              <li key={`${citation.document_id}-${idx}`}>
                <Link
                  href={buildDocumentViewerHref(workspaceId, {
                    document_id: citation.document_id,
                    chunk_id: citation.chunk_id ?? null,
                    page_number: citation.page_number ?? null,
                    location: null,
                  })}
                  className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-elevated"
                >
                  <FileText
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-citation"
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-body-sm font-medium text-primary">
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
      </div>
    </aside>
  );
}
