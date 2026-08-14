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
  onBlockVisible?: (blockId: string) => void;
};

export function KnowledgeView({
  blocks,
  markdownFallback = "",
  documentTitle = null,
  locator = null,
  highlightSnippet = null,
  activeBlockId = null,
  onBlockVisible,
}: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const result = applyLocatorHighlights(
      root,
      blocks,
      locator,
      highlightSnippet,
      activeBlockId,
    );
    if (result.scrolledBlockId && result.scrolledBlockId !== activeBlockId) {
      onBlockVisible?.(result.scrolledBlockId);
    }
  }, [blocks, locator, highlightSnippet, activeBlockId, onBlockVisible]);

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
