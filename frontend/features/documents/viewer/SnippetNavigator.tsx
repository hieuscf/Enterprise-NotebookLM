/**
 * =============================================================================
 * File: SnippetNavigator.tsx
 * Module/Service: Document Viewer / Chat Citation
 * Layer: UI
 * Purpose: Resolve citation text_snippet → chunk → PDF page + sub-span highlight.
 * Responsibilities:
 *   - Match snippet to chunks; wait for page; text-layer highlight
 *   - Page-only fallback navigates without inventing a highlight band
 * Dependencies:
 *   - citation-snippet-match, PDFViewerHandle
 * Public Exports:
 *   - SnippetNavigator
 * Database/Table: N/A
 * Related Modules: DocumentViewer
 * Important Notes: Prefer ChunkNavigator when chunk_id is known.
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

    let cancelled = false;
    void (async () => {
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
          await handle.waitForPage(page);
          if (cancelled) return;
          const ok = await handle.setHighlight({
            pageNumber: page,
            bbox: chunk.bounding_box,
            snippet: snippet?.trim() || null,
          });
          if (cancelled) return;
          onLocated?.(chunk, true);
          if (!ok) onHighlightFailed?.();
          return;
        }

        if (pageHint && pageHint > 0) {
          handle.jumpToPage(pageHint);
          await handle.waitForPage(pageHint);
          if (cancelled) return;
          // Try text-layer match on the hinted page without whole-page band.
          const ok = snippet?.trim()
            ? await handle.setHighlight({
                pageNumber: pageHint,
                snippet: snippet.trim(),
              })
            : false;
          onLocated?.(null, false);
          if (!ok) onHighlightFailed?.();
          return;
        }

        onLocated?.(null, false);
        onHighlightFailed?.();
      } catch {
        onHighlightFailed?.();
      }
    })();

    return () => {
      cancelled = true;
    };
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
