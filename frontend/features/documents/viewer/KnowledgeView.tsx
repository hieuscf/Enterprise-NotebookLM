/**
 * =============================================================================
 * File: KnowledgeView.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Citation-aware Knowledge View — Canonical Blocks → document reader.
 * Responsibilities:
 *   - Host the document canvas and semantic renderer
 *   - Apply deterministic citation highlights (block_id + text range)
 *   - Scroll active highlight/block inside the Knowledge View container
 * Dependencies:
 *   - knowledge/DocumentRenderer, knowledge/citation-highlight
 * Public Exports:
 *   - KnowledgeView
 * Database/Table: N/A (loads via /canonical)
 * Related Modules: DocumentViewer
 * Important Notes: Primary citation target — locator offsets are not changed.
 *   Highlight miss is a soft failure; do not treat as "leave Knowledge View".
 * =============================================================================
 */

"use client";

import { useEffect, useRef } from "react";

import {
  DocumentRenderer,
  KnowledgeEmpty,
  KnowledgeMarkdownFallback,
} from "@/features/documents/viewer/knowledge/DocumentRenderer";
import { applyLocatorHighlights } from "@/features/documents/viewer/knowledge/citation-highlight";
import type { CanonicalBlock, CitationLocator } from "@/types/canonical";

type Props = {
  blocks: CanonicalBlock[];
  markdownFallback?: string;
  documentTitle?: string | null;
  locator?: CitationLocator | null;
  highlightSnippet?: string | null;
  activeBlockId?: string | null;
  /** When locator/snippet miss, still scroll to this block (chunk/page fallback). */
  fallbackBlockId?: string | null;
  onBlockVisible?: (blockId: string) => void;
  onNavigationFailed?: () => void;
};

export function KnowledgeView({
  blocks,
  markdownFallback = "",
  documentTitle = null,
  locator = null,
  highlightSnippet = null,
  activeBlockId = null,
  fallbackBlockId = null,
  onBlockVisible,
  onNavigationFailed,
}: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const expectFocus =
    Boolean(locator?.ranges?.length) ||
    Boolean(highlightSnippet?.trim()) ||
    Boolean(activeBlockId) ||
    Boolean(fallbackBlockId);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (!expectFocus) return;

    let cancelled = false;
    let retryTimer: number | null = null;

    const run = (attempt: number) => {
      if (cancelled) return;
      const result = applyLocatorHighlights(
        root,
        blocks,
        locator,
        highlightSnippet,
        activeBlockId,
        fallbackBlockId,
      );
      if (result.scrolledBlockId && result.scrolledBlockId !== activeBlockId) {
        onBlockVisible?.(result.scrolledBlockId);
      }
      if (result.scrolledBlockId) return;

      // Wait for block hosts (large docs / fonts) before declaring miss.
      const hasBlockHosts = Boolean(root.querySelector("[data-block-id]"));
      if (attempt < (hasBlockHosts ? 4 : 6)) {
        const delay =
          attempt === 0
            ? 40
            : attempt === 1
              ? 120
              : attempt === 2
                ? 250
                : attempt === 3
                  ? 400
                  : attempt === 4
                    ? 700
                    : 1100;
        retryTimer = window.setTimeout(() => run(attempt + 1), delay);
        return;
      }
      // Soft-fail: keep Knowledge View; parent only toasts (does not switch mode).
      onNavigationFailed?.();
    };

    const raf = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => run(0));
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(raf);
      if (retryTimer != null) window.clearTimeout(retryTimer);
    };
  }, [
    blocks,
    locator,
    highlightSnippet,
    activeBlockId,
    fallbackBlockId,
    expectFocus,
    onBlockVisible,
    onNavigationFailed,
  ]);

  if (!blocks.length && !markdownFallback.trim()) {
    return <KnowledgeEmpty />;
  }

  return (
    <div ref={rootRef} className="knowledge-scroll">
      <article className="knowledge-canvas doc-viewer">
        {blocks.length ? (
          <DocumentRenderer blocks={blocks} documentTitle={documentTitle} />
        ) : (
          <KnowledgeMarkdownFallback markdown={markdownFallback} />
        )}
      </article>
    </div>
  );
}
