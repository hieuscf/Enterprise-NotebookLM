/**
 * =============================================================================
 * File: PDFViewer.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Render Original PDF via pdf.js (never markdown).
 * Responsibilities:
 *   - Load PDF ArrayBuffer from content URL; render pages; expose jump API
 *   - Deterministic citation highlight via bbox / text-layer snippet rects
 * Dependencies:
 *   - pdfjs-dist, HighlightOverlay, pdf-text-highlight
 * Public Exports:
 *   - PDFViewer, PDFViewerHandle
 * Important Notes: Never paint approximate full-page bands for citations —
 *   navigate only when locator confidence is insufficient.
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
  bboxToHighlightRect,
  HighlightOverlay,
  type HighlightRect,
} from "@/features/documents/viewer/HighlightOverlay";
import { findSnippetRectsInTextContent } from "@/features/documents/viewer/pdf-text-highlight";
import { cn } from "@/lib/utils";

export type PDFViewerHandle = {
  jumpToPage: (pageNumber: number) => void;
  /**
   * Apply citation highlight after the page is in view.
   * Priority: explicit rects → text snippet (PDF text layer) → bbox → none.
   * `approximate: true` is ignored (never invent a wide band).
   */
  setHighlight: (args: {
    pageNumber: number;
    bbox?: number[] | null;
    rects?: HighlightRect[] | null;
    snippet?: string | null;
    approximate?: boolean;
  }) => Promise<boolean>;
  clearHighlight: () => void;
  getPageCount: () => number;
  waitForPage: (pageNumber: number, timeoutMs?: number) => Promise<boolean>;
};

type Props = {
  /** Absolute or same-origin URL returning PDF bytes. */
  contentUrl: string;
  scale: number;
  rotation: number;
  className?: string;
  onDocumentReady?: (pageCount: number) => void;
  onLoadError?: (message: string) => void;
  /** Fired when the most-visible page changes while scrolling. */
  onVisiblePageChange?: (pageNumber: number) => void;
};

type PagePaint = {
  pageNumber: number;
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
};

export const PDFViewer = forwardRef<PDFViewerHandle, Props>(function PDFViewer(
  {
    contentUrl,
    scale,
    rotation,
    className,
    onDocumentReady,
    onLoadError,
    onVisiblePageChange,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<PagePaint[]>([]);
  const pagesRef = useRef<PagePaint[]>([]);
  const [loading, setLoading] = useState(true);
  const [highlight, setHighlightState] = useState<{
    pageNumber: number;
    rects: HighlightRect[];
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
      // User delta only — must ADD to each page's intrinsic /Rotate metadata.
      // Passing rotation: 0 forces upright MediaBox and ignores page.rotate,
      // which makes landscape/scanned PDFs appear sideways.
      const userDelta = ((rotationRef.current % 360) + 360) % 360;
      for (let i = 1; i <= pdf.numPages; i += 1) {
        const page = await pdf.getPage(i);
        const viewport = page.getViewport({
          scale: s,
          rotation: (page.rotate + userDelta) % 360,
        });
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
    async waitForPage(pageNumber: number, timeoutMs = 4000) {
      const started = Date.now();
      while (Date.now() - started < timeoutMs) {
        if (pagesRef.current.some((p) => p.pageNumber === pageNumber)) {
          return true;
        }
        await new Promise((r) => window.setTimeout(r, 50));
      }
      return pagesRef.current.some((p) => p.pageNumber === pageNumber);
    },
    async setHighlight({ pageNumber, bbox, rects, snippet }) {
      const ready = await (async () => {
        const started = Date.now();
        while (Date.now() - started < 4000) {
          if (pagesRef.current.some((p) => p.pageNumber === pageNumber)) {
            return true;
          }
          await new Promise((r) => window.setTimeout(r, 50));
        }
        return pagesRef.current.some((p) => p.pageNumber === pageNumber);
      })();
      if (!ready) return false;

      const paint = pagesRef.current.find((p) => p.pageNumber === pageNumber);
      const pageWidth = paint?.width ?? 1;
      const pageHeight = paint?.height ?? 1;

      let nextRects: HighlightRect[] = Array.isArray(rects)
        ? rects.filter(Boolean)
        : [];

      // Prefer PDF text-layer match for citation sub-spans.
      if (nextRects.length === 0 && snippet?.trim() && pdfDocRef.current) {
        try {
          const page = await pdfDocRef.current.getPage(pageNumber);
          const userDelta = ((rotationRef.current % 360) + 360) % 360;
          const viewport = page.getViewport({
            scale: scaleRef.current,
            rotation: (page.rotate + userDelta) % 360,
          });
          const textContent = await page.getTextContent();
          nextRects = findSnippetRectsInTextContent(
            {
              items: textContent.items.map((item) => {
                if (!item || typeof item !== "object" || !("str" in item)) {
                  return { str: "" };
                }
                const ti = item as {
                  str?: string;
                  transform?: number[] | Float32Array;
                  width?: number;
                  height?: number;
                };
                return {
                  str: ti.str,
                  transform: ti.transform,
                  width: ti.width,
                  height: ti.height,
                };
              }),
            },
            snippet,
            viewport.width,
            viewport.height,
          );
        } catch {
          nextRects = [];
        }
      }

      if (nextRects.length === 0 && bbox) {
        const one = bboxToHighlightRect(bbox, pageWidth, pageHeight);
        if (one) nextRects = [one];
      }

      // No approximate band — navigate without a fake highlight when unsure.
      if (nextRects.length === 0) {
        clearHighlightTimers();
        setHighlightState(null);
        const el = containerRef.current?.querySelector(
          `[data-pdf-page="${pageNumber}"]`,
        );
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
        return false;
      }

      clearHighlightTimers();
      setHighlightState({
        pageNumber,
        rects: nextRects,
        active: true,
        settled: false,
      });
      highlightTimer.current = window.setTimeout(() => {
        setHighlightState((prev) =>
          prev ? { ...prev, active: false, settled: true } : null,
        );
      }, 8000);
      const el = containerRef.current?.querySelector(
        `[data-pdf-page="${pageNumber}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      return true;
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

  // Track which page is most visible in the scroll viewport.
  useEffect(() => {
    if (!onVisiblePageChange || pages.length === 0) return;
    const root = containerRef.current;
    if (!root) return;

    const ratios = new Map<number, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const pageAttr = (entry.target as HTMLElement).dataset.pdfPage;
          const pageNumber = pageAttr ? Number(pageAttr) : NaN;
          if (!Number.isFinite(pageNumber)) continue;
          ratios.set(pageNumber, entry.intersectionRatio);
        }
        let bestPage = 1;
        let bestRatio = -1;
        for (const [page, ratio] of ratios) {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestPage = page;
          }
        }
        if (bestRatio >= 0) onVisiblePageChange(bestPage);
      },
      { root, threshold: [0.15, 0.35, 0.55, 0.75] },
    );

    for (const el of root.querySelectorAll("[data-pdf-page]")) {
      observer.observe(el);
    }
    return () => observer.disconnect();
  }, [pages, onVisiblePageChange]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "max-h-[70vh] space-y-6 overflow-y-auto scroll-smooth rounded-md bg-elevated/30 p-4 sm:p-6",
        className,
      )}
    >
      {loading ? (
        <div className="animate-pulse space-y-3" aria-busy>
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="mx-auto h-72 max-w-2xl rounded-sm bg-elevated" />
          ))}
        </div>
      ) : null}
      {pages.map((page) => (
        <div
          key={page.pageNumber}
          data-pdf-page={page.pageNumber}
          className="relative mx-auto w-fit bg-white shadow-[0_1px_3px_rgba(15,23,42,0.08),0_8px_24px_rgba(15,23,42,0.06)]"
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
            aria-label={`Page ${page.pageNumber}`}
          />
          {highlight?.pageNumber === page.pageNumber
            ? highlight.rects.map((rect, idx) => (
                <HighlightOverlay
                  key={`${page.pageNumber}-${idx}`}
                  rect={rect}
                  active={highlight.active}
                  settled={highlight.settled}
                />
              ))
            : null}
          <span className="absolute right-2 bottom-2 rounded bg-slate-900/45 px-1.5 py-0.5 text-[10px] text-white">
            {page.pageNumber}
          </span>
        </div>
      ))}
    </div>
  );
});
