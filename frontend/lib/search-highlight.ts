/**
 * =============================================================================
 * File: search-highlight.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for keyword highlight in search snippets (UC3).
 * Responsibilities:
 *   - Split snippet into plain / highlight segments for safe React rendering
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - highlightSnippetSegments, formatRetrievalMethodLabel
 * Database/Table: N/A
 * Related Modules: features/search/SearchResults.tsx, scripts/test-search-ui.mjs
 * Important Notes: No HTML injection — returns text segments only.
 * =============================================================================
 */

import type { RetrievalMethod } from "@/types/search";

export type HighlightSegment = { text: string; highlight: boolean };

/** Split `snippet` into segments; tokens from `query` are marked highlight. */
export function highlightSnippetSegments(
  snippet: string,
  query: string,
): HighlightSegment[] {
  const text = snippet || "";
  const tokens = Array.from(
    new Set(
      (query || "")
        .toLowerCase()
        .split(/[^\p{L}\p{N}]+/u)
        .map((t) => t.trim())
        .filter((t) => t.length >= 2),
    ),
  );
  if (!text || tokens.length === 0) {
    return [{ text, highlight: false }];
  }

  const pattern = new RegExp(`(${tokens.map(escapeRegExp).join("|")})`, "giu");
  const parts = text.split(pattern);
  return parts
    .filter((p) => p.length > 0)
    .map((part) => ({
      text: part,
      highlight: tokens.some((t) => t.toLowerCase() === part.toLowerCase()),
    }));
}

export function formatRetrievalMethodLabel(method: RetrievalMethod): string {
  switch (method) {
    case "vector":
      return "Vector";
    case "bm25":
      return "BM25";
    case "knowledge_graph":
      return "Knowledge Graph";
    case "rerank":
      return "Rerank";
    default:
      return method;
  }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
