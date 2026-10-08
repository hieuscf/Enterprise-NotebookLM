/**
 * =============================================================================
 * File: document-structure.ts
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Presentation-layer helpers over Canonical Blocks (no data mutation).
 * Responsibilities:
 *   - Strip Markdown markers for display without changing Canonical content
 *   - Conservative document-header grouping from existing block types
 *   - Table / list / figure / quote detection for semantic HTML
 *   - Map citation offsets from block.content → visible text nodes
 * Dependencies:
 *   - types/canonical
 * Public Exports:
 *   - displayHeadingText, headingMarkerPrefix, mapContentOffsetsToDisplay
 *   - splitDocumentHeader, parseMarkdownTable, parseListModel
 *   - parseFigure, classifyParagraphKind, isSafeMediaUrl
 * Database/Table: N/A
 * Related Modules: KnowledgeView, CanonicalBlock
 * Important Notes:
 *   - Canonical Markdown / block.content stay source of truth.
 *   - Helpers never merge blocks or rewrite heading text in the data model.
 *   - No document-specific (company) heuristics.
 * =============================================================================
 */

import type { CanonicalBlock } from "@/types/canonical";

const HEADING_MARKER_RE = /^(#{1,6})[ \t]+/;
const HR_RE = /^(?:-{3,}|\*{3,}|_{3,})\s*$/;
const FENCE_RE = /^```[\w+-]*[ \t]*\n([\s\S]*?)\n```[ \t]*$/;
const IMAGE_RE = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/;
const LIST_ITEM_RE = /^(\s*)(?:[-*+]|\d+[.)])\s+/;
const ORDERED_ITEM_RE = /^\s*\d+[.)]\s+/;
const TABLE_DELIM_RE = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;
const NUMERIC_CELL_RE = /^[+-]?(?:\d{1,3}(?:[.,]\d{3})*|\d+)(?:[.,]\d+)?%?$/;

export type HeaderSplit = {
  header: CanonicalBlock[];
  body: CanonicalBlock[];
  titleBlockId: string | null;
  subtitleBlockId: string | null;
};

export type ParsedTable = {
  headers: string[];
  rows: string[][];
  alignments: Array<"left" | "center" | "right">;
};

export type ListModel = {
  ordered: boolean;
  items: string[];
};

export type FigureModel = {
  src: string;
  alt: string;
  caption: string;
};

export type ParagraphKind = "paragraph" | "quote" | "rule" | "code";

/** Leading ATX heading marker (`# ` … `###### `), or empty string. */
export function headingMarkerPrefix(content: string): string {
  const match = (content ?? "").match(HEADING_MARKER_RE);
  return match ? match[0] : "";
}

/** Visible heading text — markers stripped for presentation only. */
export function displayHeadingText(content: string): string {
  return (content ?? "").replace(HEADING_MARKER_RE, "").replace(/\s+#+\s*$/, "").trim();
}

/**
 * Map locator offsets (into `block.content`) onto the text actually rendered.
 * Stays inside one block — never searches the rest of the document.
 *
 * List / heading / quote renderers strip markers, so raw content offsets must
 * not be applied blindly to `textContent` (that paints the wrong span).
 */
export function mapContentOffsetsToDisplay(
  content: string,
  displayText: string,
  start: number,
  end: number,
): { start: number; end: number } {
  if (end <= start) return { start: 0, end: 0 };
  if (displayText === content) {
    return clampRange(displayText.length, start, end);
  }

  const cited = content.slice(Math.max(0, start), Math.max(0, end));
  if (cited) {
    const exact = displayText.indexOf(cited);
    if (exact >= 0) {
      return { start: exact, end: exact + cited.length };
    }

    const candidates = [
      cited.replace(HEADING_MARKER_RE, "").replace(/^>\s?/gm, ""),
      cited.replace(LIST_ITEM_RE, "").replace(/\n(?:\s*)(?:[-*+]|\d+[.)])\s+/g, "\n"),
      cited
        .replace(HEADING_MARKER_RE, "")
        .replace(/^>\s?/gm, "")
        .replace(LIST_ITEM_RE, "")
        .replace(/\n(?:\s*)(?:[-*+]|\d+[.)])\s+/g, "\n"),
    ];
    for (const stripped of candidates) {
      if (!stripped || stripped === cited) continue;
      const idx = displayText.indexOf(stripped);
      if (idx >= 0) {
        return { start: idx, end: idx + stripped.length };
      }
      const soft = findNormalizedSpan(displayText, stripped);
      if (soft) return soft;
    }

    const softCited = findNormalizedSpan(displayText, cited);
    if (softCited) return softCited;
  }

  // Align content → display by walking both strings and skipping presentation-only markers.
  const mapped = mapViaPresentationAlignment(content, displayText, start, end);
  if (mapped) return mapped;

  const prefixLen = Math.max(0, content.length - displayText.length);
  if (content.endsWith(displayText) && prefixLen > 0) {
    return clampRange(displayText.length, start - prefixLen, end - prefixLen);
  }

  // Last resort: do not trust raw content offsets on a transformed display —
  // clamp only if lengths are close enough that the span is still meaningful.
  if (Math.abs(content.length - displayText.length) <= 4) {
    return clampRange(displayText.length, start, end);
  }
  return { start: 0, end: 0 };
}

/** Whitespace/punctuation-tolerant span search with accurate original offsets. */
function findNormalizedSpan(
  haystack: string,
  needle: string,
): { start: number; end: number } | null {
  const { norm: normHay, map } = normalizedIndexMap(haystack);
  const normNeedle = normalizeForMatch(needle);
  if (!normNeedle || normNeedle.length < 4 || map.length === 0) return null;
  const nidx = normHay.indexOf(normNeedle);
  if (nidx < 0) return null;
  const start = map[nidx] ?? 0;
  const endIdx = Math.min(map.length - 1, nidx + normNeedle.length - 1);
  const end = (map[endIdx] ?? start) + 1;
  return end > start ? { start, end } : null;
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

/**
 * Walk content and display in lockstep, skipping list/heading/quote markers
 * that are present in Canonical content but absent from rendered text.
 */
function mapViaPresentationAlignment(
  content: string,
  displayText: string,
  start: number,
  end: number,
): { start: number; end: number } | null {
  if (!content || !displayText || end <= start) return null;

  let di = 0;
  let displayStart = -1;
  let displayEnd = -1;
  let i = 0;

  const skipContentMarkers = (at: number): number => {
    let p = at;
    // ATX heading at line start
    const head = content.slice(p).match(/^(#{1,6})[ \t]+/);
    if (head && (p === 0 || content[p - 1] === "\n")) {
      return p + head[0].length;
    }
    // List marker at line start
    const list = content.slice(p).match(/^(\s*)(?:[-*+]|\d+[.)])\s+/);
    if (list && (p === 0 || content[p - 1] === "\n")) {
      return p + list[0].length;
    }
    // Blockquote marker
    const quote = content.slice(p).match(/^>\s?/);
    if (quote && (p === 0 || content[p - 1] === "\n")) {
      return p + quote[0].length;
    }
    return p;
  };

  while (i < content.length && di < displayText.length) {
    i = skipContentMarkers(i);
    if (i >= content.length) break;

    const c = content[i] ?? "";
    const d = displayText[di] ?? "";

    if (/\s/.test(c) && /\s/.test(d)) {
      if (i >= start && displayStart < 0) displayStart = di;
      if (i < end) displayEnd = di + 1;
      // Collapse whitespace runs on both sides.
      while (i < content.length && /\s/.test(content[i] ?? "")) i += 1;
      while (di < displayText.length && /\s/.test(displayText[di] ?? "")) di += 1;
      continue;
    }

    if (c.toLowerCase() === d.toLowerCase()) {
      if (i >= start && displayStart < 0) displayStart = di;
      if (i < end) displayEnd = di + 1;
      i += 1;
      di += 1;
      continue;
    }

    // Content has an extra character (marker remnant / punctuation) — skip it.
    if (!/\s/.test(c) && (i < content.length - 1)) {
      i += 1;
      continue;
    }
    break;
  }

  if (displayStart >= 0 && displayEnd > displayStart) {
    return clampRange(displayText.length, displayStart, displayEnd);
  }
  return null;
}

function clampRange(len: number, start: number, end: number): { start: number; end: number } {
  const s = Math.max(0, Math.min(start, len));
  const e = Math.max(s, Math.min(end, len));
  return { start: s, end: e };
}

/**
 * Conservative letterhead grouping: leading consecutive headings before the
 * first body block. Requires ≥2 headings so a lone H1 is not treated as a cover.
 */
export function splitDocumentHeader(
  blocks: CanonicalBlock[],
  documentTitle?: string | null,
): HeaderSplit {
  const empty: HeaderSplit = {
    header: [],
    body: blocks,
    titleBlockId: findTitleBlockId(blocks, documentTitle),
    subtitleBlockId: null,
  };
  if (blocks.length < 2) return empty;

  const header: CanonicalBlock[] = [];
  for (const block of blocks) {
    if (block.block_type !== "heading") break;
    const level = block.heading_level ?? 1;
    const text = displayHeadingText(block.content);
    if (level !== 1) break;
    if (text.length > 96) break;
    header.push(block);
    if (header.length >= 8) break;
  }

  if (header.length < 2) return empty;

  const next = blocks[header.length];
  if (
    next &&
    next.block_type === "heading" &&
    (next.heading_level ?? 2) >= 2 &&
    displayHeadingText(next.content).length <= 96
  ) {
    header.push(next);
  }

  const body = blocks.slice(header.length);
  const h1s = header.filter((b) => (b.heading_level ?? 1) === 1);
  const lastH1 = h1s[h1s.length - 1] ?? header[header.length - 1];
  const lastH1Index = header.findIndex((b) => b.id === lastH1.id);
  const maybeSubtitle = header[lastH1Index + 1];
  const subtitleBlockId =
    maybeSubtitle && (maybeSubtitle.heading_level ?? 2) >= 2 ? maybeSubtitle.id : null;

  return {
    header,
    body,
    titleBlockId: lastH1.id,
    subtitleBlockId,
  };
}

function findTitleBlockId(
  blocks: CanonicalBlock[],
  documentTitle?: string | null,
): string | null {
  const needle = normalizeLabel(documentTitle ?? "");
  if (needle) {
    const match = blocks.find(
      (b) => b.block_type === "heading" && normalizeLabel(displayHeadingText(b.content)) === needle,
    );
    if (match) return match.id;
  }
  const firstHeading = blocks.find((b) => b.block_type === "heading");
  return firstHeading?.id ?? null;
}

function normalizeLabel(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

export function parseMarkdownTable(content: string): ParsedTable | null {
  const lines = (content ?? "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length < 2) return null;
  if (!lines[0].includes("|")) return null;
  if (!TABLE_DELIM_RE.test(lines[1])) return null;

  const headers = splitTableRow(lines[0]);
  if (headers.length < 1) return null;
  const alignments = splitTableRow(lines[1]).map(alignmentFromDelimiter);
  const rows = lines.slice(2).map(splitTableRow);
  const width = headers.length;
  const paddedAlign: Array<"left" | "center" | "right"> = Array.from(
    { length: width },
    (_, i) => alignments[i] ?? "left",
  );

  for (let col = 0; col < width; col += 1) {
    if (paddedAlign[col] !== "left") continue;
    const values = rows.map((r) => r[col] ?? "").filter((c) => c.length > 0);
    if (values.length > 0 && values.every((c) => NUMERIC_CELL_RE.test(c))) {
      paddedAlign[col] = "right";
    }
  }

  return {
    headers,
    alignments: paddedAlign,
    rows: rows.map((r) => {
      const next = r.slice(0, width);
      while (next.length < width) next.push("");
      return next;
    }),
  };
}

function splitTableRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

function alignmentFromDelimiter(cell: string): "left" | "center" | "right" {
  const t = cell.trim();
  const left = t.startsWith(":");
  const right = t.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  return "left";
}

export function parseListModel(content: string): ListModel {
  const lines = (content ?? "").split(/\r?\n/);
  const items: string[] = [];
  let ordered = false;
  for (const line of lines) {
    if (!line.trim()) continue;
    if (ORDERED_ITEM_RE.test(line)) ordered = true;
    items.push(line.replace(LIST_ITEM_RE, "").trimEnd());
  }
  return { ordered, items: items.length ? items : [(content ?? "").trim()] };
}

export function parseFigure(content: string): FigureModel | null {
  const match = (content ?? "").match(IMAGE_RE);
  if (!match) return null;
  const src = match[2]?.trim() ?? "";
  if (!isSafeMediaUrl(src)) return null;
  const alt = match[1]?.trim() ?? "";
  const title = match[3]?.trim() ?? "";
  return { src, alt, caption: title || alt };
}

export function classifyParagraphKind(content: string): ParagraphKind {
  const trimmed = (content ?? "").trim();
  if (!trimmed) return "paragraph";
  if (HR_RE.test(trimmed)) return "rule";
  if (FENCE_RE.test(trimmed)) return "code";
  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length > 0 && lines.every((l) => l.trim().startsWith(">"))) return "quote";
  return "paragraph";
}

export function displayQuoteText(content: string): string {
  return (content ?? "")
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*>\s?/, ""))
    .join("\n")
    .trim();
}

export function displayCodeText(content: string): string {
  const match = (content ?? "").trim().match(FENCE_RE);
  return match ? match[1] : (content ?? "");
}

export function isSafeMediaUrl(url: string): boolean {
  const t = (url ?? "").trim();
  if (!t) return false;
  const lower = t.toLowerCase();
  if (lower.startsWith("javascript:") || lower.startsWith("vbscript:")) return false;
  if (lower.startsWith("data:")) return lower.startsWith("data:image/");
  return (
    lower.startsWith("https:") ||
    lower.startsWith("http:") ||
    lower.startsWith("/") ||
    lower.startsWith("./") ||
    lower.startsWith("../")
  );
}

export function isSafeHref(url: string): boolean {
  const t = (url ?? "").trim().toLowerCase();
  if (!t) return false;
  if (t.startsWith("javascript:") || t.startsWith("vbscript:") || t.startsWith("data:")) {
    return false;
  }
  return t.startsWith("https:") || t.startsWith("http:") || t.startsWith("mailto:") || t.startsWith("/");
}

/** True when the API fell back to a single raw-Markdown paragraph. */
export function isRawMarkdownBlob(blocks: CanonicalBlock[]): boolean {
  if (blocks.length !== 1) return false;
  const block = blocks[0];
  if (block.block_type !== "paragraph") return false;
  const c = block.content ?? "";
  return HEADING_MARKER_RE.test(c) && /\n#{1,6}\s+/m.test(c);
}
