/**
 * =============================================================================
 * File: pdf-text-highlight.ts
 * Module/Service: Document Viewer / Citation
 * Layer: UI
 * Purpose: Resolve citation text_snippet → PDF.js text-layer rectangles.
 * Responsibilities:
 *   - Match snippet against page.getTextContent() items (exact → CI → normalized)
 *   - Return CSS-percentage HighlightRect[] for multi-line spans
 * Dependencies:
 *   - HighlightOverlay.HighlightRect; citation-snippet-match.normalizeSnippet
 * Public Exports:
 *   - findSnippetRectsInTextContent
 * Database/Table: N/A
 * Related Modules: PDFViewer, ChunkNavigator, SnippetNavigator
 * Important Notes: Prefer these rects over whole-chunk bbox when snippet is a
 *   sub-span. Returns [] when confidence is insufficient (caller must not fake).
 * =============================================================================
 */

import { normalizeSnippet } from "@/features/chat/citation/citation-snippet-match";
import type { HighlightRect } from "@/features/documents/viewer/HighlightOverlay";

type TextItemLike = {
  str?: string;
  transform?: number[] | Float32Array;
  width?: number;
  height?: number;
};

type TextContentLike = {
  items: TextItemLike[];
};

type CharSpan = {
  charStart: number;
  charEnd: number;
  left: number;
  top: number;
  right: number;
  bottom: number;
};

/**
 * Find highlight rectangles for `snippet` inside a PDF.js text content payload.
 * Coordinates are percentages of the rendered viewport (pageWidth × pageHeight).
 */
export function findSnippetRectsInTextContent(
  textContent: TextContentLike | null | undefined,
  snippet: string,
  pageWidth: number,
  pageHeight: number,
): HighlightRect[] {
  if (!textContent?.items?.length || !snippet.trim()) return [];
  if (pageWidth <= 0 || pageHeight <= 0) return [];

  const spans: CharSpan[] = [];
  let joined = "";

  for (const item of textContent.items) {
    const str = typeof item.str === "string" ? item.str : "";
    if (!str) continue;
    const transform = item.transform;
    if (!transform || transform.length < 6) continue;

    const tx = Number(transform[4]);
    const ty = Number(transform[5]);
    const fontHeight = Math.abs(Number(transform[3]) || Number(item.height) || 10);
    const width = Number(item.width) || Math.max(1, str.length * fontHeight * 0.5);

    // PDF user space (origin bottom-left) → canvas/CSS (origin top-left).
    const left = tx;
    const top = pageHeight - ty - fontHeight;
    const right = left + width;
    const bottom = top + fontHeight;

    const charStart = joined.length;
    joined += str;
    const charEnd = joined.length;
    spans.push({ charStart, charEnd, left, top, right, bottom });
    // Soft space between PDF text items (common when items are word-split).
    joined += " ";
  }

  if (!joined.trim()) return [];

  const match = locateSnippet(joined, snippet);
  if (!match) return [];

  const hitSpans = spans.filter(
    (s) => s.charEnd > match.start && s.charStart < match.start + match.length,
  );
  if (hitSpans.length === 0) return [];

  // Merge adjacent spans on roughly the same line into fewer rects.
  const lines: CharSpan[][] = [];
  let current: CharSpan[] = [];
  let lastBottom = -Infinity;
  for (const span of hitSpans) {
    if (current.length === 0 || Math.abs(span.top - lastBottom) < span.bottom - span.top) {
      // Same visual line if vertical centers are close.
      if (
        current.length > 0 &&
        Math.abs(span.top - current[0].top) > (span.bottom - span.top) * 0.7
      ) {
        lines.push(current);
        current = [span];
      } else {
        current.push(span);
      }
    } else {
      lines.push(current);
      current = [span];
    }
    lastBottom = span.top;
  }
  if (current.length) lines.push(current);

  const rects: HighlightRect[] = [];
  for (const line of lines) {
    const left = Math.min(...line.map((s) => s.left));
    const top = Math.min(...line.map((s) => s.top));
    const right = Math.max(...line.map((s) => s.right));
    const bottom = Math.max(...line.map((s) => s.bottom));
    const width = right - left;
    const height = bottom - top;
    if (width <= 0 || height <= 0) continue;
    rects.push({
      left: clampPct((left / pageWidth) * 100),
      top: clampPct((top / pageHeight) * 100),
      width: clampPct((width / pageWidth) * 100, 1, 100),
      height: clampPct((height / pageHeight) * 100, 1, 100),
    });
  }
  return rects;
}

function locateSnippet(
  haystack: string,
  snippet: string,
): { start: number; length: number } | null {
  const exact = haystack.indexOf(snippet);
  if (exact >= 0) return { start: exact, length: snippet.length };

  const ci = haystack.toLowerCase().indexOf(snippet.toLowerCase());
  if (ci >= 0) return { start: ci, length: snippet.length };

  // Normalized whitespace match — map back approximately via ratio.
  const normHay = normalizeSnippet(haystack);
  const normSnip = normalizeSnippet(snippet);
  if (!normSnip || normSnip.length < 8) return null;
  const normIdx = normHay.indexOf(normSnip);
  if (normIdx < 0) return null;

  const ratio = haystack.length / Math.max(1, normHay.length);
  const start = Math.max(0, Math.floor(normIdx * ratio));
  const length = Math.max(snippet.length, Math.ceil(normSnip.length * ratio));
  if (start >= haystack.length) return null;
  return { start, length: Math.min(length, haystack.length - start) };
}

function clampPct(n: number, min = 0, max = 100): number {
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}
