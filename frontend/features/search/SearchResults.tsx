/**
 * =============================================================================
 * File: SearchResults.tsx
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Render ranked search hits; deep-link to Document Viewer (FR3).
 * Responsibilities:
 *   - Loading / empty / error / result list; router.push with ?chunk=
 * Dependencies:
 *   - lib/search-highlight, search-navigation, next/navigation, types/search
 * Public Exports:
 *   - SearchResults
 * Database/Table: N/A
 * Related Modules: features/search/SearchView.tsx, DocumentViewer
 * Important Notes: Click analytics via onResultClick (fire-and-forget).
 * =============================================================================
 */

"use client";

import { AlertCircle, FileText } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  formatRetrievalMethodLabel,
  highlightSnippetSegments,
} from "@/lib/search-highlight";
import { buildDocumentViewerHref } from "@/lib/search-navigation";
import { saveSearchMatches } from "@/lib/search-matches";
import { formatContentLocationLabel } from "@/lib/content-location";
import { cn } from "@/lib/utils";
import type { SearchResultItem } from "@/types/search";

type Props = {
  workspaceId: string;
  query: string;
  results: SearchResultItem[];
  resultsCount: number;
  loading: boolean;
  error: string | null;
  hasSearched: boolean;
  titles?: Record<string, string>;
  /** Called before navigation — must not block if it fails. */
  onResultClick?: (item: SearchResultItem) => void | Promise<void>;
  /** Persist search UI state before navigating away. */
  onBeforeNavigate?: () => void;
};

export function SearchResults({
  workspaceId,
  query,
  results,
  resultsCount,
  loading,
  error,
  hasSearched,
  titles = {},
  onResultClick,
  onBeforeNavigate,
}: Props) {
  const router = useRouter();

  function handleClick(item: SearchResultItem) {
    onBeforeNavigate?.();
    if (onResultClick) {
      void Promise.resolve(onResultClick(item)).catch(() => undefined);
    }
    // Persist siblings on the same document for Prev/Next in AI panel.
    const siblings = results
      .filter((r) => r.document_id === item.document_id && r.chunk_id)
      .map((r) => ({
        chunkId: r.chunk_id as string,
        documentId: r.document_id,
        pageNumber: r.page_number ?? r.location?.page_number ?? null,
        score: r.score,
        retrievalMethod: r.retrieval_method,
        textSnippet: r.text_snippet,
        documentTitle: r.document_title ?? titles[r.document_id] ?? null,
      }));
    if (item.chunk_id) {
      saveSearchMatches(workspaceId, item.document_id, siblings, item.chunk_id);
    }
    router.push(buildDocumentViewerHref(workspaceId, item));
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-3" aria-busy aria-label="Đang tìm kiếm">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg border border-border-default bg-elevated/60"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-body-sm text-danger"
      >
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p>{error}</p>
      </div>
    );
  }

  if (!hasSearched) {
    return (
      <div className="rounded-lg border border-dashed border-border-default px-6 py-12 text-center">
        <FileText className="mx-auto h-8 w-8 text-tertiary" aria-hidden />
        <p className="mt-3 text-body-sm text-secondary">
          Nhập truy vấn để tìm kiếm ngữ nghĩa trong workspace.
        </p>
      </div>
    );
  }

  if (resultsCount === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border-default px-6 py-12 text-center">
        <p className="text-body-sm font-medium text-primary">Không có kết quả</p>
        <p className="mt-1 text-body-sm text-secondary">
          Không tìm thấy đoạn văn phù hợp với “{query}”. Thử từ khóa khác hoặc nới filter.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption text-secondary">
        {resultsCount} kết quả · xếp hạng theo độ liên quan
      </p>
      <ul className="flex flex-col gap-2">
        {results.map((item) => {
          const title =
            item.document_title ||
            titles[item.document_id] ||
            `Tài liệu ${item.document_id.slice(0, 8)}…`;
          const segments = highlightSnippetSegments(item.text_snippet, query);
          const locLabel = formatContentLocationLabel(
            item.location ?? {
              page_number: item.page_number,
              section_index: null,
              section_title: null,
            },
          );
          return (
            <li key={`${item.document_id}-${item.chunk_id ?? item.rank}`}>
              <button
                type="button"
                onClick={() => handleClick(item)}
                className={cn(
                  "group w-full cursor-pointer rounded-lg border border-border-default bg-surface px-4 py-3 text-left",
                  "transition-[border-color,box-shadow,background-color] duration-200",
                  "hover:border-accent-primary/50 hover:bg-elevated/50 hover:shadow-md",
                  "focus:outline-none focus:ring-2 focus:ring-accent-primary/25",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-caption font-semibold text-tertiary">#{item.rank}</span>
                  <span
                    className={cn(
                      "text-body-sm font-semibold text-primary transition-colors",
                      "group-hover:underline group-hover:decoration-accent-primary/60",
                    )}
                  >
                    {title}
                  </span>
                  {locLabel ? (
                    <span className="text-caption text-tertiary">{locLabel}</span>
                  ) : null}
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      methodBadgeClass(item.retrieval_method),
                    )}
                  >
                    {formatRetrievalMethodLabel(item.retrieval_method)}
                  </span>
                  <span className="ml-auto text-caption tabular-nums text-tertiary">
                    score {item.score.toFixed(3)}
                  </span>
                </div>
                <p className="mt-2 text-body-sm leading-relaxed text-secondary">
                  {segments.map((seg, i) =>
                    seg.highlight ? (
                      <mark
                        key={i}
                        className="rounded-sm bg-accent-primary-soft px-0.5 text-accent-primary"
                      >
                        {seg.text}
                      </mark>
                    ) : (
                      <span key={i}>{seg.text}</span>
                    ),
                  )}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function methodBadgeClass(method: SearchResultItem["retrieval_method"]): string {
  switch (method) {
    case "vector":
      return "bg-accent-primary-soft text-accent-primary";
    case "bm25":
      return "bg-accent-tertiary-soft text-accent-tertiary";
    case "knowledge_graph":
      return "bg-elevated text-secondary";
    default:
      return "bg-elevated text-tertiary";
  }
}
