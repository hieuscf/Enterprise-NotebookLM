/**
 * =============================================================================
 * File: PDFViewer.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Render Original PDF via pdf.js (never markdown).
 * Responsibilities:
 *   - Load PDF; measure pages; paint pages as they enter the scroll viewport
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
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
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

type PageSlot = {
  pageNumber: number;
  width: number;
  height: number;
};

function userRotation(rotation: number): number {
  return ((rotation % 360) + 360) % 360;
}

async function paintPageToCanvas(
  pdf: import("pdfjs-dist").PDFDocumentProxy,
  pageNumber: number,
  canvas: HTMLCanvasElement,
  scale: number,
  rotation: number,
): Promise<{ width: number; height: number } | null> {
  const page = await pdf.getPage(pageNumber);
  const viewport = page.getViewport({
    scale,
    rotation: (page.rotate + userRotation(rotation)) % 360,
  });
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({
    canvasContext: ctx,
    viewport,
    canvas,
  } as Parameters<typeof page.render>[0]).promise;
  return { width: viewport.width, height: viewport.height };
}

export const PDFViewer = memo(forwardRef<PDFViewerHandle, Props>(function PDFViewer(
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
  const canvasByPage = useRef(new Map<number, HTMLCanvasElement>());
  const painted = useRef(new Set<number>());
  const painting = useRef(new Set<number>());
  const lastLayout = useRef({ scale, rotation });
  const onDocumentReadyRef = useRef(onDocumentReady);
  const onLoadErrorRef = useRef(onLoadError);
  const onVisiblePageChangeRef = useRef(onVisiblePageChange);
  onDocumentReadyRef.current = onDocumentReady;
  onLoadErrorRef.current = onLoadError;
  onVisiblePageChangeRef.current = onVisiblePageChange;
  const [slots, setSlots] = useState<PageSlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [highlight, setHighlightState] = useState<{
    pageNumber: number;
    rects: HighlightRect[];
    active: boolean;
    settled: boolean;
  } | null>(null);
  const slotsRef = useRef<PageSlot[]>([]);
  slotsRef.current = slots;
  const pdfDocRef = useRef<import("pdfjs-dist").PDFDocumentProxy | null>(null);
  const highlightTimer = useRef<number | null>(null);
  const scaleRef = useRef(scale);
  const rotationRef = useRef(rotation);
  scaleRef.current = scale;
  rotationRef.current = rotation;

  const registerCanvas = useCallback(
    (pageNumber: number, node: HTMLCanvasElement | null) => {
      if (node) canvasByPage.current.set(pageNumber, node);
      else canvasByPage.current.delete(pageNumber);
    },
    [],
  );

  const clearHighlightTimers = () => {
    if (highlightTimer.current != null) {
      window.clearTimeout(highlightTimer.current);
      highlightTimer.current = null;
    }
  };

  const ensurePainted = useCallback(async (pageNumber: number): Promise<boolean> => {
    if (painted.current.has(pageNumber)) return true;
    if (painting.current.has(pageNumber)) {
      const started = Date.now();
      while (Date.now() - started < 4000) {
        if (painted.current.has(pageNumber)) return true;
        if (!painting.current.has(pageNumber)) break;
        await new Promise((r) => window.setTimeout(r, 40));
      }
      return painted.current.has(pageNumber);
    }
    const pdf = pdfDocRef.current;
    const canvas = canvasByPage.current.get(pageNumber);
    if (!pdf || !canvas) return false;
    painting.current.add(pageNumber);
    try {
      const paintedSize = await paintPageToCanvas(
        pdf,
        pageNumber,
        canvas,
        scaleRef.current,
        rotationRef.current,
      );
      if (!paintedSize) return false;
      painted.current.add(pageNumber);
      return true;
    } catch {
      return false;
    } finally {
      painting.current.delete(pageNumber);
    }
  }, []);

  const measurePages = useCallback(
    async (pdf: import("pdfjs-dist").PDFDocumentProxy) => {
      const s = scaleRef.current;
      const userDelta = userRotation(rotationRef.current);
      const next: PageSlot[] = [];
      for (let i = 1; i <= pdf.numPages; i += 1) {
        const page = await pdf.getPage(i);
        const viewport = page.getViewport({
          scale: s,
          rotation: (page.rotate + userDelta) % 360,
        });
        next.push({
          pageNumber: i,
          width: viewport.width,
          height: viewport.height,
        });
      }
      painted.current.clear();
      painting.current.clear();
      lastLayout.current = { scale: s, rotation: rotationRef.current };
      setSlots(next);
    },
    [],
  );

  useImperativeHandle(ref, () => ({
    jumpToPage(pageNumber: number) {
      void ensurePainted(pageNumber);
      const el = containerRef.current?.querySelector(
        `[data-pdf-page="${pageNumber}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    async waitForPage(pageNumber: number, timeoutMs = 4000) {
      const started = Date.now();
      while (Date.now() - started < timeoutMs) {
        if (canvasByPage.current.has(pageNumber)) {
          if (painted.current.has(pageNumber) || (await ensurePainted(pageNumber))) {
            return true;
          }
        }
        await new Promise((r) => window.setTimeout(r, 50));
      }
      return painted.current.has(pageNumber);
    },
    async setHighlight({ pageNumber, bbox, rects, snippet }) {
      const ready = await (async () => {
        const started = Date.now();
        while (Date.now() - started < 4000) {
          if (canvasByPage.current.has(pageNumber)) break;
          await new Promise((r) => window.setTimeout(r, 50));
        }
        return ensurePainted(pageNumber);
      })();
      if (!ready) return false;

      const slot = slotsRef.current.find((p) => p.pageNumber === pageNumber);
      const canvas = canvasByPage.current.get(pageNumber);
      const pageWidth = canvas?.width || slot?.width || 1;
      const pageHeight = canvas?.height || slot?.height || 1;

      let nextRects: HighlightRect[] = Array.isArray(rects)
        ? rects.filter(Boolean)
        : [];

      if (nextRects.length === 0 && snippet?.trim() && pdfDocRef.current) {
        try {
          const page = await pdfDocRef.current.getPage(pageNumber);
          const viewport = page.getViewport({
            scale: scaleRef.current,
            rotation: (page.rotate + userRotation(rotationRef.current)) % 360,
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

      const el = containerRef.current?.querySelector(
        `[data-pdf-page="${pageNumber}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "center" });

      if (nextRects.length === 0) {
        clearHighlightTimers();
        setHighlightState(null);
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
      return true;
    },
    clearHighlight() {
      clearHighlightTimers();
      setHighlightState(null);
    },
    getPageCount() {
      return slotsRef.current.length;
    },
  }));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSlots([]);
    painted.current.clear();
    painting.current.clear();
    canvasByPage.current.clear();
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
        await measurePages(pdf);
        if (!cancelled) onDocumentReadyRef.current?.(pdf.numPages);
      })
      .catch((err) => {
        if (cancelled) return;
        onLoadErrorRef.current?.(
          err instanceof Error ? err.message : "Không tải được PDF.",
        );
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
  }, [contentUrl, measurePages]);

  useEffect(() => {
    const pdf = pdfDocRef.current;
    if (!pdf) return;
    if (
      lastLayout.current.scale === scale &&
      lastLayout.current.rotation === rotation
    ) {
      return;
    }
    let cancelled = false;
    void measurePages(pdf).then(() => {
      if (cancelled) return;
    });
    return () => {
      cancelled = true;
    };
  }, [scale, rotation, measurePages]);

  useEffect(() => {
    const root = containerRef.current;
    if (!root || slots.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const pageAttr = (entry.target as HTMLElement).dataset.pdfPage;
          const pageNumber = pageAttr ? Number(pageAttr) : NaN;
          if (!Number.isFinite(pageNumber)) continue;
          if (painted.current.has(pageNumber) || painting.current.has(pageNumber)) {
            continue;
          }
          void ensurePainted(pageNumber);
        }
      },
      { root, rootMargin: "1200px 0px", threshold: 0.01 },
    );

    for (const el of root.querySelectorAll("[data-pdf-page]")) {
      observer.observe(el);
    }
    return () => observer.disconnect();
  }, [slots, ensurePainted]);

  useEffect(() => {
    if (slots.length === 0) return;
    const root = containerRef.current;
    if (!root) return;

    const ratios = new Map<number, number>();
    let lastReported = 0;
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
        if (bestRatio >= 0 && bestPage !== lastReported) {
          lastReported = bestPage;
          onVisiblePageChangeRef.current?.(bestPage);
        }
      },
      { root, threshold: [0.15, 0.35, 0.55, 0.75] },
    );

    for (const el of root.querySelectorAll("[data-pdf-page]")) {
      observer.observe(el);
    }
    return () => observer.disconnect();
  }, [slots]);

  return (
    <div
      ref={containerRef}
        className={cn(
          "min-h-0 flex-1 overflow-x-auto overflow-y-auto scroll-smooth rounded-md bg-elevated/30 p-4 sm:p-6",
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
      <div className="flex flex-col gap-6">
        {slots.map((page) => (
          <PdfPage
            key={page.pageNumber}
            page={page}
            highlight={
              highlight?.pageNumber === page.pageNumber ? highlight : null
            }
            onCanvas={registerCanvas}
          />
        ))}
      </div>
    </div>
  );
}));

const PdfPage = memo(function PdfPage({
  page,
  highlight,
  onCanvas,
}: {
  page: PageSlot;
  highlight: {
    pageNumber: number;
    rects: HighlightRect[];
    active: boolean;
    settled: boolean;
  } | null;
  onCanvas: (pageNumber: number, node: HTMLCanvasElement | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useLayoutEffect(() => {
    onCanvas(page.pageNumber, canvasRef.current);
    return () => onCanvas(page.pageNumber, null);
  }, [onCanvas, page.pageNumber]);

  return (
    <div
      data-pdf-page={page.pageNumber}
      className="relative mx-auto w-full bg-white shadow-[0_1px_3px_rgba(15,23,42,0.08),0_8px_24px_rgba(15,23,42,0.06)]"
      style={{
        maxWidth: page.width,
        aspectRatio: `${page.width} / ${page.height}`,
      }}
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 block h-full w-full"
        aria-label={`Page ${page.pageNumber}`}
      />
      {highlight
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
  );
});
