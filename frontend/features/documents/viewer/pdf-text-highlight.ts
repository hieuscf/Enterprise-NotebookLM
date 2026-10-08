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
 *   - HighlightOverlay.HighlightRect
 * Public Exports:
 *   - findSnippetRectsInTextContent
 * Database/Table: N/A
 * Related Modules: PDFViewer, ChunkNavigator, SnippetNavigator
 * Important Notes: Prefer these rects over whole-chunk bbox when snippet is a
 *   sub-span. Returns [] when confidence is insufficient (caller must not fake).
 * =============================================================================
 */

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
  for (const span of hitSpans) {
    if (
      current.length > 0 &&
      Math.abs(span.top - current[0].top) > (span.bottom - span.top) * 0.7
    ) {
      lines.push(current);
      current = [span];
    } else {
      current.push(span);
    }
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

function snippetVariants(snippet: string): string[] {
  const base = (snippet || "").trim();
  if (!base) return [];
  const out: string[] = [];
  const push = (value: string) => {
    const v = value.replace(/\s+/g, " ").trim();
    if (v && !out.includes(v)) out.push(v);
  };
  push(base);
  push(base.replace(/^[-*+•]\s+/, ""));
  push(base.replace(/^\d+[.)]\s+/, ""));
  push(base.replace(/^>\s+/, ""));
  for (const cur of [...out]) {
    push(cur.replace(/^[“”"']+/, "").replace(/[“”"']+$/, ""));
  }
  return out;
}

function locateSnippet(
  haystack: string,
  snippet: string,
): { start: number; length: number } | null {
  const variants = snippetVariants(snippet);
  let best: { start: number; length: number } | null = null;

  for (const needle of variants) {
    const exact = haystack.indexOf(needle);
    if (exact >= 0) {
      const hit = { start: exact, length: needle.length };
      if (!best || hit.length > best.length) best = hit;
      continue;
    }

    const ci = haystack.toLowerCase().indexOf(needle.toLowerCase());
    if (ci >= 0) {
      const hit = { start: ci, length: needle.length };
      if (!best || hit.length > best.length) best = hit;
      continue;
    }

    // Normalized whitespace match with accurate original-index mapping.
    // Never use length-ratio approximation — that paints the wrong span.
    const { norm: normHay, map } = normalizedIndexMap(haystack);
    const normNeedle = normalizeForMatch(needle);
    if (!normNeedle || normNeedle.length < 8 || map.length === 0) continue;
    const nidx = normHay.indexOf(normNeedle);
    if (nidx < 0) continue;
    const start = map[nidx] ?? 0;
    const endIdx = Math.min(map.length - 1, nidx + normNeedle.length - 1);
    const end = (map[endIdx] ?? start) + 1;
    if (end <= start) continue;
    const hit = { start, length: end - start };
    if (!best || hit.length > best.length) best = hit;
  }

  // Progressive prefix when the full citation is slightly longer than the page line.
  if (!best && variants[0] && variants[0].length > 40) {
    const primary = variants[0];
    for (let len = primary.length; len >= 32; len -= 8) {
      let head = primary.slice(0, len).trim();
      if (len < primary.length) {
        const cut = Math.max(head.lastIndexOf(" "), head.lastIndexOf("."));
        if (cut >= 32) head = head.slice(0, cut).trim();
      }
      if (head.length < 32) continue;
      const hit = locateSnippet(haystack, head);
      if (hit) return hit;
    }
  }

  return best;
}

function normalizeForMatch(value: string): string {
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

function clampPct(n: number, min = 0, max = 100): number {
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}
