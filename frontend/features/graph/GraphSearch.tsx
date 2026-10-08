/**
 * =============================================================================
 * File: GraphSearch.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Polished search for entities, topics, documents, and relations.
 * Responsibilities:
 *   - Query matching nodes; keyboard navigation through results
 *   - Emit select/center callbacks with a refined dropdown
 * Dependencies:
 *   - lucide-react, types/knowledge-graph, graph-style
 * Public Exports:
 *   - GraphSearch
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: `/` focuses this field (handled by parent).
 * =============================================================================
 */

"use client";

import { Search, Sparkles, X } from "lucide-react";
import { forwardRef, useEffect, useId, useState } from "react";

import { nodeTypeLabel, nodeTypeStyles } from "@/features/graph/graph-style";
import { cn } from "@/lib/utils";
import type { KnowledgeGraphNode } from "@/types/knowledge-graph";

type Props = {
  query: string;
  results: KnowledgeGraphNode[];
  onQueryChange: (value: string) => void;
  onSelectResult: (nodeId: string) => void;
  className?: string;
};

export const GraphSearch = forwardRef<HTMLInputElement, Props>(
  function GraphSearch(
    { query, results, onQueryChange, onSelectResult, className },
    ref,
  ) {
    const listId = useId();
    const [activeIndex, setActiveIndex] = useState(0);

    useEffect(() => {
      setActiveIndex(0);
    }, [query, results.length]);

    return (
      <div className={cn("relative w-full max-w-md", className)}>
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-tertiary"
            aria-hidden
          />
          <input
            ref={ref}
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Tìm thực thể, chủ đề, tài liệu…"
            aria-label="Tìm kiếm đồ thị tri thức"
            aria-controls={listId}
            aria-autocomplete="list"
            className="h-9 w-full rounded-full border border-border-default bg-surface pl-9 pr-9 text-body-sm text-primary shadow-xs placeholder:text-tertiary transition-all focus:border-accent-secondary/50 focus:outline-none focus:ring-2 focus:ring-accent-secondary/20"
            onKeyDown={(e) => {
              if (!results.length) return;
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => (i + 1) % results.length);
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => (i - 1 + results.length) % results.length);
              } else if (e.key === "Enter") {
                e.preventDefault();
                const hit = results[activeIndex];
                if (hit) onSelectResult(hit.id);
              }
            }}
          />
          {query ? (
            <button
              type="button"
              aria-label="Xóa tìm kiếm"
              onClick={() => onQueryChange("")}
              className="absolute right-2.5 top-1/2 flex h-5 w-5 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full text-tertiary hover:bg-elevated hover:text-primary"
            >
              <X className="h-3 w-3" aria-hidden />
            </button>
          ) : null}
        </div>

        {query.trim() ? (
          <div
            id={listId}
            role="listbox"
            className="absolute z-20 mt-2 max-h-72 w-full overflow-y-auto rounded-xl border border-border-default bg-surface p-1 shadow-lg"
          >
            <div className="flex items-center justify-between border-b border-border-default px-3 py-1.5">
              <p className="text-caption text-tertiary">
                {results.length} kết quả
              </p>
              <span className="rounded bg-base px-1.5 py-0.5 text-[10px] text-tertiary">
                Enter để chọn
              </span>
            </div>
            {results.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-3 py-6 text-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-elevated text-tertiary">
                  <Sparkles className="h-4 w-4" aria-hidden />
                </span>
                <p className="text-body-sm text-secondary">
                  Không có nút phù hợp.
                </p>
              </div>
            ) : (
              <ul>
                {results.slice(0, 12).map((node, index) => {
                  const styles = nodeTypeStyles[node.type];
                  return (
                    <li key={node.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={index === activeIndex}
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => onSelectResult(node.id)}
                        className={cn(
                          "flex w-full cursor-pointer items-start gap-3 rounded-lg px-2.5 py-2 text-left transition-colors",
                          index === activeIndex
                            ? "bg-accent-secondary-soft"
                            : "hover:bg-elevated",
                        )}
                      >
                        <span
                          className={cn(
                            "mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                            styles.chip,
                          )}
                        >
                          {nodeTypeLabel(node.type)}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-body-sm font-medium text-primary">
                            {node.label}
                          </span>
                          {node.subtype ? (
                            <span className="block truncate text-caption text-tertiary">
                              {node.subtype}
                            </span>
                          ) : null}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ) : null}
      </div>
    );
  },
);
