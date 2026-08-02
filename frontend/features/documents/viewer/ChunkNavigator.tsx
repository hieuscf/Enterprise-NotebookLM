/**
 * =============================================================================
 * File: ChunkNavigator.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Locate chunk metadata → jump PDF page → highlight (no text search).
 * Responsibilities:
 *   - Resolve chunk by id from loaded metadata; call PDFViewerHandle
 *   - Missing chunk → onMissing
 * Public Exports:
 *   - ChunkNavigator
 * Important Notes: Logic lives here — not inside PDFViewer.
 * =============================================================================
 */

"use client";

import { useEffect, useRef } from "react";

import type { PDFViewerHandle } from "@/features/documents/viewer/PDFViewer";
import type { DocumentChunk } from "@/types/documents";

type Props = {
  chunkId: string | null;
  chunks: DocumentChunk[];
  pdfRef: React.RefObject<PDFViewerHandle | null>;
  ready: boolean;
  onMissing?: (chunkId: string) => void;
  onLocated?: (chunk: DocumentChunk) => void;
};

export function ChunkNavigator({
  chunkId,
  chunks,
  pdfRef,
  ready,
  onMissing,
  onLocated,
}: Props) {
  const ranFor = useRef<string | null>(null);

  useEffect(() => {
    if (!chunkId || !ready) return;
    if (ranFor.current === chunkId) return;
    ranFor.current = chunkId;

    const chunk = chunks.find((c) => c.id === chunkId);
    if (!chunk) {
      onMissing?.(chunkId);
      return;
    }

    const page = chunk.page_number && chunk.page_number > 0 ? chunk.page_number : 1;
    const handle = pdfRef.current;
    if (!handle) {
      // Allow retry once PDF handle mounts.
      ranFor.current = null;
      return;
    }

    // Jump then highlight (single scroll path).
    handle.jumpToPage(page);
    const t = window.setTimeout(() => {
      handle.setHighlight({
        pageNumber: page,
        bbox: chunk.bounding_box,
        approximate: !chunk.bounding_box,
      });
      onLocated?.(chunk);
    }, 160);
    return () => window.clearTimeout(t);
  }, [chunkId, chunks, pdfRef, ready, onMissing, onLocated]);

  return null;
}
