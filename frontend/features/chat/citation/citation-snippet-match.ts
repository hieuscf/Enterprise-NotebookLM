/**
 * =============================================================================
 * File: citation-snippet-match.ts
 * Module/Service: Chat Service / Document Viewer
 * Layer: UI
 * Purpose: Match citation text_snippet to document chunks for highlight.
 * Responsibilities:
 *   - Exact → case-insensitive → whitespace-normalized match against chunk content
 *   - Map normalized hits back to original character offsets accurately
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
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function normalizedIndexMap(value: string): { norm: string; map: number[] } {
  const map: number[] = [];
  let norm = "";
  let prevSpace = true;
  for (let i = 0; i < value.length; i += 1) {
    let ch = value[i] ?? "";
    if (ch === "\u2018" || ch === "\u2019") ch = "'";
    if (ch === "\u201c" || ch === "\u201d") ch = '"';
    if (ch === "\u00a0" || /\s/.test(ch)) {
      if (!prevSpace && norm.length > 0) {
        norm += " ";
        map.push(i);
      }
      prevSpace = true;
      continue;
    }
    norm += ch.toLowerCase();
    map.push(i);
    prevSpace = false;
  }
  while (norm.endsWith(" ")) {
    norm = norm.slice(0, -1);
    map.pop();
  }
  return { norm, map };
}

/** Find start index of snippet in haystack (exact → CI → normalized with real offsets). */
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

  const { norm: normHay, map } = normalizedIndexMap(haystack);
  const normSnip = normalizeSnippet(snippet);
  if (!normSnip || map.length === 0) return null;
  const normIdx = normHay.indexOf(normSnip);
  if (normIdx < 0) return null;

  const start = map[normIdx] ?? 0;
  const endIdx = Math.min(map.length - 1, normIdx + normSnip.length - 1);
  const end = (map[endIdx] ?? start) + 1;
  if (end <= start) return null;
  return { index: start, length: end - start };
}

export function findChunkForSnippet(
  chunks: DocumentChunk[],
  snippet: string,
): DocumentChunk | null {
  if (!snippet.trim() || chunks.length === 0) return null;

  // Prefer exact / case-insensitive / normalized containment.
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
