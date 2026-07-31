/**
 * =============================================================================
 * File: SearchResults.tsx
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Render ranked search hits with method badge and keyword highlight.
 * Responsibilities:
 *   - Loading / empty / error / result list states; navigate on click
 * Dependencies:
 *   - lib/search-highlight, next/navigation, types/search
 * Public Exports:
 *   - SearchResults
 * Database/Table: N/A
 * Related Modules: features/search/SearchView.tsx
 * Important Notes: Click analytics via onResultClick (fire-and-forget; must not
 *   block navigation if PATCH fails).
 * =============================================================================
 */

"use client";

import { AlertCircle, FileText } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  formatRetrievalMethodLabel,
  highlightSnippetSegments,
} from "@/lib/search-highlight";
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
  /** Optional analytics hook — must not block navigation if it fails. */
  onResultClick?: (item: SearchResultItem) => void | Promise<void>;
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
}: Props) {
  const router = useRouter();

  async function handleClick(item: SearchResultItem) {
    const href = `/workspaces/${workspaceId}/documents/${item.document_id}`;
    // Fire-and-forget analytics — never block navigation.
    if (onResultClick) {
      void Promise.resolve(onResultClick(item)).catch(() => undefined);
    }
    router.push(href);
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
          const title = titles[item.document_id] ?? `Tài liệu ${item.document_id.slice(0, 8)}…`;
          const segments = highlightSnippetSegments(item.text_snippet, query);
          return (
            <li key={`${item.document_id}-${item.chunk_id ?? item.rank}`}>
              <button
                type="button"
                onClick={() => void handleClick(item)}
                className={cn(
                  "w-full rounded-lg border border-border-default bg-surface px-4 py-3 text-left transition-colors",
                  "hover:border-accent-primary/40 hover:bg-elevated/40 focus:outline-none focus:ring-2 focus:ring-accent-primary/20",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-caption font-semibold text-tertiary">#{item.rank}</span>
                  <span className="text-body-sm font-semibold text-primary">{title}</span>
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
