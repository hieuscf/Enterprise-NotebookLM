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
 *   - applyLocatorHighlights, findBlockForSnippet
 * Database/Table: N/A
 * Related Modules: KnowledgeView, CitationLocator
 * Important Notes:
 *   - Offsets are relative to block.content; mapping to display text is local.
 *   - Do not use window.find / regex / fuzzy innerText search.
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

/** Exact → case-insensitive → whitespace-normalized containment in block.content. */
export function matchSnippetInBlockContent(
  content: string,
  snippet: string,
): { start: number; end: number } | null {
  const needle = (snippet || "").trim();
  if (!content || !needle) return null;

  const exact = content.indexOf(needle);
  if (exact >= 0) return { start: exact, end: exact + needle.length };

  const ci = content.toLowerCase().indexOf(needle.toLowerCase());
  if (ci >= 0) return { start: ci, end: ci + needle.length };

  const normContent = normalizeForMatch(content);
  const normNeedle = normalizeForMatch(needle);
  if (!normNeedle || normNeedle.length < 8) return null;
  const nidx = normContent.indexOf(normNeedle);
  if (nidx < 0) return null;

  // Approximate map: use proportional index into original content.
  const ratio = content.length / Math.max(1, normContent.length);
  const start = Math.max(0, Math.min(content.length - 1, Math.floor(nidx * ratio)));
  const end = Math.max(
    start + 1,
    Math.min(content.length, Math.floor((nidx + normNeedle.length) * ratio)),
  );
  return { start, end };
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
  if (best) return best;

  // Chunk head may be longer than any single block — try progressive prefixes.
  if (needle.length > 80) {
    for (const len of [160, 120, 80, 48]) {
      if (needle.length < len) continue;
      const head = needle.slice(0, len);
      for (const block of blocks) {
        if (matchSnippetInBlockContent(block.content || "", head)) return block;
      }
    }
  }
  return null;
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

/** Wrap a character range inside an element's text nodes with <mark>. */
export function highlightTextRange(
  host: HTMLElement,
  start: number,
  end: number,
): HTMLElement | null {
  if (end <= start) return null;
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  let cursor = 0;
  let startNode: Text | null = null;
  let startOffset = 0;
  let endNode: Text | null = null;
  let endOffset = 0;

  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const len = node.data.length;
    const nodeStart = cursor;
    const nodeEnd = cursor + len;
    if (!startNode && start >= nodeStart && start < nodeEnd) {
      startNode = node;
      startOffset = start - nodeStart;
    }
    if (!endNode && end > nodeStart && end <= nodeEnd) {
      endNode = node;
      endOffset = end - nodeStart;
    }
    cursor = nodeEnd;
    if (startNode && endNode) break;
  }

  if (!startNode || !endNode) {
    return null;
  }

  try {
    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    const mark = document.createElement("mark");
    mark.dataset.citationHl = "1";
    mark.className = "highlight-citation";
    range.surroundContents(mark);
    return mark;
  } catch {
    return null;
  }
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
    const block = findBlockForSnippet(blocks, snippet);
    if (block) {
      const hit = matchSnippetInBlockContent(block.content || "", snippet);
      const host = root.querySelector(
        `[data-block-id="${CSS.escape(block.id)}"]`,
      ) as HTMLElement | null;
      if (host && hit) {
        const mapped = mapRangeForBlock(block, host, hit.start, hit.end);
        const mark = highlightTextRange(host, mapped.start, mapped.end);
        if (mark) firstMark = mark;
        host.setAttribute("data-active-block", "");
        matchedBlockId = block.id;
      } else if (host) {
        host.setAttribute("data-outline-active", "");
        matchedBlockId = block.id;
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
