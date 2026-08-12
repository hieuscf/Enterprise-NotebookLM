/**
 * =============================================================================
 * File: citation-snippet-match.ts
 * Module/Service: Chat Service / Document Viewer
 * Layer: UI
 * Purpose: Match citation text_snippet to document chunks for highlight.
 * Responsibilities:
 *   - Exact → whitespace-normalized → case-insensitive match against chunk content
 * Dependencies:
 *   - types/documents
 * Public Exports:
 *   - normalizeSnippet, findChunkForSnippet, matchSnippetInText
 * Database/Table: N/A
 * Related Modules: SnippetNavigator, DocumentViewer
 * Important Notes: Never mutates citation text; failure returns null (no crash).
 * =============================================================================
 */

import type { DocumentChunk } from "@/types/documents";

export function normalizeSnippet(value: string): string {
  return (value || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Find start index of snippet in haystack (exact → normalized → case-insensitive). */
export function matchSnippetInText(
  haystack: string,
  snippet: string,
): { index: number; length: number } | null {
  if (!haystack || !snippet) return null;
  const exact = haystack.indexOf(snippet);
  if (exact >= 0) return { index: exact, length: snippet.length };

  const lowerHay = haystack.toLowerCase();
  const lowerSnip = snippet.toLowerCase();
  const ci = lowerHay.indexOf(lowerSnip);
  if (ci >= 0) return { index: ci, length: snippet.length };

  const normHay = normalizeSnippet(haystack);
  const normSnip = normalizeSnippet(snippet);
  if (!normSnip) return null;
  const normIdx = normHay.indexOf(normSnip);
  if (normIdx < 0) return null;

  // Approximate: map normalized index back poorly — still useful for chunk pick.
  return { index: Math.min(normIdx, Math.max(0, haystack.length - 1)), length: snippet.length };
}

export function findChunkForSnippet(
  chunks: DocumentChunk[],
  snippet: string,
): DocumentChunk | null {
  if (!snippet.trim() || chunks.length === 0) return null;

  // Prefer exact / case-insensitive containment.
  for (const chunk of chunks) {
    if (matchSnippetInText(chunk.content || "", snippet)) {
      return chunk;
    }
  }

  // Fuzzy: longest shared token overlap (≥3 tokens of length ≥3).
  const tokens = normalizeSnippet(snippet)
    .split(" ")
    .filter((t) => t.length >= 3);
  if (tokens.length < 2) return null;

  let best: DocumentChunk | null = null;
  let bestScore = 0;
  for (const chunk of chunks) {
    const content = normalizeSnippet(chunk.content || "");
    if (!content) continue;
    let score = 0;
    for (const t of tokens) {
      if (content.includes(t)) score += 1;
    }
    const ratio = score / tokens.length;
    if (ratio > bestScore && ratio >= 0.55) {
      bestScore = ratio;
      best = chunk;
    }
  }
  return best;
}
