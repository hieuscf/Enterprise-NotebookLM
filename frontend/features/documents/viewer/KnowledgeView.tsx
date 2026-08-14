/**
 * =============================================================================
 * File: KnowledgeView.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Render Canonical Knowledge Document blocks with citation highlight.
 * Responsibilities:
 *   - Render structured blocks (heading/paragraph/table/list/figure)
 *   - Apply block-range highlight for citation text_snippet
 *   - Scroll active highlight into view after render
 * Dependencies:
 *   - types/canonical, react-markdown (tables via remark-gfm)
 * Public Exports:
 *   - KnowledgeView
 * Database/Table: N/A (loads via /canonical)
 * Related Modules: DocumentViewer
 * Important Notes: Primary citation target — no PDF fuzzy match here.
 * =============================================================================
 */

"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { CanonicalBlock, CitationLocator } from "@/types/canonical";

type Props = {
  blocks: CanonicalBlock[];
  markdownFallback?: string;
  locator?: CitationLocator | null;
  highlightSnippet?: string | null;
  activeBlockId?: string | null;
  onBlockVisible?: (blockId: string) => void;
};

export function KnowledgeView({
  blocks,
  markdownFallback = "",
  locator = null,
  highlightSnippet = null,
  activeBlockId = null,
  onBlockVisible,
}: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    // Clear previous marks
    root.querySelectorAll("mark[data-citation-hl]").forEach((el) => {
      const parent = el.parentNode;
      if (!parent) return;
      while (el.firstChild) parent.insertBefore(el.firstChild, el);
      parent.removeChild(el);
      parent.normalize();
    });

    const ranges = locator?.ranges?.filter((r) => r.end > r.start) ?? [];
    let firstMark: HTMLElement | null = null;

    if (ranges.length && locator?.confidence && locator.confidence !== "none") {
      for (const range of ranges) {
        const host = root.querySelector(
          `[data-block-id="${CSS.escape(range.block_id)}"]`,
        ) as HTMLElement | null;
        if (!host) continue;
        const mark = highlightTextRange(host, range.start, range.end);
        if (mark && !firstMark) firstMark = mark;
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
        const mark = highlightTextRange(host, idx, idx + snippet.length);
        if (mark && !firstMark) firstMark = mark;
        break;
      }
    }

    const scrollTarget =
      firstMark ??
      (activeBlockId
        ? (root.querySelector(
            `[data-block-id="${CSS.escape(activeBlockId)}"]`,
          ) as HTMLElement | null)
        : null);

    if (scrollTarget) {
      scrollTarget.scrollIntoView({ behavior: "smooth", block: "center" });
      if (activeBlockId) onBlockVisible?.(activeBlockId);
      else if (ranges[0]?.block_id) onBlockVisible?.(ranges[0].block_id);
    }
  }, [blocks, locator, highlightSnippet, activeBlockId, onBlockVisible]);

  if (!blocks.length && markdownFallback) {
    return (
      <div
        ref={rootRef}
        className="prose prose-sm max-w-none overflow-auto rounded-md border border-border-default bg-surface p-4 text-primary"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdownFallback}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className="max-h-full space-y-3 overflow-auto rounded-md border border-border-default bg-surface p-4"
    >
      {blocks.map((block) => (
        <BlockNode
          key={block.id}
          block={block}
          active={activeBlockId === block.id}
        />
      ))}
    </div>
  );
}

function BlockNode({
  block,
  active,
}: {
  block: CanonicalBlock;
  active: boolean;
}) {
  const common = cn(
    "scroll-mt-24 rounded-sm px-1 -mx-1",
    active && "ring-2 ring-accent-primary/40",
  );

  if (block.block_type === "heading") {
    const level = Math.min(6, Math.max(1, block.heading_level ?? 2));
    const className = cn(
      common,
      "font-semibold text-primary",
      level <= 1 && "text-title",
      level === 2 && "text-body font-semibold",
      level >= 3 && "text-body-sm font-semibold",
    );
    if (level === 1) {
      return (
        <h1 data-block-id={block.id} className={className}>
          {block.content}
        </h1>
      );
    }
    if (level === 2) {
      return (
        <h2 data-block-id={block.id} className={className}>
          {block.content}
        </h2>
      );
    }
    if (level === 3) {
      return (
        <h3 data-block-id={block.id} className={className}>
          {block.content}
        </h3>
      );
    }
    return (
      <h4 data-block-id={block.id} className={className}>
        {block.content}
      </h4>
    );
  }

  if (block.block_type === "table") {
    return (
      <div data-block-id={block.id} className={cn(common, "overflow-x-auto")}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
      </div>
    );
  }

  if (block.block_type === "list") {
    return (
      <div data-block-id={block.id} className={cn(common, "text-body-sm text-primary")}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
      </div>
    );
  }

  if (block.block_type === "figure") {
    return (
      <figure
        data-block-id={block.id}
        className={cn(common, "border border-dashed border-border-default p-3 text-caption text-tertiary")}
      >
        {block.content || "Figure"}
      </figure>
    );
  }

  return (
    <p
      data-block-id={block.id}
      className={cn(common, "whitespace-pre-wrap text-body-sm leading-relaxed text-primary")}
    >
      {block.content}
    </p>
  );
}

/** Wrap a character range inside an element's text nodes with <mark>. */
function highlightTextRange(
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
    // Fallback: wrap whole host text match if offsets drift due to MD render.
    const text = host.textContent || "";
    // no-op if can't map
    if (!text) return null;
    return null;
  }

  try {
    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    const mark = document.createElement("mark");
    mark.dataset.citationHl = "1";
    mark.className = "rounded-sm bg-amber-200/80 text-inherit";
    range.surroundContents(mark);
    return mark;
  } catch {
    return null;
  }
}
