/**
 * =============================================================================
 * File: PDFViewer.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Render Original PDF via pdf.js (never markdown).
 * Responsibilities:
 *   - Load PDF ArrayBuffer from content URL; render pages; expose jump API
 * Dependencies:
 *   - pdfjs-dist, HighlightOverlay
 * Public Exports:
 *   - PDFViewer, PDFViewerHandle
 * =============================================================================
 */

"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import {
  approximatePageHighlight,
  bboxToHighlightRect,
  HighlightOverlay,
  type HighlightRect,
} from "@/features/documents/viewer/HighlightOverlay";
import { cn } from "@/lib/utils";

export type PDFViewerHandle = {
  jumpToPage: (pageNumber: number) => void;
  setHighlight: (args: {
    pageNumber: number;
    bbox?: number[] | null;
    approximate?: boolean;
  }) => void;
  clearHighlight: () => void;
  getPageCount: () => number;
};

type Props = {
  /** Absolute or same-origin URL returning PDF bytes. */
  contentUrl: string;
  scale: number;
  rotation: number;
  className?: string;
  onDocumentReady?: (pageCount: number) => void;
  onLoadError?: (message: string) => void;
};

type PagePaint = {
  pageNumber: number;
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
};

export const PDFViewer = forwardRef<PDFViewerHandle, Props>(function PDFViewer(
  { contentUrl, scale, rotation, className, onDocumentReady, onLoadError },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<PagePaint[]>([]);
  const pagesRef = useRef<PagePaint[]>([]);
  const [loading, setLoading] = useState(true);
  const [highlight, setHighlightState] = useState<{
    pageNumber: number;
    rect: HighlightRect;
    active: boolean;
    settled: boolean;
  } | null>(null);
  const pdfDocRef = useRef<import("pdfjs-dist").PDFDocumentProxy | null>(null);
  const highlightTimer = useRef<number | null>(null);
  const scaleRef = useRef(scale);
  const rotationRef = useRef(rotation);
  scaleRef.current = scale;
  rotationRef.current = rotation;

  const clearHighlightTimers = () => {
    if (highlightTimer.current != null) {
      window.clearTimeout(highlightTimer.current);
      highlightTimer.current = null;
    }
  };

  const paintPages = useCallback(
    async (pdf: import("pdfjs-dist").PDFDocumentProxy) => {
      const painted: PagePaint[] = [];
      const s = scaleRef.current;
      const r = rotationRef.current;
      for (let i = 1; i <= pdf.numPages; i += 1) {
        const page = await pdf.getPage(i);
        const viewport = page.getViewport({ scale: s, rotation: r });
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        if (!ctx) continue;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        // pdfjs-dist 4.x RenderParameters
        await page.render({
          canvasContext: ctx,
          viewport,
          canvas,
        } as Parameters<typeof page.render>[0]).promise;
        painted.push({
          pageNumber: i,
          canvas,
          width: viewport.width,
          height: viewport.height,
        });
      }
      pagesRef.current = painted;
      setPages(painted);
    },
    [],
  );

  useImperativeHandle(ref, () => ({
    jumpToPage(pageNumber: number) {
      const el = containerRef.current?.querySelector(
        `[data-pdf-page="${pageNumber}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    setHighlight({ pageNumber, bbox, approximate }) {
      const paint = pagesRef.current.find((p) => p.pageNumber === pageNumber);
      const rect =
        bboxToHighlightRect(bbox, paint?.width ?? 1, paint?.height ?? 1) ||
        (approximate || !bbox ? approximatePageHighlight() : null);
      if (!rect) return;
      clearHighlightTimers();
      setHighlightState({ pageNumber, rect, active: true, settled: false });
      highlightTimer.current = window.setTimeout(() => {
        setHighlightState((prev) =>
          prev ? { ...prev, active: false, settled: true } : null,
        );
      }, 7000);
      const el = containerRef.current?.querySelector(
        `[data-pdf-page="${pageNumber}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    },
    clearHighlight() {
      clearHighlightTimers();
      setHighlightState(null);
    },
    getPageCount() {
      return pagesRef.current.length;
    },
  }));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPages([]);
    pagesRef.current = [];
    fetch(contentUrl, { credentials: "same-origin" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buf = await res.arrayBuffer();
        if (cancelled) return;
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
        const loadingTask = pdfjs.getDocument({ data: buf });
        const pdf = await loadingTask.promise;
        if (cancelled) {
          await pdf.destroy();
          return;
        }
        pdfDocRef.current = pdf;
        await paintPages(pdf);
        if (!cancelled) onDocumentReady?.(pdf.numPages);
      })
      .catch((err) => {
        if (cancelled) return;
        onLoadError?.(err instanceof Error ? err.message : "Không tải được PDF.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      clearHighlightTimers();
      void pdfDocRef.current?.destroy();
      pdfDocRef.current = null;
    };
  }, [contentUrl, paintPages, onDocumentReady, onLoadError]);

  // Re-paint when zoom/rotation changes (cached PDFDocumentProxy).
  useEffect(() => {
    const pdf = pdfDocRef.current;
    if (!pdf) return;
    let cancelled = false;
    void paintPages(pdf).then(() => {
      if (cancelled) return;
    });
    return () => {
      cancelled = true;
    };
  }, [scale, rotation, paintPages]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "max-h-[70vh] space-y-4 overflow-y-auto scroll-smooth rounded-lg border border-border-default bg-elevated/30 p-3",
        className,
      )}
    >
      {loading ? (
        <div className="animate-pulse space-y-3" aria-busy>
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-64 rounded-md bg-elevated" />
          ))}
        </div>
      ) : null}
      {pages.map((page) => (
        <div
          key={page.pageNumber}
          data-pdf-page={page.pageNumber}
          className="relative mx-auto w-fit shadow-sm"
        >
          <canvas
            ref={(node) => {
              if (node && page.canvas) {
                const ctx = node.getContext("2d");
                if (!ctx) return;
                node.width = page.canvas.width;
                node.height = page.canvas.height;
                ctx.drawImage(page.canvas, 0, 0);
              }
            }}
            className="max-w-full"
            aria-label={`Trang ${page.pageNumber}`}
          />
          {highlight?.pageNumber === page.pageNumber ? (
            <HighlightOverlay
              rect={highlight.rect}
              active={highlight.active}
              settled={highlight.settled}
            />
          ) : null}
          <span className="absolute bottom-2 right-2 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white">
            {page.pageNumber}
          </span>
        </div>
      ))}
    </div>
  );
});
