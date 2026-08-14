/**
 * =============================================================================
 * File: section-extraction-adapter.ts
 * Module/Service: Chat Service (Web App)
 * Layer: Adapter
 * Purpose: Turn section_extraction answer text + citations into a document
 *          outline render model (no markdown ordered lists).
 * Responsibilities:
 *   - Parse flat answer lines (including legacy "1. 4.1 Title" lists)
 *   - Group duplicate subsections; merge body in encounter / chunk_index order
 *   - Normalize HTML tables, strip heading echoes, dedupe near-identical paragraphs
 *   - Build an arbitrary-depth heading tree from dotted section numbers
 * Dependencies:
 *   - CitationViewModel
 * Public Exports:
 *   - buildSectionExtractionModel, parseHtmlTableFragment, formatSectionHeading
 *   - peelHeadingPrefix, isDocumentSectionNumber, isHeaderFooterArtifact
 * Database/Table: N/A
 * Related Modules: SectionExtractionAnswer, AssistantBubble
 * Important Notes:
 *   - Presentation only. Does not change retrieval, route_type, or LLM counts.
 *   - Section numbers are document identifiers, never UI list indexes.
 * =============================================================================
 */

import type { CitationViewModel } from "@/features/chat/citation/citation-types";

export type SectionExtractionItemInput = {
  documentId?: string;
  chunkId?: string;
  pageNumber?: number;
  sectionNumber?: string;
  sectionTitle?: string;
  parentSectionNumber?: string;
  headingLevel?: number;
  chunkIndex: number;
  content: string;
};

export type SectionTable = {
  headers: string[];
  rows: string[][];
};

export type SectionBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "bullets"; items: string[] }
  | { kind: "table"; table: SectionTable };

export type SectionNode = {
  key: string;
  number: string | null;
  title: string;
  depth: number;
  chunkIds: string[];
  citations: CitationViewModel[];
  blocks: SectionBlock[];
  children: SectionNode[];
};

export type SectionExtractionModel = {
  nodes: SectionNode[];
};

type FlatSection = {
  documentId: string;
  number: string | null;
  title: string;
  parentNumber: string | null;
  chunkIndex: number;
  chunkIds: string[];
  bodyLines: string[];
  order: number;
};

const SECTION_NUMBER_RE = /^\d+(?:\.\d+)*$/;
const WRAPPED_SECTION_RE = /^(?:\d+)[.)]\s+(\d+(?:\.\d+)+)(?:[.)])?\s+(.+)$/;
const DIRECT_SECTION_RE = /^(\d+(?:\.\d+)*)(?:[.)])?\s+(.+)$/;
const ATX_HEADING_RE = /^#{1,6}\s+/;
const BULLET_PREFIX_RE = /^\s*(?:[-*+]|•)\s+/;
const INTRO_SUFFIX_RE = /\s+(?:gồm|includes)\s*:?\s*$/i;
const HTML_TAG_RE = /<\/?[a-zA-Z][^>]*>/;
const TABLE_ROW_OPEN_RE = /<tr[\s>]/i;
const ARTIFACT_ONLY_RE =
  /^(?:<\/?(?:tr|td|th|table|thead|tbody|tfoot)(?:\s[^>]*)?>|&lt;\/?(?:tr|td|th|table|thead|tbody|tfoot)(?:\s[^>]*)?&gt;)+$/i;
const GFM_ROW_RE = /^\s*\|.+\|\s*$/;
const GFM_DELIM_RE = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;

export function formatSectionHeading(number: string | null, title: string): string {
  const n = (number ?? "").trim();
  const t = (title ?? "").trim();
  if (n && t) return n.includes(".") ? `${n} ${t}` : `${n}. ${t}`;
  return n || t;
}

export function parentSectionNumber(number: string | null | undefined): string | null {
  if (!number || !number.includes(".")) return null;
  return number.slice(0, number.lastIndexOf("."));
}

export function compareSectionNumbers(a: string | null, b: string | null): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  const pa = a.split(".").map((p) => Number.parseInt(p, 10));
  const pb = b.split(".").map((p) => Number.parseInt(p, 10));
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i += 1) {
    if (i >= pa.length) return -1;
    if (i >= pb.length) return 1;
    const da = Number.isFinite(pa[i]) ? pa[i] : 0;
    const db = Number.isFinite(pb[i]) ? pb[i] : 0;
    if (da !== db) return da - db;
  }
  return 0;
}

export function unescapeHtmlEntities(text: string): string {
  return (text ?? "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&amp;/gi, "&");
}

export function normalizeFingerprint(text: string): string {
  return (text ?? "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Outline ids like 4 / 4.1 / 2.1.1 — not dates (30.06.2026) or thousands (100.000). */
export function isDocumentSectionNumber(value: string): boolean {
  if (!SECTION_NUMBER_RE.test(value)) return false;
  const rawParts = value.split(".");
  const parts = rawParts.map((p) => Number.parseInt(p, 10));
  if (parts.some((p) => !Number.isFinite(p) || p < 0)) return false;
  if (parts.length === 0 || parts.length > 8) return false;
  if (parts.length === 3) {
    const a = parts[0];
    const b = parts[1];
    const c = parts[2];
    const dmy = a >= 1 && a <= 31 && b >= 1 && b <= 12 && c >= 1900 && c <= 2100;
    const ymd = a >= 1900 && a <= 2100 && b >= 1 && b <= 12 && c >= 1 && c <= 31;
    if (dmy || ymd) return false;
  }
  if (
    rawParts.length >= 2 &&
    rawParts[0].length <= 3 &&
    rawParts.slice(1).every((p) => p.length === 3)
  ) {
    return false;
  }
  if (parts.some((p) => p > 99)) return false;
  return true;
}

export function stripMarkdownEmphasis(text: string): string {
  return (text ?? "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .trim();
}

export function isHeaderFooterArtifact(line: string): boolean {
  const raw = unescapeHtmlEntities(line).trim();
  if (!raw) return true;
  const text = stripMarkdownEmphasis(stripTags(raw));
  const fp = normalizeFingerprint(text);
  if (!fp) return true;
  if (/^(trang|page)\s*\d+(\s*\/\s*\d+)?$/i.test(text)) return true;
  if (/^\d+\s*\/\s*\d+$/.test(text)) return true;
  if (/^(confidential|nội bộ|internal use only)$/i.test(text)) return true;

  const wrappedEmphasis = /^(?:\*\*|__).+(?:\*\*|__)$/.test(raw);
  const short = text.length <= 80;
  const noSentencePunct = !/[.!?…]/.test(text);
  const companyBanner =
    /\b(công ty|jsc|ltd|pte\.?\s*ltd|llc|llp|tnhh|cổ phần|corporation|incorporated|group|tập đoàn)\b/i.test(
      text,
    );
  const narrative =
    /\b(thành lập|mua|bán|đầu tư|lĩnh vực|vốn góp|theo|đã|được|vào ngày|là cung cấp)\b/i.test(
      text,
    );

  if (wrappedEmphasis && short && companyBanner) return true;
  if (short && noSentencePunct && companyBanner && !narrative && text.split(/\s+/).length <= 12) {
    return true;
  }
  return false;
}

function headingFingerprints(number: string | null, title: string): Set<string> {
  const set = new Set<string>();
  const t = title.trim();
  if (t) set.add(normalizeFingerprint(t));
  if (number && t) {
    set.add(normalizeFingerprint(`${number} ${t}`));
    set.add(normalizeFingerprint(`${number}. ${t}`));
    set.add(normalizeFingerprint(formatSectionHeading(number, t)));
  }
  return set;
}

/** Drop an exact heading echo; if the line continues past the heading, keep the remainder. */
export function peelHeadingPrefix(
  line: string,
  number: string | null,
  title: string,
): string | null {
  const cleaned = unescapeHtmlEntities(line)
    .replace(ATX_HEADING_RE, "")
    .replace(BULLET_PREFIX_RE, "")
    .trim();
  if (!cleaned) return null;
  const fp = normalizeFingerprint(cleaned);
  if (!fp) return null;
  const prints = headingFingerprints(number, title);
  for (const heading of prints) {
    if (!heading) continue;
    if (fp === heading) return null;
    if (fp.startsWith(`${heading} `) || fp.startsWith(heading)) {
      const restFp = fp.slice(heading.length).trim();
      if (!restFp) return null;
      for (let i = 0; i < cleaned.length; i += 1) {
        const rest = cleaned.slice(i).replace(/^[\s.:;,\-–—]+/, "").trim();
        if (normalizeFingerprint(rest) === restFp) return rest || null;
      }
      return null;
    }
  }
  return cleaned;
}

function stripTags(html: string): string {
  return unescapeHtmlEntities(html)
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<\/?[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isArtifactOnly(line: string): boolean {
  const trimmed = unescapeHtmlEntities(line).replace(/\s+/g, "");
  if (!trimmed) return true;
  return ARTIFACT_ONLY_RE.test(trimmed) && !/[^\s<>\/a-zA-Z=&;]/i.test(stripTags(line));
}

function looksLikeTableLine(line: string): boolean {
  const raw = unescapeHtmlEntities(line).trim();
  if (!raw) return false;
  if (TABLE_ROW_OPEN_RE.test(raw) || /<t[dh][\s>]/i.test(raw)) return true;
  if (GFM_ROW_RE.test(raw) || GFM_DELIM_RE.test(raw)) return true;
  return false;
}

export function parseHtmlTableFragment(html: string): SectionTable | null {
  const source = unescapeHtmlEntities(html ?? "");
  if (!TABLE_ROW_OPEN_RE.test(source) && !/<t[dh][\s>]/i.test(source)) return null;

  const rows: Array<{ header: boolean; cells: string[] }> = [];
  const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let match: RegExpExecArray | null = trRe.exec(source);
  while (match) {
    const inner = match[1] ?? "";
    const cells: string[] = [];
    let header = false;
    const cellRe = /<t(h|d)[^>]*>([\s\S]*?)<\/t\1>/gi;
    let cellMatch: RegExpExecArray | null = cellRe.exec(inner);
    while (cellMatch) {
      if ((cellMatch[1] ?? "").toLowerCase() === "h") header = true;
      cells.push(stripTags(cellMatch[2] ?? ""));
      cellMatch = cellRe.exec(inner);
    }
    if (cells.length > 0) rows.push({ header, cells });
    match = trRe.exec(source);
  }

  if (rows.length === 0) {
    const loose: string[] = [];
    const cellRe = /<t(h|d)[^>]*>([\s\S]*?)<\/t\1>/gi;
    let cellMatch: RegExpExecArray | null = cellRe.exec(source);
    let header = false;
    while (cellMatch) {
      if ((cellMatch[1] ?? "").toLowerCase() === "h") header = true;
      loose.push(stripTags(cellMatch[2] ?? ""));
      cellMatch = cellRe.exec(source);
    }
    if (loose.length > 0) rows.push({ header, cells: loose });
  }

  if (rows.length === 0) return null;

  const width = Math.max(...rows.map((r) => r.cells.length), 1);
  const padded = rows.map((r) => {
    const cells = r.cells.slice(0, width);
    while (cells.length < width) cells.push("");
    return { ...r, cells };
  });

  const headerRows = padded.filter((r) => r.header);
  const bodyRows = padded.filter((r) => !r.header);
  let headers: string[];
  let data: string[][];

  if (headerRows.length >= 1) {
    headers = headerRows[0].cells;
    if (headerRows.length > 1) {
      const extra = headerRows.slice(1).map((r) => r.cells);
      data = [...extra, ...bodyRows.map((r) => r.cells)];
    } else {
      data = bodyRows.map((r) => r.cells);
    }
  } else {
    headers = padded[0].cells;
    data = padded.slice(1).map((r) => r.cells);
  }

  const meaningful = headers.some((h) => h.length > 0) || data.some((row) => row.some((c) => c.length > 0));
  if (!meaningful) return null;
  return { headers, rows: data };
}

function parseGfmTable(lines: string[]): SectionTable | null {
  if (lines.length < 2 || !GFM_DELIM_RE.test(lines[1])) return null;
  const split = (line: string): string[] => {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|")) s = s.slice(0, -1);
    return s.split("|").map((c) => c.trim());
  };
  const headers = split(lines[0]);
  if (headers.length < 1) return null;
  const rows = lines.slice(2).filter((l) => !GFM_DELIM_RE.test(l)).map(split);
  const width = headers.length;
  return {
    headers,
    rows: rows.map((r) => {
      const next = r.slice(0, width);
      while (next.length < width) next.push("");
      return next;
    }),
  };
}

function parseHeadingLine(
  rawLine: string,
): { number: string; title: string; wrapped: boolean } | null {
  let line = unescapeHtmlEntities(rawLine).replace(ATX_HEADING_RE, "").trim();
  line = line.replace(BULLET_PREFIX_RE, "").trim();
  if (!line) return null;

  const wrapped = line.match(WRAPPED_SECTION_RE);
  if (wrapped?.[1] && wrapped[2]) {
    return {
      number: wrapped[1],
      title: wrapped[2].replace(INTRO_SUFFIX_RE, "").trim(),
      wrapped: true,
    };
  }

  const direct = line.match(DIRECT_SECTION_RE);
  if (direct?.[1] && direct[2]) {
    return {
      number: direct[1],
      title: direct[2].replace(INTRO_SUFFIX_RE, "").trim(),
      wrapped: false,
    };
  }
  return null;
}

function isSectionHeading(
  parsed: { number: string; title: string; wrapped: boolean },
  hasRoot: boolean,
): boolean {
  if (!isDocumentSectionNumber(parsed.number)) return false;
  if (parsed.wrapped) return true;
  if (parsed.number.includes(".")) return true;
  if (!hasRoot) return true;
  if (parsed.title.length >= 12 && parsed.title === parsed.title.toUpperCase()) return true;
  return false;
}

export function stripHeadingFromBody(
  number: string | null,
  title: string,
  lines: string[],
): string[] {
  const kept: string[] = [];
  for (const line of lines) {
    const remainder = peelHeadingPrefix(line, number, title);
    if (!remainder) continue;
    if (isHeaderFooterArtifact(remainder)) continue;
    kept.push(remainder);
  }
  return kept;
}

function isNearDuplicate(a: string, b: string): boolean {
  const fa = normalizeFingerprint(a);
  const fb = normalizeFingerprint(b);
  if (!fa || !fb) return false;
  if (fa === fb) return true;
  const shorter = fa.length <= fb.length ? fa : fb;
  const longer = fa.length <= fb.length ? fb : fa;
  if (shorter.length < 24) return false;
  return longer.startsWith(shorter) && shorter.length / longer.length >= 0.9;
}

export function dedupeParagraphs(texts: string[]): string[] {
  const kept: string[] = [];
  for (const text of texts) {
    const trimmed = text.trim();
    if (!trimmed) continue;
    if (kept.some((prev) => isNearDuplicate(prev, trimmed))) continue;
    kept.push(trimmed);
  }
  return kept;
}

function toBlocks(lines: string[]): SectionBlock[] {
  const blocks: SectionBlock[] = [];
  let i = 0;

  const flushParagraphs = (buffer: string[]) => {
    const paras = dedupeParagraphs(
      buffer
        .map((text) => stripMarkdownEmphasis(text))
        .filter((text) => text && !isHeaderFooterArtifact(text)),
    );
    for (const text of paras) {
      const last = blocks[blocks.length - 1];
      if (last?.kind === "paragraph" && isNearDuplicate(last.text, text)) continue;
      blocks.push({ kind: "paragraph", text });
    }
  };

  while (i < lines.length) {
    const line = lines[i]?.trim() ?? "";
    if (!line || isArtifactOnly(line) || isHeaderFooterArtifact(line)) {
      i += 1;
      continue;
    }

    if (looksLikeTableLine(line) && TABLE_ROW_OPEN_RE.test(unescapeHtmlEntities(line))) {
      const htmlLines: string[] = [];
      while (i < lines.length && (looksLikeTableLine(lines[i] ?? "") || isArtifactOnly(lines[i] ?? ""))) {
        if (!isArtifactOnly(lines[i] ?? "") || TABLE_ROW_OPEN_RE.test(unescapeHtmlEntities(lines[i] ?? ""))) {
          htmlLines.push(lines[i] ?? "");
        }
        i += 1;
      }
      const table = parseHtmlTableFragment(htmlLines.join(""));
      if (table) {
        blocks.push({ kind: "table", table });
        continue;
      }
      flushParagraphs(htmlLines.map((l) => stripTags(l)).filter(Boolean));
      continue;
    }

    if (GFM_ROW_RE.test(line)) {
      const gfm: string[] = [];
      while (i < lines.length && (GFM_ROW_RE.test(lines[i] ?? "") || GFM_DELIM_RE.test(lines[i] ?? ""))) {
        gfm.push(lines[i] ?? "");
        i += 1;
      }
      const table = parseGfmTable(gfm);
      if (table) {
        blocks.push({ kind: "table", table });
        continue;
      }
    }

    if (BULLET_PREFIX_RE.test(lines[i] ?? "")) {
      const items: string[] = [];
      while (i < lines.length && BULLET_PREFIX_RE.test(lines[i] ?? "")) {
        const item = (lines[i] ?? "").replace(BULLET_PREFIX_RE, "").trim();
        if (item && !isArtifactOnly(item) && !HTML_TAG_RE.test(item) && !isHeaderFooterArtifact(item)) {
          items.push(stripMarkdownEmphasis(item));
        }
        i += 1;
      }
      const unique = dedupeParagraphs(items);
      if (unique.length > 0) blocks.push({ kind: "bullets", items: unique });
      continue;
    }

    const para: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() &&
      !looksLikeTableLine(lines[i] ?? "") &&
      !BULLET_PREFIX_RE.test(lines[i] ?? "")
    ) {
      const cleaned = (lines[i] ?? "").replace(BULLET_PREFIX_RE, "").trim();
      if (
        cleaned &&
        !isArtifactOnly(cleaned) &&
        !isHeaderFooterArtifact(cleaned) &&
        !/^<\/?(?:tr|td|th)\b/i.test(unescapeHtmlEntities(cleaned))
      ) {
        para.push(
          HTML_TAG_RE.test(cleaned)
            ? stripTags(cleaned)
            : stripMarkdownEmphasis(cleaned),
        );
      }
      i += 1;
    }
    flushParagraphs(para);
  }

  return blocks;
}

function parseContentToFlat(content: string): FlatSection[] {
  const lines = (content ?? "").split(/\r?\n/);
  const items: FlatSection[] = [];
  let order = 0;
  let hasRoot = false;

  const startItem = (number: string, title: string): FlatSection => {
    const item: FlatSection = {
      documentId: "",
      number,
      title,
      parentNumber: parentSectionNumber(number),
      chunkIndex: order,
      chunkIds: [],
      bodyLines: [],
      order,
    };
    items.push(item);
    order += 1;
    hasRoot = true;
    return item;
  };

  for (const raw of lines) {
    const parsed = parseHeadingLine(raw);
    const current = items[items.length - 1];
    if (parsed && isSectionHeading(parsed, hasRoot)) {
      if (current && current.number === parsed.number) {
        const remainder =
          peelHeadingPrefix(raw, current.number, current.title) ??
          peelHeadingPrefix(parsed.title, current.number, current.title);
        if (remainder && !isHeaderFooterArtifact(remainder)) {
          current.bodyLines.push(remainder);
        }
        continue;
      }
      startItem(parsed.number, parsed.title);
      continue;
    }

    const trimmed = unescapeHtmlEntities(raw).trim();
    if (!trimmed) continue;
    if (isHeaderFooterArtifact(trimmed)) continue;
    if (!current) {
      startItem("", trimmed.replace(INTRO_SUFFIX_RE, "").trim());
      continue;
    }
    current.bodyLines.push(trimmed);
  }

  return items;
}

function fromStructuredItems(items: SectionExtractionItemInput[]): FlatSection[] {
  return items.map((item, index) => ({
    documentId: item.documentId ?? "",
    number: item.sectionNumber ?? null,
    title: (item.sectionTitle ?? "").trim(),
    parentNumber: item.parentSectionNumber ?? parentSectionNumber(item.sectionNumber),
    chunkIndex: item.chunkIndex,
    chunkIds: item.chunkId ? [item.chunkId] : [],
    bodyLines: (item.content ?? "").split(/\r?\n/),
    order: index,
  }));
}

function sectionKey(item: FlatSection): string {
  const number = item.number ?? normalizeFingerprint(item.title) ?? `anon-${item.order}`;
  return `${item.documentId}:${item.parentNumber ?? ""}:${number}`;
}

function groupSections(items: FlatSection[]): FlatSection[] {
  const grouped = new Map<string, FlatSection>();
  const order: string[] = [];

  const sorted = [...items].sort((a, b) => {
    if (a.chunkIndex !== b.chunkIndex) return a.chunkIndex - b.chunkIndex;
    const byNumber = compareSectionNumbers(a.number, b.number);
    if (byNumber !== 0) return byNumber;
    return a.order - b.order;
  });

  for (const item of sorted) {
    const key = sectionKey(item);
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {
        ...item,
        bodyLines: [...item.bodyLines],
        chunkIds: [...item.chunkIds],
      });
      order.push(key);
      continue;
    }
    existing.bodyLines.push(...item.bodyLines);
    for (const id of item.chunkIds) {
      if (!existing.chunkIds.includes(id)) existing.chunkIds.push(id);
    }
    if (!existing.title && item.title) existing.title = item.title;
  }

  return order.map((key) => grouped.get(key)!);
}

function attachCitations(
  nodes: SectionNode[],
  citations: CitationViewModel[],
): void {
  if (citations.length === 0) return;
  const used = new Set<string>();

  const walk = (node: SectionNode) => {
    const matched = citations.filter((c) => {
      if (used.has(c.id)) return false;
      if (node.chunkIds.length > 0 && c.chunkId && node.chunkIds.includes(c.chunkId)) return true;
      const titleFp = normalizeFingerprint(node.title);
      const snippetFp = normalizeFingerprint(c.textSnippet || "");
      const sectionFp = normalizeFingerprint(c.sectionTitle || "");
      if (titleFp && sectionFp && (sectionFp === titleFp || sectionFp.includes(titleFp) || titleFp.includes(sectionFp))) {
        return true;
      }
      if (titleFp && snippetFp && (snippetFp.includes(titleFp) || titleFp.includes(snippetFp.slice(0, 48)))) {
        return true;
      }
      return false;
    });

    const unique: CitationViewModel[] = [];
    const seen = new Set<string>();
    for (const c of matched) {
      const key = `${c.documentId}:${c.chunkId ?? c.id}`;
      const pageKey =
        c.page != null ? `${c.documentId}:${c.page}` : key;
      if (seen.has(pageKey) || seen.has(key)) {
        used.add(c.id);
        continue;
      }
      seen.add(pageKey);
      seen.add(key);
      used.add(c.id);
      unique.push(c);
    }
    node.citations = unique;
    for (const child of node.children) walk(child);
  };

  for (const node of nodes) walk(node);

  const leftover = citations.filter((c) => !used.has(c.id));
  if (leftover.length === 0) return;

  const leaves: SectionNode[] = [];
  const collect = (node: SectionNode) => {
    if (node.children.length === 0) leaves.push(node);
    node.children.forEach(collect);
  };
  nodes.forEach(collect);
  leftover.forEach((citation, index) => {
    if (leaves.length === 0) return;
    const target = leaves[index % leaves.length];
    if (!target) return;
    if (
      citation.chunkId &&
      target.citations.some((c) => c.chunkId === citation.chunkId)
    ) {
      return;
    }
    if (
      citation.page != null &&
      target.citations.some(
        (c) => c.documentId === citation.documentId && c.page === citation.page,
      )
    ) {
      return;
    }
    target.citations.push(citation);
  });
}

function toNode(item: FlatSection): SectionNode {
  const normalized = item.bodyLines.map((line) => unescapeHtmlEntities(line).trim()).filter(Boolean);
  const stripped = stripHeadingFromBody(item.number, item.title, normalized);
  return {
    key: sectionKey(item),
    number: item.number,
    title: stripMarkdownEmphasis(item.title),
    depth: item.number ? item.number.split(".").length : 1,
    chunkIds: item.chunkIds,
    citations: [],
    blocks: toBlocks(stripped),
    children: [],
  };
}

function dropRepeatedRunningHeaders(nodes: SectionNode[]): void {
  const counts = new Map<string, number>();
  const walkCount = (node: SectionNode) => {
    for (const block of node.blocks) {
      if (block.kind !== "paragraph") continue;
      const fp = normalizeFingerprint(block.text);
      if (fp && block.text.trim().length <= 80) {
        counts.set(fp, (counts.get(fp) ?? 0) + 1);
      }
    }
    node.children.forEach(walkCount);
  };
  nodes.forEach(walkCount);

  const repeated = new Set(
    [...counts.entries()].filter(([, count]) => count >= 2).map(([fp]) => fp),
  );

  const walkFilter = (node: SectionNode) => {
    node.blocks = node.blocks.filter((block) => {
      if (block.kind !== "paragraph") return true;
      const text = block.text.trim();
      const fp = normalizeFingerprint(text);
      if (isHeaderFooterArtifact(text)) return false;
      if (repeated.has(fp) && text.length <= 80 && !/[.!?…]/.test(text)) return false;
      return true;
    });
    node.children.forEach(walkFilter);
  };
  nodes.forEach(walkFilter);
}

function buildTree(items: FlatSection[]): SectionNode[] {
  const nodes = items.map(toNode);
  const byNumber = new Map<string, SectionNode>();
  for (const node of nodes) {
    if (node.number && !byNumber.has(node.number)) byNumber.set(node.number, node);
  }

  const roots: SectionNode[] = [];
  for (const node of nodes) {
    const parentNum = parentSectionNumber(node.number);
    const parent = parentNum ? byNumber.get(parentNum) : undefined;
    if (parent && parent !== node) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

export function buildSectionExtractionModel(input: {
  content: string;
  citations?: CitationViewModel[];
  items?: SectionExtractionItemInput[];
}): SectionExtractionModel {
  const flat =
    input.items && input.items.length > 0
      ? fromStructuredItems(input.items)
      : parseContentToFlat(input.content);
  const grouped = groupSections(flat);
  const nodes = buildTree(grouped);
  dropRepeatedRunningHeaders(nodes);
  attachCitations(nodes, input.citations ?? []);
  return { nodes };
}

export function modelHasRenderableSections(model: SectionExtractionModel): boolean {
  return model.nodes.some((n) => Boolean(n.number || n.title || n.blocks.length));
}
