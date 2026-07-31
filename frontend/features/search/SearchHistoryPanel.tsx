/**
 * =============================================================================
 * File: SearchHistoryPanel.tsx
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Current-user search history list; click to re-run a query (UC3).
 * Responsibilities:
 *   - Render history rows; emit onReplay(query, filters)
 * Dependencies:
 *   - types/search
 * Public Exports:
 *   - SearchHistoryPanel
 * Database/Table: N/A
 * Related Modules: features/search/SearchView.tsx, hooks/useSearchHistory
 * Important Notes: Empty list is valid — not an error.
 * =============================================================================
 */

"use client";

import { Clock3, RotateCcw } from "lucide-react";

import { cn } from "@/lib/utils";
import type { SearchFilters, SearchHistoryItem } from "@/types/search";

type Props = {
  items: SearchHistoryItem[];
  loading: boolean;
  error: string | null;
  onReplay: (queryText: string, filters?: SearchFilters | null) => void;
};

export function SearchHistoryPanel({ items, loading, error, onReplay }: Props) {
  return (
    <section className="rounded-lg border border-border-default bg-surface">
      <header className="flex items-center gap-2 border-b border-border-default px-4 py-3">
        <Clock3 className="h-4 w-4 text-tertiary" aria-hidden />
        <h2 className="text-body-sm font-semibold text-primary">Lịch sử tìm kiếm</h2>
      </header>

      {loading ? (
        <div className="space-y-2 p-4" aria-busy>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-elevated" />
          ))}
        </div>
      ) : error ? (
        <p className="px-4 py-6 text-body-sm text-danger">{error}</p>
      ) : items.length === 0 ? (
        <p className="px-4 py-6 text-body-sm text-secondary">
          Chưa có lịch sử. Các truy vấn của bạn sẽ xuất hiện tại đây.
        </p>
      ) : (
        <ul className="divide-y divide-border-default">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() =>
                  onReplay(item.query_text, (item.filters as SearchFilters) ?? null)
                }
                className={cn(
                  "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors",
                  "hover:bg-elevated/50 focus:outline-none focus:bg-elevated/50",
                )}
              >
                <RotateCcw className="mt-0.5 h-3.5 w-3.5 shrink-0 text-tertiary" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-body-sm font-medium text-primary">
                    {item.query_text}
                  </p>
                  <p className="mt-0.5 text-caption text-tertiary">
                    {formatDate(item.created_at)} · {item.results_count} kết quả
                  </p>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
