/**
 * =============================================================================
 * File: citation-highlight.ts
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Deterministic citation highlight on Knowledge View block hosts.
 * Responsibilities:
 *   - Wrap a character range inside a block's text nodes with <mark>
 *   - Clear previous marks without changing Canonical content
 *   - Scroll the active mark/block inside the Knowledge View container
 *   - Resolve snippet → block when locator ranges are missing (FR5)
 * Dependencies:
 *   - document-structure (offset mapping)
 * Public Exports:
 *   - highlightTextRange, clearCitationMarks, scrollTargetIntoContainer
 *   - applyLocatorHighlights, findBlockForSnippet, matchSnippetInBlockContent
 * Database/Table: N/A
 * Related Modules: KnowledgeView, CitationLocator
 * Important Notes:
 *   - Offsets are relative to block.content; mapping to display text is local.
 *   - Highlight per text-node (never surroundContents across element boundaries).
 * =============================================================================
 */

import type { CanonicalBlock, CitationLocator } from "@/types/canonical";

import { displayHeadingText, mapContentOffsetsToDisplay } from "./document-structure";

function normalizeForMatch(value: string): string {
  return (value || "")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Build (normalized string, index map back into original). */
function normalizedIndexMap(value: string): { norm: string; map: number[] } {
  const map: number[] = [];
  let norm = "";
  let prevSpace = true;
  for (let i = 0; i < value.length; i += 1) {
    let ch = value[i];
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

/** Strip list / quote markers and fancy quotes that citations often include. */
function snippetVariants(snippet: string): string[] {
  const base = (snippet || "").trim();
  if (!base) return [];
  const out: string[] = [];
  const push = (value: string) => {
    const v = value.replace(/\s+/g, " ").trim();
    if (v && !out.includes(v)) out.push(v);
  };
  push(base);
  // Leading bullet / ordered-list / blockquote markers (common in chat citations).
  push(base.replace(/^[-*+•]\s+/, ""));
  push(base.replace(/^\d+[.)]\s+/, ""));
  push(base.replace(/^>\s+/, ""));
  push(
    base
      .replace(/^[-*+•]\s+/, "")
      .replace(/^\d+[.)]\s+/, "")
      .replace(/^>\s+/, ""),
  );
  // Surrounding quotation marks from the UI copy.
  for (const cur of [...out]) {
    push(cur.replace(/^[“”"']+/, "").replace(/[“”"']+$/, ""));
  }
  return out;
}

/** Exact → case-insensitive → whitespace-normalized containment (no prefix fallback). */
function matchExactOrNormalized(
  content: string,
  needle: string,
): { start: number; end: number } | null {
  if (!content || !needle) return null;

  const exact = content.indexOf(needle);
  if (exact >= 0) return { start: exact, end: exact + needle.length };

  const ci = content.toLowerCase().indexOf(needle.toLowerCase());
  if (ci >= 0) return { start: ci, end: ci + needle.length };

  const { norm: normContent, map } = normalizedIndexMap(content);
  const normNeedle = normalizeForMatch(needle);
  if (!normNeedle || normNeedle.length < 8 || map.length === 0) return null;
  const nidx = normContent.indexOf(normNeedle);
  if (nidx < 0) return null;
  const start = map[nidx] ?? 0;
  const endIdx = Math.min(map.length - 1, nidx + normNeedle.length - 1);
  const end = (map[endIdx] ?? start) + 1;
  return end > start ? { start, end } : null;
}

function scoreHit(hit: { start: number; end: number } | null): number {
  return hit ? hit.end - hit.start : 0;
}

/**
 * Match citation snippet inside block/display text.
 * Always prefers the *longest* successful match (full sentence > short window).
 */
export function matchSnippetInBlockContent(
  content: string,
  snippet: string,
): { start: number; end: number } | null {
  const variants = snippetVariants(snippet);
  if (!content || variants.length === 0) return null;

  let best: { start: number; end: number } | null = null;

  // 1) Full variants first (with/without list markers).
  for (const needle of variants) {
    const hit = matchExactOrNormalized(content, needle);
    if (scoreHit(hit) > scoreHit(best)) best = hit;
  }
  // Near-complete match — stop (avoid shorter sliding-window hits).
  const targetLen = variants[0]?.length ?? 0;
  if (best && scoreHit(best) >= Math.max(32, Math.floor(targetLen * 0.85))) {
    return best;
  }

  // 2) Progressive prefixes of the best stripped variant (longest → shorter).
  //    Cuts at word/punctuation boundaries when possible.
  const primary =
    variants.find((v) => !/^[-*+•]/.test(v) && !/^\d+[.)]/.test(v)) ??
    variants[0];
  if (primary.length > 32) {
    for (let len = primary.length; len >= 32; len -= 8) {
      let head = primary.slice(0, len).trim();
      // Prefer ending on whitespace / punctuation so we don't stop mid-word.
      if (len < primary.length) {
        const cut = Math.max(
          head.lastIndexOf(" "),
          head.lastIndexOf("."),
          head.lastIndexOf(":"),
          head.lastIndexOf(","),
        );
        if (cut >= 32) head = head.slice(0, cut + (head[cut] === " " ? 0 : 1)).trim();
      }
      if (head.length < 32) continue;
      const hit = matchExactOrNormalized(content, head);
      if (scoreHit(hit) > scoreHit(best)) best = hit;
      // First (longest) prefix hit is enough.
      if (hit) break;
    }
  }
  if (best && scoreHit(best) >= Math.max(48, Math.floor(targetLen * 0.6))) {
    return best;
  }

  // 3) Last resort: sliding windows — keep the longest window hit only.
  if (primary.length > 48) {
    const window = Math.min(120, Math.max(48, Math.floor(primary.length / 2)));
    const step = Math.max(12, Math.floor(window / 3));
    for (let i = 0; i + 32 <= primary.length; i += step) {
      const part = primary.slice(i, Math.min(primary.length, i + window)).trim();
      if (part.length < 32) continue;
      const hit = matchExactOrNormalized(content, part);
      if (scoreHit(hit) > scoreHit(best)) best = hit;
    }
  }

  return best;
}

/** Prefer longest exact/normalized hit; used when locator ranges are empty. */
export function findBlockForSnippet(
  blocks: CanonicalBlock[],
  snippet: string,
): CanonicalBlock | null {
  const needle = (snippet || "").trim();
  if (!needle || blocks.length === 0) return null;

  let best: CanonicalBlock | null = null;
  let bestScore = 0;
  for (const block of blocks) {
    const hit = matchSnippetInBlockContent(block.content || "", needle);
    if (!hit) continue;
    const score = hit.end - hit.start;
    if (score > bestScore) {
      bestScore = score;
      best = block;
    }
  }
  return best;
}

export function clearCitationMarks(root: HTMLElement): void {
  root.querySelectorAll("mark[data-citation-hl]").forEach((el) => {
    const parent = el.parentNode;
    if (!parent) return;
    while (el.firstChild) parent.insertBefore(el.firstChild, el);
    parent.removeChild(el);
    parent.normalize();
  });
  root.querySelectorAll("[data-active-block], [data-outline-active]").forEach((el) => {
    el.removeAttribute("data-active-block");
    el.removeAttribute("data-outline-active");
  });
}

type TextSlice = { node: Text; start: number; end: number };

function collectTextSlices(
  host: HTMLElement,
  start: number,
  end: number,
): TextSlice[] {
  if (end <= start) return [];
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  const slices: TextSlice[] = [];
  let cursor = 0;
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const len = node.data.length;
    const nodeStart = cursor;
    const nodeEnd = cursor + len;
    const overlapStart = Math.max(start, nodeStart);
    const overlapEnd = Math.min(end, nodeEnd);
    if (overlapEnd > overlapStart) {
      slices.push({
        node,
        start: overlapStart - nodeStart,
        end: overlapEnd - nodeStart,
      });
    }
    cursor = nodeEnd;
    if (cursor >= end) break;
  }
  return slices;
}

/**
 * Wrap a character range inside an element's text nodes with <mark>.
 * Highlights each text node independently so nested markdown (bold/links)
 * does not break surroundContents.
 */
export function highlightTextRange(
  host: HTMLElement,
  start: number,
  end: number,
): HTMLElement | null {
  if (end <= start) return null;
  const slices = collectTextSlices(host, start, end);
  if (!slices.length) return null;

  let firstMark: HTMLElement | null = null;
  // Wrap from the end so earlier offsets stay valid within each node.
  for (let i = slices.length - 1; i >= 0; i -= 1) {
    const slice = slices[i];
    try {
      const range = document.createRange();
      range.setStart(slice.node, slice.start);
      range.setEnd(slice.node, slice.end);
      const mark = document.createElement("mark");
      mark.dataset.citationHl = "1";
      mark.className = "highlight-citation";
      range.surroundContents(mark);
      firstMark = mark;
    } catch {
      // Node may have been split by a prior wrap; skip soft failures.
    }
  }
  return firstMark;
}

export function scrollTargetIntoContainer(container: HTMLElement, target: HTMLElement): void {
  const cRect = container.getBoundingClientRect();
  const tRect = target.getBoundingClientRect();
  const delta = tRect.top - cRect.top - cRect.height / 2 + tRect.height / 2;
  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  container.scrollTo({
    top: container.scrollTop + delta,
    behavior: reduced ? "auto" : "smooth",
  });
}

type ApplyResult = {
  firstMark: HTMLElement | null;
  scrolledBlockId: string | null;
};

function highlightSnippetOnHost(
  host: HTMLElement,
  block: CanonicalBlock | undefined,
  snippet: string,
): HTMLElement | null {
  const content = block?.content || "";
  const display = host.textContent ?? "";

  // Prefer matching the visible text (list markers stripped in the DOM) so the
  // full Selected text — not a short mid-window — gets painted.
  const displayHit = matchSnippetInBlockContent(display, snippet);
  if (displayHit && scoreHit(displayHit) >= 24) {
    const mark = highlightTextRange(host, displayHit.start, displayHit.end);
    if (mark) return mark;
  }

  const contentHit = matchSnippetInBlockContent(content, snippet);
  if (contentHit) {
    const mapped = mapRangeForBlock(block, host, contentHit.start, contentHit.end);
    const mark = highlightTextRange(host, mapped.start, mapped.end);
    if (mark) return mark;
  }

  return null;
}

export function applyLocatorHighlights(
  root: HTMLElement,
  blocks: CanonicalBlock[],
  locator: CitationLocator | null,
  highlightSnippet: string | null,
  activeBlockId: string | null,
  fallbackBlockId: string | null = null,
): ApplyResult {
  clearCitationMarks(root);

  const ranges = locator?.ranges?.filter((r) => r.end > r.start) ?? [];
  const locatorUsable =
    ranges.length > 0 &&
    Boolean(locator?.confidence) &&
    locator?.confidence !== "none";
  let firstMark: HTMLElement | null = null;
  let matchedBlockId: string | null = null;
  const byId = new Map(blocks.map((b) => [b.id, b]));

  if (locatorUsable) {
    for (const range of ranges) {
      const host = root.querySelector(
        `[data-block-id="${CSS.escape(range.block_id)}"]`,
      ) as HTMLElement | null;
      if (!host) continue;
      const block = byId.get(range.block_id);
      const mapped = mapRangeForBlock(block, host, range.start, range.end);
      const mark = highlightTextRange(host, mapped.start, mapped.end);
      if (mark && !firstMark) {
        firstMark = mark;
        matchedBlockId = range.block_id;
      }
      host.setAttribute("data-active-block", "");
      if (!matchedBlockId) matchedBlockId = range.block_id;
    }
  }

  if (!firstMark && highlightSnippet?.trim()) {
    const snippet = highlightSnippet.trim();
    // Prefer the best single block, then paint every block that contains a
    // substantial slice (snippet often spans multiple canonical blocks).
    const ordered = [...blocks].sort((a, b) => {
      const ha = matchSnippetInBlockContent(a.content || "", snippet);
      const hb = matchSnippetInBlockContent(b.content || "", snippet);
      return (hb ? hb.end - hb.start : 0) - (ha ? ha.end - ha.start : 0);
    });
    for (const block of ordered) {
      const hit = matchSnippetInBlockContent(block.content || "", snippet);
      if (!hit || hit.end - hit.start < 24) continue;
      const host = root.querySelector(
        `[data-block-id="${CSS.escape(block.id)}"]`,
      ) as HTMLElement | null;
      if (!host) continue;
      const mark = highlightSnippetOnHost(host, block, snippet);
      if (!mark) continue;
      host.setAttribute("data-active-block", "");
      if (!firstMark) {
        firstMark = mark;
        matchedBlockId = block.id;
      }
      // Cap multi-block paint to avoid marking half the document.
      if (root.querySelectorAll("mark[data-citation-hl]").length >= 4) break;
    }
    if (!firstMark) {
      const block = findBlockForSnippet(blocks, snippet);
      if (block) {
        const host = root.querySelector(
          `[data-block-id="${CSS.escape(block.id)}"]`,
        ) as HTMLElement | null;
        host?.setAttribute("data-outline-active", "");
        if (host) matchedBlockId = block.id;
      }
    }
  }

  // Locator ranges present but mark failed — still try snippet on those hosts.
  if (!firstMark && locatorUsable && highlightSnippet?.trim()) {
    const snippet = highlightSnippet.trim();
    for (const range of ranges) {
      const host = root.querySelector(
        `[data-block-id="${CSS.escape(range.block_id)}"]`,
      ) as HTMLElement | null;
      if (!host) continue;
      const mark = highlightSnippetOnHost(host, byId.get(range.block_id), snippet);
      if (mark) {
        firstMark = mark;
        host.setAttribute("data-active-block", "");
        matchedBlockId = range.block_id;
        break;
      }
    }
  }

  const fallbackId =
    matchedBlockId ??
    activeBlockId ??
    (locatorUsable ? ranges[0]?.block_id ?? null : null) ??
    fallbackBlockId;
  const scrollTarget =
    firstMark ??
    (fallbackId
      ? (root.querySelector(
          `[data-block-id="${CSS.escape(fallbackId)}"]`,
        ) as HTMLElement | null)
      : null);

  if (scrollTarget && !firstMark && fallbackId) {
    const host = root.querySelector(
      `[data-block-id="${CSS.escape(fallbackId)}"]`,
    ) as HTMLElement | null;
    host?.setAttribute("data-outline-active", "");
  }

  let scrolledBlockId: string | null = null;
  if (scrollTarget) {
    scrollTargetIntoContainer(root, scrollTarget);
    scrolledBlockId = fallbackId;
  }

  return { firstMark, scrolledBlockId };
}

function mapRangeForBlock(
  block: CanonicalBlock | undefined,
  host: HTMLElement,
  start: number,
  end: number,
): { start: number; end: number } {
  const content = block?.content ?? host.textContent ?? "";
  const display =
    block?.block_type === "heading"
      ? displayHeadingText(content)
      : (host.textContent ?? content);
  return mapContentOffsetsToDisplay(content, display, start, end);
}
