/**
 * =============================================================================
 * File: ChunkNavigator.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Locate chunk metadata → jump PDF page → highlight citation span.
 * Responsibilities:
 *   - Resolve chunk by id; wait for page render; highlight via snippet/bbox
 *   - Missing chunk → onMissing
 * Public Exports:
 *   - ChunkNavigator
 * Important Notes: Prefer text_snippet sub-span over whole-chunk bbox.
 * =============================================================================
 */

"use client";

import { useEffect, useRef } from "react";

import type { PDFViewerHandle } from "@/features/documents/viewer/PDFViewer";
import type { DocumentChunk } from "@/types/documents";

type Props = {
  chunkId: string | null;
  /** Citation text_snippet — used for sub-span text-layer highlight. */
  highlightSnippet?: string | null;
  chunks: DocumentChunk[];
  pdfRef: React.RefObject<PDFViewerHandle | null>;
  ready: boolean;
  onMissing?: (chunkId: string) => void;
  onLocated?: (chunk: DocumentChunk) => void;
  onHighlightFailed?: () => void;
};

export function ChunkNavigator({
  chunkId,
  highlightSnippet = null,
  chunks,
  pdfRef,
  ready,
  onMissing,
  onLocated,
  onHighlightFailed,
}: Props) {
  const ranFor = useRef<string | null>(null);

  useEffect(() => {
    if (!chunkId || !ready) return;
    const key = `${chunkId}|${highlightSnippet ?? ""}`;
    if (ranFor.current === key) return;
    ranFor.current = key;

    const chunk = chunks.find((c) => c.id === chunkId);
    if (!chunk) {
      onMissing?.(chunkId);
      return;
    }

    const page =
      chunk.page_number && chunk.page_number > 0 ? chunk.page_number : 1;
    const handle = pdfRef.current;
    if (!handle) {
      ranFor.current = null;
      return;
    }

    let cancelled = false;
    void (async () => {
      handle.jumpToPage(page);
      await handle.waitForPage(page);
      if (cancelled) return;
      // Prefer citation snippet (sub-span); fall back to chunk bbox only.
      const snippet =
        highlightSnippet?.trim() &&
        chunk.content &&
        chunk.content.includes(highlightSnippet.trim())
          ? highlightSnippet.trim()
          : highlightSnippet?.trim() || null;
      const ok = await handle.setHighlight({
        pageNumber: page,
        bbox: chunk.bounding_box,
        snippet,
      });
      if (cancelled) return;
      onLocated?.(chunk);
      if (!ok && !chunk.bounding_box && !snippet) {
        onHighlightFailed?.();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    chunkId,
    highlightSnippet,
    chunks,
    pdfRef,
    ready,
    onMissing,
    onLocated,
    onHighlightFailed,
  ]);

  return null;
}
