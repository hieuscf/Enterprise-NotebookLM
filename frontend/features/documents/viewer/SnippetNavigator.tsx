/**
 * =============================================================================
 * File: SnippetNavigator.tsx
 * Module/Service: Document Viewer / Chat Citation
 * Layer: UI
 * Purpose: Resolve citation text_snippet → chunk → PDF page + highlight.
 * Responsibilities:
 *   - Match snippet to chunks; jump/highlight; fall back to page / approximate
 * Dependencies:
 *   - citation-snippet-match, PDFViewerHandle
 * Public Exports:
 *   - SnippetNavigator
 * Database/Table: N/A
 * Related Modules: DocumentViewer
 * Important Notes: Highlight failure must not crash — falls back gracefully.
 * =============================================================================
 */

"use client";

import { useEffect, useRef } from "react";

import { findChunkForSnippet } from "@/features/chat/citation/citation-snippet-match";
import type { PDFViewerHandle } from "@/features/documents/viewer/PDFViewer";
import type { DocumentChunk } from "@/types/documents";

type Props = {
  snippet: string | null;
  pageHint: number | null;
  chunks: DocumentChunk[];
  pdfRef: React.RefObject<PDFViewerHandle | null>;
  ready: boolean;
  enabled: boolean;
  onLocated?: (chunk: DocumentChunk | null, matched: boolean) => void;
  onHighlightFailed?: () => void;
};

export function SnippetNavigator({
  snippet,
  pageHint,
  chunks,
  pdfRef,
  ready,
  enabled,
  onLocated,
  onHighlightFailed,
}: Props) {
  const ranFor = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled || !ready) return;
    const key = `${snippet ?? ""}|${pageHint ?? ""}`;
    if (!snippet && !(pageHint && pageHint > 0)) return;
    if (ranFor.current === key) return;
    ranFor.current = key;

    const handle = pdfRef.current;
    if (!handle) {
      ranFor.current = null;
      return;
    }

    try {
      const chunk = snippet ? findChunkForSnippet(chunks, snippet) : null;
      if (chunk) {
        const page =
          chunk.page_number && chunk.page_number > 0
            ? chunk.page_number
            : pageHint && pageHint > 0
              ? pageHint
              : 1;
        handle.jumpToPage(page);
        const t = window.setTimeout(() => {
          handle.setHighlight({
            pageNumber: page,
            bbox: chunk.bounding_box,
            approximate: !chunk.bounding_box,
          });
          onLocated?.(chunk, true);
        }, 160);
        return () => window.clearTimeout(t);
      }

      if (pageHint && pageHint > 0) {
        handle.jumpToPage(pageHint);
        const t = window.setTimeout(() => {
          handle.setHighlight({
            pageNumber: pageHint,
            approximate: true,
          });
          onLocated?.(null, false);
          onHighlightFailed?.();
        }, 160);
        return () => window.clearTimeout(t);
      }

      onLocated?.(null, false);
      onHighlightFailed?.();
    } catch {
      onHighlightFailed?.();
    }
  }, [
    snippet,
    pageHint,
    chunks,
    pdfRef,
    ready,
    enabled,
    onLocated,
    onHighlightFailed,
  ]);

  return null;
}
