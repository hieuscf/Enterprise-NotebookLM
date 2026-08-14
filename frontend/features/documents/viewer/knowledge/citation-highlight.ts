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
 * Dependencies:
 *   - document-structure (offset mapping)
 * Public Exports:
 *   - highlightTextRange, clearCitationMarks, scrollTargetIntoContainer
 *   - applyLocatorHighlights
 * Database/Table: N/A
 * Related Modules: KnowledgeView, CitationLocator
 * Important Notes:
 *   - Offsets are relative to block.content; mapping to display text is local.
 *   - Do not use window.find / regex / fuzzy innerText search.
 * =============================================================================
 */

import type { CanonicalBlock, CitationLocator } from "@/types/canonical";

import { displayHeadingText, mapContentOffsetsToDisplay } from "./document-structure";

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
): ApplyResult {
  clearCitationMarks(root);

  const ranges = locator?.ranges?.filter((r) => r.end > r.start) ?? [];
  let firstMark: HTMLElement | null = null;
  const byId = new Map(blocks.map((b) => [b.id, b]));

  if (ranges.length && locator?.confidence && locator.confidence !== "none") {
    for (const range of ranges) {
      const host = root.querySelector(
        `[data-block-id="${CSS.escape(range.block_id)}"]`,
      ) as HTMLElement | null;
      if (!host) continue;
      const block = byId.get(range.block_id);
      const mapped = mapRangeForBlock(block, host, range.start, range.end);
      const mark = highlightTextRange(host, mapped.start, mapped.end);
      if (mark && !firstMark) firstMark = mark;
      host.setAttribute("data-active-block", "");
    }
  } else if (highlightSnippet?.trim()) {
    const snippet = highlightSnippet.trim();
    for (const block of blocks) {
      const idx = block.content.indexOf(snippet);
      if (idx < 0) continue;
      const host = root.querySelector(
        `[data-block-id="${CSS.escape(block.id)}"]`,
      ) as HTMLElement | null;
      if (!host) continue;
      const mapped = mapRangeForBlock(block, host, idx, idx + snippet.length);
      const mark = highlightTextRange(host, mapped.start, mapped.end);
      if (mark && !firstMark) firstMark = mark;
      host.setAttribute("data-active-block", "");
      break;
    }
  }

  const fallbackId = activeBlockId ?? ranges[0]?.block_id ?? null;
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
