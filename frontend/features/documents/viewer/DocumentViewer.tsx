/**
 * =============================================================================
 * File: DocumentViewer.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Enterprise document reading workspace — Knowledge View (canonical)
 *          + Original View (PDF), outline, AI inspector, citation focus.
 * Responsibilities:
 *   - Load canonical markdown/blocks + chunk metadata; default Knowledge View
 *   - Citation highlight via block ranges; Original View for provenance PDF
 * Dependencies:
 *   - KnowledgeView, PDFViewer, ChunkNavigator, ViewerToolbar, AIContextPanel
 * Public Exports:
 *   - DocumentViewer
 * Database/Table: document_chunks, document_versions (markdown_storage_path)
 * Related Modules: DocumentDetailView
 * Important Notes: Do not re-chunk on open; find-in-document uses canonical blocks.
 * =============================================================================
 */

"use client";

import { List, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AIContextPanel } from "@/features/documents/viewer/AIContextPanel";
import { ChunkNavigator } from "@/features/documents/viewer/ChunkNavigator";
import { KnowledgeView } from "@/features/documents/viewer/KnowledgeView";
import { KnowledgeSkeleton } from "@/features/documents/viewer/knowledge/DocumentRenderer";
import { findBlockForSnippet } from "@/features/documents/viewer/knowledge/citation-highlight";
import {
  PDFViewer,
  type PDFViewerHandle,
} from "@/features/documents/viewer/PDFViewer";
import { SnippetNavigator } from "@/features/documents/viewer/SnippetNavigator";
import { ViewerToolbar } from "@/features/documents/viewer/ViewerToolbar";
import {
  ApiClientError,
  documentContentUrl,
  getCanonicalDocument,
  listDocumentChunks,
} from "@/lib/api-client";
import { loadSearchMatches } from "@/lib/search-matches";
import { cn } from "@/lib/utils";
import type { CanonicalDocument } from "@/types/canonical";
import type {
  Document,
  DocumentChunk,
  DocumentChunkListResponse,
  DocumentVersion,
} from "@/types/documents";

type Props = {
  workspaceId: string;
  documentId: string;
  document?: Document | null;
  currentVersion?: DocumentVersion | null;
  focusChunkId: string | null;
  focusPage: number | null;
  focusCitationId?: string | null;
  focusSnippet?: string | null;
  focusVersionId?: string | null;
  focusLocator?: import("@/types/canonical").CitationLocator | null;
  initialView?: "knowledge" | "original";
  onOpenVersionHistory?: () => void;
  onMissingChunk?: () => void;
  onHighlightFailed?: () => void;
};

type TocNode = {
  key: string;
  label: string;
  page?: number | null;
  blockId?: string | null;
  children?: TocNode[];
};

type NavTab = "outline" | "pages";
type ViewMode = "knowledge" | "original";

type LocalFindHit = {
  chunkId: string;
  pageNumber: number | null;
  snippet: string;
  blockId?: string | null;
};

export function DocumentViewer({
  workspaceId,
  documentId,
  document = null,
  currentVersion = null,
  focusChunkId,
  focusPage,
  focusCitationId = null,
  focusSnippet = null,
  focusVersionId = null,
  focusLocator = null,
  initialView = "knowledge",
  onOpenVersionHistory,
  onMissingChunk,
  onHighlightFailed,
}: Props) {
  const router = useRouter();
  const pdfRef = useRef<PDFViewerHandle | null>(null);
  const findInputRef = useRef<HTMLInputElement | null>(null);

  const [meta, setMeta] = useState<DocumentChunkListResponse | null>(null);
  const [canonical, setCanonical] = useState<CanonicalDocument | null>(null);
  const [canonicalError, setCanonicalError] = useState<string | null>(null);
  const [canonicalLoading, setCanonicalLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>(initialView);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [metaReady, setMetaReady] = useState(false);
  const [pdfReady, setPdfReady] = useState(false);
  const [scale, setScale] = useState(1.1);
  const [rotation, setRotation] = useState(0);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [navTab, setNavTab] = useState<NavTab>("outline");
  const [navOpen, setNavOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [activeChunkId, setActiveChunkId] = useState<string | null>(focusChunkId);
  const [activeBlockId, setActiveBlockId] = useState<string | null>(
    focusLocator?.ranges?.[0]?.block_id ?? null,
  );
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [citationSnippetPreview, setCitationSnippetPreview] = useState<string | null>(
    focusSnippet,
  );
  const [contentKey, setContentKey] = useState(0);

  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [findHits, setFindHits] = useState<LocalFindHit[]>([]);
  const [findIndex, setFindIndex] = useState(0);

  const contentUrl = useMemo(
    () =>
      documentContentUrl(workspaceId, documentId, {
        versionId: focusVersionId,
      }),
    [workspaceId, documentId, focusVersionId],
  );
  const downloadUrl = useMemo(
    () =>
      documentContentUrl(workspaceId, documentId, {
        versionId: focusVersionId,
        download: true,
      }),
    [workspaceId, documentId, focusVersionId],
  );

  const storedMatches = useMemo(
    () => loadSearchMatches(workspaceId, documentId),
    [workspaceId, documentId],
  );
  const matches = storedMatches?.matches ?? [];
  const matchIndex = Math.max(
    0,
    matches.findIndex((m) => m.chunkId === activeChunkId),
  );

  useEffect(() => {
    setActiveChunkId(focusChunkId);
  }, [focusChunkId]);

  useEffect(() => {
    setCitationSnippetPreview(focusSnippet);
  }, [focusSnippet]);

  useEffect(() => {
    setViewMode(initialView);
  }, [initialView]);

  useEffect(() => {
    const id =
      focusLocator?.ranges?.find((r) => r.end > r.start)?.block_id ?? null;
    if (id) setActiveBlockId(id);
  }, [focusLocator]);

  useEffect(() => {
    let active = true;
    setCanonicalLoading(true);
    setCanonicalError(null);

    async function loadCanonical() {
      try {
        const data = await getCanonicalDocument(
          workspaceId,
          documentId,
          focusVersionId,
        );
        if (!active) return;
        setCanonical(data);
        setCanonicalError(null);
      } catch (err) {
        if (!active) return;
        setCanonical(null);
        setCanonicalError(
          err instanceof ApiClientError
            ? err.message
            : "Canonical document unavailable.",
        );
      } finally {
        if (active) setCanonicalLoading(false);
      }
    }
    void loadCanonical();
    return () => {
      active = false;
    };
  }, [workspaceId, documentId, focusVersionId]);

  useEffect(() => {
    setPdfReady(false);
    setPdfError(null);
    setPageCount(0);
    setCurrentPage(1);
  }, [contentUrl, contentKey]);

  useEffect(() => {
    if (focusChunkId || focusCitationId || focusSnippet) return;
    if (!pdfReady || !focusPage || focusPage <= 0) return;
    pdfRef.current?.jumpToPage(focusPage);
    setCurrentPage(focusPage);
  }, [focusChunkId, focusCitationId, focusSnippet, focusPage, pdfReady]);

  useEffect(() => {
    let active = true;
    let timer: number | null = null;

    async function load(poll: boolean) {
      try {
        const data = await listDocumentChunks(
          workspaceId,
          documentId,
          focusVersionId,
        );
        if (!active) return;
        setMeta(data);
        setMetaReady(true);
        setMetaError(null);
        const status = data.preview_status ?? "pending";
        if (poll && (status === "pending" || status === "processing")) {
          timer = window.setTimeout(() => {
            void load(true);
          }, 2000);
        }
      } catch (err) {
        if (!active) return;
        setMetaError(
          err instanceof ApiClientError
            ? err.message
            : "Unable to load document metadata.",
        );
      }
    }

    setMetaReady(false);
    void load(true);
    return () => {
      active = false;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [workspaceId, documentId, focusVersionId]);

  // Debounced find-in-document against Canonical blocks (preferred) or chunks.
  useEffect(() => {
    const q = findQuery.trim().toLowerCase();
    if (!q) {
      setFindHits([]);
      setFindIndex(0);
      return;
    }
    const t = window.setTimeout(() => {
      const hits: LocalFindHit[] = [];
      if (canonical?.blocks?.length) {
        for (const block of canonical.blocks) {
          const content = block.content?.toLowerCase() ?? "";
          if (!content.includes(q)) continue;
          const idx = content.indexOf(q);
          const start = Math.max(0, idx - 40);
          const end = Math.min(block.content.length, idx + q.length + 60);
          hits.push({
            chunkId: block.id,
            pageNumber: block.page_number ?? null,
            snippet: block.content.slice(start, end),
            blockId: block.id,
          });
          if (hits.length >= 50) break;
        }
      } else if (meta?.items?.length) {
        for (const chunk of meta.items) {
          const content = chunk.content?.toLowerCase() ?? "";
          if (!content.includes(q)) continue;
          const idx = content.indexOf(q);
          const start = Math.max(0, idx - 40);
          const end = Math.min(chunk.content.length, idx + q.length + 60);
          hits.push({
            chunkId: chunk.id,
            pageNumber: chunk.page_number ?? null,
            snippet: chunk.content.slice(start, end),
            blockId: chunk.block_ids?.[0] ?? null,
          });
          if (hits.length >= 50) break;
        }
      }
      setFindHits(hits);
      setFindIndex(0);
    }, 220);
    return () => window.clearTimeout(t);
  }, [findQuery, meta, canonical]);

  const activeChunk: DocumentChunk | null = useMemo(() => {
    if (!meta || !activeChunkId) return null;
    return meta.items.find((c) => c.id === activeChunkId) ?? null;
  }, [meta, activeChunkId]);

  /** Block to scroll to when locator confidence is none / snippet differs from markdown. */
  const knowledgeFallbackBlockId = useMemo(() => {
    const locRange = focusLocator?.ranges?.find((r) => r.end > r.start);
    if (
      locRange &&
      focusLocator?.confidence &&
      focusLocator.confidence !== "none"
    ) {
      return locRange.block_id;
    }
    if (!canonical?.blocks?.length) return null;
    if (focusSnippet?.trim()) {
      const block = findBlockForSnippet(canonical.blocks, focusSnippet.trim());
      if (block) return block.id;
    }
    if (activeChunk?.content?.trim()) {
      const block = findBlockForSnippet(
        canonical.blocks,
        activeChunk.content.trim().slice(0, 240),
      );
      if (block) return block.id;
    }
    if (focusPage && focusPage > 0) {
      const byPage = canonical.blocks.find((b) => b.page_number === focusPage);
      if (byPage) return byPage.id;
    }
    return locRange?.block_id ?? null;
  }, [canonical, focusLocator, focusSnippet, activeChunk, focusPage]);

  useEffect(() => {
    if (knowledgeFallbackBlockId) {
      setActiveBlockId(knowledgeFallbackBlockId);
    }
  }, [knowledgeFallbackBlockId]);

  // Knowledge View unavailable → Original View still has ChunkNavigator.
  useEffect(() => {
    if (canonicalLoading) return;
    if (canonical) return;
    if (initialView !== "knowledge") return;
    if (focusChunkId || (focusPage != null && focusPage > 0)) {
      setViewMode("original");
    }
  }, [canonicalLoading, canonical, initialView, focusChunkId, focusPage]);

  const handleKnowledgeNavFailed = useCallback(() => {
    if (focusChunkId || (focusPage != null && focusPage > 0)) {
      setViewMode("original");
      return;
    }
    onHighlightFailed?.();
  }, [focusChunkId, focusPage, onHighlightFailed]);

  const activeMatch = matches[matchIndex] ?? null;
  const toc = useMemo(
    () =>
      buildToc(
        canonical?.heading_tree?.length
          ? canonical.heading_tree
          : meta?.heading_tree,
        meta?.items ?? [],
      ),
    [meta, canonical],
  );

  const pageEntries = useMemo(() => {
    const count =
      pageCount ||
      currentVersion?.page_count ||
      Math.max(
        0,
        ...(meta?.items ?? []).map((c) => c.page_number ?? 0),
      );
    const labels = new Map<number, string>();
    for (const node of flattenToc(toc)) {
      if (node.page && !labels.has(node.page)) {
        labels.set(node.page, node.label);
      }
    }
    return Array.from({ length: count }, (_, i) => {
      const page = i + 1;
      return { page, label: labels.get(page) ?? null };
    });
  }, [pageCount, currentVersion?.page_count, meta, toc]);

  const previewStatus = meta?.preview_status ?? "pending";
  const previewReady = previewStatus === "completed";
  const previewFailed = previewStatus === "failed";
  const previewBusy =
    previewStatus === "pending" || previewStatus === "processing";
  const viewerKind =
    previewReady && meta?.viewer_kind === "pdf" ? "pdf" : "original_download";

  const handleMissing = useCallback(() => {
    onMissingChunk?.();
    if (focusPage && focusPage > 0) {
      pdfRef.current?.jumpToPage(focusPage);
      setCurrentPage(focusPage);
    }
  }, [onMissingChunk, focusPage]);

  const handleLocated = useCallback((chunk: DocumentChunk) => {
    const key = chunk.heading_path || chunk.section_path || chunk.section;
    if (key) setActiveSection(key);
    if (chunk.page_number) setCurrentPage(chunk.page_number);
  }, []);

  const handlePdfReady = useCallback((count: number) => {
    setPdfReady(true);
    setPageCount(count);
  }, []);

  const handlePdfError = useCallback((msg: string) => {
    setPdfError(msg);
  }, []);

  const jumpToPage = useCallback((page: number) => {
    pdfRef.current?.jumpToPage(page);
    setCurrentPage(page);
  }, []);

  const goMatch = useCallback(
    (nextIndex: number) => {
      const entry = matches[nextIndex];
      if (!entry) return;
      setActiveChunkId(entry.chunkId);
      const params = new URLSearchParams();
      params.set("chunk", entry.chunkId);
      if (entry.pageNumber) params.set("page", String(entry.pageNumber));
      router.replace(
        `/workspaces/${workspaceId}/documents/${documentId}?${params.toString()}`,
        { scroll: false },
      );
    },
    [matches, router, workspaceId, documentId],
  );

  const goFindHit = useCallback(
    (index: number) => {
      const hit = findHits[index];
      if (!hit) return;
      setFindIndex(index);
      if (hit.blockId) {
        setActiveBlockId(hit.blockId);
        setViewMode("knowledge");
      } else {
        setActiveChunkId(hit.chunkId);
        if (hit.pageNumber) {
          setViewMode("original");
          jumpToPage(hit.pageNumber);
        }
      }
    },
    [findHits, jumpToPage],
  );

  const askAi = useCallback(
    (text: string) => {
      const q = encodeURIComponent(
        text.length > 500 ? `${text.slice(0, 500)}…` : text,
      );
      router.push(
        `/workspaces/${workspaceId}/chat?documentId=${documentId}&q=${q}`,
      );
    },
    [router, workspaceId, documentId],
  );

  // Keyboard shortcuts (ignore when typing in inputs).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (typing) {
        if (e.key === "Escape") {
          (target as HTMLElement).blur();
          setFindOpen(false);
        }
        return;
      }

      if (e.key === "/" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setFindOpen(true);
        window.setTimeout(() => findInputRef.current?.focus(), 0);
        return;
      }
      if (e.key === "Escape") {
        setFindOpen(false);
        return;
      }
      if (viewerKind !== "pdf" || !pdfReady) return;
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setScale((s) => Math.min(2.5, s + 0.15));
      } else if (e.key === "-") {
        e.preventDefault();
        setScale((s) => Math.max(0.5, s - 0.15));
      } else if (e.key === "0") {
        e.preventDefault();
        setScale(1);
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        setScale(1.25);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        jumpToPage(Math.max(1, currentPage - 1));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        jumpToPage(Math.min(Math.max(pageCount, 1), currentPage + 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewerKind, pdfReady, currentPage, pageCount, jumpToPage]);

  useEffect(() => {
    if (findOpen) findInputRef.current?.focus();
  }, [findOpen]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-default px-2.5 text-caption font-medium text-secondary hover:bg-elevated lg:hidden"
          onClick={() => setNavOpen((v) => !v)}
        >
          <List className="h-3.5 w-3.5" aria-hidden />
          Outline
        </button>
        <div className="inline-flex h-8 items-center rounded-md border border-border-default p-0.5">
          <button
            type="button"
            className={cn(
              "h-7 rounded px-2.5 text-caption font-medium",
              viewMode === "knowledge"
                ? "bg-accent-primary-soft text-accent-primary"
                : "text-tertiary hover:text-secondary",
            )}
            onClick={() => setViewMode("knowledge")}
            disabled={!canonical && Boolean(canonicalError)}
          >
            Knowledge
          </button>
          <button
            type="button"
            className={cn(
              "h-7 rounded px-2.5 text-caption font-medium",
              viewMode === "original"
                ? "bg-accent-primary-soft text-accent-primary"
                : "text-tertiary hover:text-secondary",
            )}
            onClick={() => setViewMode("original")}
          >
            Original
          </button>
        </div>
        <div className="min-w-0 flex-1">
          <ViewerToolbar
            variant={viewMode}
            sectionLabel={viewMode === "knowledge" ? activeSection : null}
            scale={scale}
            page={currentPage}
            pageCount={pageCount || currentVersion?.page_count || 0}
            searchOpen={findOpen}
            disabled={viewerKind !== "pdf" || !pdfReady}
            onZoomIn={() => setScale((s) => Math.min(2.5, s + 0.15))}
            onZoomOut={() => setScale((s) => Math.max(0.5, s - 0.15))}
            onFitWidth={() => setScale(1.25)}
            onFitPage={() => setScale(1)}
            onRotate={() => setRotation((r) => (r + 90) % 360)}
            onRefresh={() => setContentKey((k) => k + 1)}
            onDownload={() =>
              window.open(downloadUrl, "_blank", "noopener,noreferrer")
            }
            onOpenOriginal={() => setViewMode("original")}
            onPrint={() => window.print()}
            onPrevPage={() => jumpToPage(Math.max(1, currentPage - 1))}
            onNextPage={() =>
              jumpToPage(Math.min(Math.max(pageCount, 1), currentPage + 1))
            }
            onJumpPage={jumpToPage}
            onToggleSearch={() => setFindOpen((v) => !v)}
          />
        </div>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-default px-2.5 text-caption font-medium text-secondary hover:bg-elevated xl:hidden"
          onClick={() => setInspectorOpen((v) => !v)}
        >
          AI Context
        </button>
        <button
          type="button"
          className="hidden h-8 w-8 items-center justify-center rounded-md text-tertiary hover:bg-elevated lg:inline-flex"
          onClick={() => setNavOpen((v) => !v)}
          aria-label={navOpen ? "Hide navigation" : "Show navigation"}
          title={navOpen ? "Hide navigation" : "Show navigation"}
        >
          {navOpen ? (
            <PanelLeftClose className="h-4 w-4" aria-hidden />
          ) : (
            <PanelLeftOpen className="h-4 w-4" aria-hidden />
          )}
        </button>
      </div>

      {findOpen ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-md border border-border-default bg-surface px-3 py-2">
          <label htmlFor="doc-find" className="sr-only">
            Search this document
          </label>
          <input
            ref={findInputRef}
            id="doc-find"
            value={findQuery}
            onChange={(e) => setFindQuery(e.target.value)}
            placeholder="Search this document…"
            className="h-9 min-w-[12rem] flex-1 rounded-md border border-border-default bg-base px-3 text-body-sm outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (e.shiftKey) goFindHit(Math.max(0, findIndex - 1));
                else goFindHit(Math.min(findHits.length - 1, findIndex + 1));
              }
            }}
          />
          <span className="text-caption tabular-nums text-tertiary">
            {findQuery.trim()
              ? findHits.length
                ? `${findIndex + 1} / ${findHits.length}`
                : "0 matches"
              : "—"}
          </span>
          <button
            type="button"
            className="h-8 rounded-md border border-border-default px-2 text-caption disabled:opacity-40"
            disabled={!findHits.length}
            onClick={() => goFindHit(Math.max(0, findIndex - 1))}
          >
            Prev
          </button>
          <button
            type="button"
            className="h-8 rounded-md border border-border-default px-2 text-caption disabled:opacity-40"
            disabled={!findHits.length}
            onClick={() =>
              goFindHit(Math.min(findHits.length - 1, findIndex + 1))
            }
          >
            Next
          </button>
          <button
            type="button"
            className="rounded-md p-1.5 text-tertiary hover:bg-elevated"
            aria-label="Close search"
            onClick={() => setFindOpen(false)}
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      ) : null}

      {metaError ? (
        <p role="alert" className="text-body-sm text-danger">
          {metaError}
        </p>
      ) : null}
      {previewReady && pdfError ? (
        <p role="alert" className="text-body-sm text-danger">
          {pdfError}
        </p>
      ) : null}

      <div
        className={cn(
          "grid min-h-0 flex-1 gap-3",
          navOpen && inspectorOpen
            ? "xl:grid-cols-[220px_minmax(0,1fr)_280px]"
            : navOpen
              ? "xl:grid-cols-[220px_minmax(0,1fr)]"
              : inspectorOpen
                ? "xl:grid-cols-[minmax(0,1fr)_280px]"
                : "xl:grid-cols-[minmax(0,1fr)]",
        )}
      >
        {/* Left navigation */}
        <aside
          className={cn(
            "flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-border-default bg-surface",
            navOpen ? "flex" : "hidden",
          )}
        >
          <div
            role="tablist"
            className="flex shrink-0 border-b border-border-default"
          >
            {(
              [
                { id: "outline" as const, label: "Outline" },
                { id: "pages" as const, label: "Pages" },
              ] as const
            ).map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={navTab === t.id}
                onClick={() => setNavTab(t.id)}
                className={cn(
                  "flex-1 px-3 py-2 text-caption font-semibold tracking-wide uppercase",
                  navTab === t.id
                    ? "border-b-2 border-accent-primary text-accent-primary"
                    : "text-tertiary hover:text-secondary",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {navTab === "outline" ? (
              toc.length === 0 ? (
                <p className="px-2 py-4 text-caption text-secondary">
                  No outline available yet.
                </p>
              ) : (
                <TocList
                  nodes={toc}
                  activeKey={activeSection}
                  onSelect={(node) => {
                    setActiveSection(node.key);
                    if (node.blockId) {
                      setActiveBlockId(node.blockId);
                      setViewMode("knowledge");
                    } else if (node.page) {
                      setViewMode("original");
                      jumpToPage(node.page);
                    }
                  }}
                />
              )
            ) : pageEntries.length === 0 ? (
              <p className="px-2 py-4 text-caption text-secondary">
                Page list unavailable until preview is ready.
              </p>
            ) : (
              <ul className="flex flex-col gap-0.5">
                {pageEntries.map((entry) => (
                  <li key={entry.page}>
                    <button
                      type="button"
                      onClick={() => {
                        setViewMode("original");
                        jumpToPage(entry.page);
                      }}
                      className={cn(
                        "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                        currentPage === entry.page
                          ? "bg-accent-primary-soft text-accent-primary"
                          : "text-secondary hover:bg-elevated hover:text-primary",
                      )}
                    >
                      <span className="w-6 shrink-0 text-caption tabular-nums opacity-70">
                        {String(entry.page).padStart(2, "0")}
                      </span>
                      <span className="min-w-0 truncate text-caption">
                        {entry.label || `Page ${entry.page}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* Canvas */}
        <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
          {viewMode === "knowledge" ? (
            canonical ? (
              <KnowledgeView
                blocks={canonical.blocks}
                markdownFallback={canonical.markdown}
                documentTitle={canonical.document_title}
                locator={focusLocator}
                highlightSnippet={focusSnippet}
                activeBlockId={activeBlockId}
                fallbackBlockId={knowledgeFallbackBlockId}
                onBlockVisible={setActiveBlockId}
                onNavigationFailed={handleKnowledgeNavFailed}
              />
            ) : canonicalLoading ? (
              <KnowledgeSkeleton />
            ) : (
              <div className="flex h-full min-h-[28rem] flex-col items-center justify-center gap-3 rounded-md border border-border-default bg-elevated/20 px-6">
                <p className="text-body-sm font-medium text-primary">
                  {canonicalError
                    ? "Knowledge View unavailable"
                    : "Document content is unavailable."}
                </p>
                <p className="max-w-sm text-center text-caption text-secondary">
                  {canonicalError ||
                    "Canonical Markdown could not be loaded for this version."}
                </p>
                <button
                  type="button"
                  className="mt-2 inline-flex h-9 items-center rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white"
                  onClick={() => setViewMode("original")}
                >
                  Open Original View
                </button>
              </div>
            )
          ) : previewBusy ? (
            <div
              className="flex h-full min-h-[28rem] flex-col items-center justify-center gap-3 rounded-md border border-border-default bg-elevated/20 px-6"
              aria-busy
              aria-live="polite"
            >
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
              <p className="text-body-sm font-medium text-primary">
                Preparing document preview…
              </p>
              <p className="text-caption text-secondary">
                OCR · Chunking · Indexing continue in the background
              </p>
            </div>
          ) : previewFailed ? (
            <div className="flex h-full min-h-[28rem] flex-col items-center justify-center rounded-md border border-dashed border-border-default px-6 text-center">
              <p className="text-body-sm font-medium text-primary">
                Could not create a preview
              </p>
              <p className="mt-2 max-w-sm text-body-sm text-secondary">
                You can still download the original file to read this document.
              </p>
              <button
                type="button"
                className="mt-4 inline-flex h-9 items-center rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white"
                onClick={() =>
                  window.open(downloadUrl, "_blank", "noopener,noreferrer")
                }
              >
                Download original
              </button>
            </div>
          ) : viewerKind === "pdf" ? (
            <>
              <PDFViewer
                key={contentKey}
                ref={pdfRef}
                contentUrl={contentUrl}
                scale={scale}
                rotation={rotation}
                onDocumentReady={handlePdfReady}
                onLoadError={handlePdfError}
                onVisiblePageChange={setCurrentPage}
                className="min-h-0 flex-1 border-0 bg-elevated/40"
              />
              <ChunkNavigator
                chunkId={activeChunkId}
                highlightSnippet={focusSnippet}
                chunks={meta?.items ?? []}
                pdfRef={pdfRef}
                ready={metaReady && pdfReady}
                onMissing={handleMissing}
                onLocated={handleLocated}
                onHighlightFailed={onHighlightFailed}
              />
              <SnippetNavigator
                enabled={Boolean(focusCitationId || focusSnippet) && !focusChunkId}
                snippet={focusSnippet}
                pageHint={
                  focusLocator?.page_number ?? focusPage
                }
                chunks={meta?.items ?? []}
                pdfRef={pdfRef}
                ready={metaReady && pdfReady}
                onLocated={(chunk, matched) => {
                  if (chunk) {
                    setActiveChunkId(chunk.id);
                    handleLocated(chunk);
                  }
                  if (!matched) setCitationSnippetPreview(focusSnippet);
                }}
                onHighlightFailed={onHighlightFailed}
              />
            </>
          ) : (
            <div className="flex h-full min-h-[28rem] flex-col items-center justify-center rounded-md border border-dashed border-border-default px-6 text-center">
              <p className="text-body-sm font-medium text-primary">
                Preview not available for this format
              </p>
              <button
                type="button"
                className="mt-4 inline-flex h-9 items-center rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white"
                onClick={() =>
                  window.open(downloadUrl, "_blank", "noopener,noreferrer")
                }
              >
                Download original
              </button>
            </div>
          )}
        </div>

        {/* Right inspector */}
        <div className={cn(inspectorOpen ? "flex" : "hidden", "min-h-0 h-full flex-col overflow-hidden")}>
          <AIContextPanel
            workspaceId={workspaceId}
            documentId={documentId}
            document={document}
            currentVersion={currentVersion}
            chunk={activeChunk}
            match={
              activeMatch
                ? {
                    chunkId: activeMatch.chunkId,
                    score: activeMatch.score,
                    retrievalMethod: activeMatch.retrievalMethod,
                    textSnippet: activeMatch.textSnippet,
                    documentTitle: activeMatch.documentTitle,
                  }
                : activeChunk
                  ? {
                      chunkId: activeChunk.id,
                      textSnippet: activeChunk.content,
                    }
                  : citationSnippetPreview
                    ? {
                        chunkId: focusCitationId || "citation",
                        textSnippet: citationSnippetPreview,
                        documentTitle: meta?.document_title,
                      }
                    : null
            }
            matchIndex={matchIndex >= 0 ? matchIndex : 0}
            matchCount={matches.length}
            onPrev={() => goMatch(matchIndex - 1)}
            onNext={() => goMatch(matchIndex + 1)}
            onOpenVersionHistory={onOpenVersionHistory}
            onAskAi={askAi}
          />
        </div>
      </div>
    </div>
  );
}

function TocList({
  nodes,
  activeKey,
  onSelect,
  depth = 0,
}: {
  nodes: TocNode[];
  activeKey: string | null;
  onSelect: (n: TocNode) => void;
  depth?: number;
}) {
  return (
    <ul
      className={cn(
        "flex flex-col gap-0.5",
        depth > 0 && "ml-2 border-l border-border-default pl-2",
      )}
    >
      {nodes.map((node) => (
        <li key={node.key}>
          <button
            type="button"
            className={cn(
              "w-full rounded-md px-2 py-1.5 text-left text-caption transition-colors",
              activeKey === node.key
                ? "bg-accent-primary-soft font-semibold text-accent-primary"
                : "text-secondary hover:bg-elevated hover:text-primary",
            )}
            onClick={() => onSelect(node)}
          >
            {node.label}
          </button>
          {node.children?.length ? (
            <TocList
              nodes={node.children}
              activeKey={activeKey}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function flattenToc(nodes: TocNode[]): TocNode[] {
  const out: TocNode[] = [];
  for (const n of nodes) {
    out.push(n);
    if (n.children?.length) out.push(...flattenToc(n.children));
  }
  return out;
}

function cleanHeadingLabel(raw: string): string {
  return raw.replace(/^#{1,6}\s*/, "").trim();
}

function buildToc(
  headingTree: Array<Record<string, unknown>> | undefined,
  chunks: DocumentChunk[],
): TocNode[] {
  if (headingTree && headingTree.length > 0) {
    return mapHeadingTree(headingTree);
  }
  const seen = new Set<string>();
  const out: TocNode[] = [];
  for (const chunk of chunks) {
    const label = cleanHeadingLabel(
      chunk.heading_path || chunk.section_path || chunk.section || "",
    );
    if (!label || seen.has(label)) continue;
    seen.add(label);
    out.push({
      key: label,
      label,
      page: chunk.page_number,
    });
  }
  return out.slice(0, 80);
}

function mapHeadingTree(nodes: Array<Record<string, unknown>>): TocNode[] {
  return nodes.map((n, i) => {
    const title = cleanHeadingLabel(
      String(n.title || n.text || n.name || `Section ${i + 1}`),
    );
    const childrenRaw = n.children;
    const children = Array.isArray(childrenRaw)
      ? mapHeadingTree(childrenRaw as Array<Record<string, unknown>>)
      : undefined;
    const blockId =
      typeof n.block_id === "string"
        ? n.block_id
        : typeof n.id === "string"
          ? n.id
          : null;
    return {
      key: `${blockId ?? title}:${i}`,
      label: title,
      page: typeof n.page_number === "number" ? n.page_number : null,
      blockId,
      children,
    };
  });
}
