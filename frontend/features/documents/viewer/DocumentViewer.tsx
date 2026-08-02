/**
 * =============================================================================
 * File: DocumentViewer.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Original Document Viewer — PDF + ChunkNavigator + AI Context Panel.
 * Responsibilities:
 *   - Load original content URL + chunk metadata (AI Representation for panel)
 *   - Never render markdown body; PDF (or download fallback) only
 * Dependencies:
 *   - PDFViewer, ChunkNavigator, ViewerToolbar, AIContextPanel
 * Public Exports:
 *   - DocumentViewer
 * Important Notes: No Retrieval / Embedding / Search from this component.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AIContextPanel } from "@/features/documents/viewer/AIContextPanel";
import { ChunkNavigator } from "@/features/documents/viewer/ChunkNavigator";
import {
  PDFViewer,
  type PDFViewerHandle,
} from "@/features/documents/viewer/PDFViewer";
import { ViewerToolbar } from "@/features/documents/viewer/ViewerToolbar";
import {
  ApiClientError,
  documentContentUrl,
  listDocumentChunks,
} from "@/lib/api-client";
import { loadSearchMatches } from "@/lib/search-matches";
import { cn } from "@/lib/utils";
import type { DocumentChunk, DocumentChunkListResponse } from "@/types/documents";

type Props = {
  workspaceId: string;
  documentId: string;
  focusChunkId: string | null;
  focusPage: number | null;
  onMissingChunk?: () => void;
};

type TocNode = { key: string; label: string; page?: number | null; children?: TocNode[] };

export function DocumentViewer({
  workspaceId,
  documentId,
  focusChunkId,
  focusPage,
  onMissingChunk,
}: Props) {
  const router = useRouter();
  const pdfRef = useRef<PDFViewerHandle | null>(null);
  const [meta, setMeta] = useState<DocumentChunkListResponse | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [metaReady, setMetaReady] = useState(false);
  const [pdfReady, setPdfReady] = useState(false);
  const [scale, setScale] = useState(1.1);
  const [rotation, setRotation] = useState(0);
  const [activeChunkId, setActiveChunkId] = useState<string | null>(focusChunkId);
  const [activeSection, setActiveSection] = useState<string | null>(null);

  const contentUrl = useMemo(
    () => documentContentUrl(workspaceId, documentId),
    [workspaceId, documentId],
  );
  const downloadUrl = useMemo(
    () => documentContentUrl(workspaceId, documentId, { download: true }),
    [workspaceId, documentId],
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
    setPdfReady(false);
    setPdfError(null);
  }, [contentUrl]);

  // Poll chunk meta until preview is terminal (pending/processing → wait).
  useEffect(() => {
    let active = true;
    let timer: number | null = null;

    async function load(poll: boolean) {
      try {
        const data = await listDocumentChunks(workspaceId, documentId);
        if (!active) return;
        setMeta(data);
        setMetaReady(true);
        setMetaError(null);
        const status = data.preview_status ?? "pending";
        if (
          poll &&
          (status === "pending" || status === "processing")
        ) {
          timer = window.setTimeout(() => {
            void load(true);
          }, 2000);
        }
      } catch (err) {
        if (!active) return;
        setMetaError(
          err instanceof ApiClientError
            ? err.message
            : "Không tải được metadata chunk.",
        );
      }
    }

    setMetaReady(false);
    void load(true);
    return () => {
      active = false;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [workspaceId, documentId]);

  const activeChunk: DocumentChunk | null = useMemo(() => {
    if (!meta || !activeChunkId) return null;
    return meta.items.find((c) => c.id === activeChunkId) ?? null;
  }, [meta, activeChunkId]);

  const activeMatch = matches[matchIndex] ?? null;

  const toc = useMemo(
    () => buildToc(meta?.heading_tree, meta?.items ?? []),
    [meta],
  );

  const previewStatus = meta?.preview_status ?? "pending";
  const previewReady = previewStatus === "completed";
  const previewFailed = previewStatus === "failed";
  const previewBusy =
    previewStatus === "pending" || previewStatus === "processing";
  const viewerKind =
    previewReady && meta?.viewer_kind === "pdf" ? "pdf" : "original_download";

  const handleMissing = useCallback(
    (_id: string) => {
      onMissingChunk?.();
      if (focusPage && focusPage > 0) {
        pdfRef.current?.jumpToPage(focusPage);
      }
    },
    [onMissingChunk, focusPage],
  );

  const handleLocated = useCallback((chunk: DocumentChunk) => {
    const key = chunk.heading_path || chunk.section_path || chunk.section;
    if (key) setActiveSection(key);
  }, []);

  const handlePdfReady = useCallback((_pageCount: number) => {
    setPdfReady(true);
  }, []);

  const handlePdfError = useCallback((msg: string) => {
    setPdfError(msg);
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

  return (
    <div className="flex flex-col gap-3">
      <ViewerToolbar
        scale={scale}
        disabled={viewerKind !== "pdf" || !pdfReady}
        onZoomIn={() => setScale((s) => Math.min(2.5, s + 0.15))}
        onZoomOut={() => setScale((s) => Math.max(0.5, s - 0.15))}
        onFitWidth={() => setScale(1.25)}
        onFitPage={() => setScale(1)}
        onRotate={() => setRotation((r) => (r + 90) % 360)}
        onDownload={() => {
          window.open(downloadUrl, "_blank", "noopener,noreferrer");
        }}
        onOpenOriginal={() => {
          window.open(downloadUrl, "_blank", "noopener,noreferrer");
        }}
        onPrint={() => window.print()}
      />

      {metaError && (
        <p role="alert" className="text-body-sm text-danger">
          {metaError}
        </p>
      )}
      {previewReady && pdfError ? (
        <p role="alert" className="text-body-sm text-danger">
          {pdfError}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[200px_minmax(0,1fr)_240px]">
        <aside className="hidden max-h-[70vh] overflow-y-auto rounded-lg border border-border-default bg-elevated/40 p-3 lg:block">
          <p className="mb-2 text-caption font-semibold uppercase tracking-wide text-tertiary">
            Mục lục
          </p>
          {toc.length === 0 ? (
            <p className="text-caption text-secondary">Chưa có TOC từ parser.</p>
          ) : (
            <TocList
              nodes={toc}
              activeKey={activeSection}
              onSelect={(node) => {
                setActiveSection(node.key);
                if (node.page) pdfRef.current?.jumpToPage(node.page);
              }}
            />
          )}
        </aside>

        <div className="min-w-0">
          {previewBusy ? (
            <div
              className="flex flex-col items-center gap-3 rounded-lg border border-border-default px-6 py-14"
              aria-busy
              aria-live="polite"
            >
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
              <p className="text-body-sm font-medium text-primary">
                Đang tạo bản xem tài liệu…
              </p>
              <p className="text-caption text-secondary">
                {previewStatus === "processing"
                  ? "Preview Generator đang xử lý"
                  : "Chờ pipeline bắt đầu tạo preview"}
              </p>
              <div className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-elevated">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-accent-primary/70" />
              </div>
            </div>
          ) : previewFailed ? (
            <div className="rounded-lg border border-dashed border-border-default px-6 py-10 text-center">
              <p className="text-body-sm font-medium text-primary">
                Không thể tạo bản xem.
              </p>
              <p className="mt-2 text-body-sm text-secondary">
                Bạn vẫn có thể tải file gốc để đọc tài liệu.
              </p>
              <button
                type="button"
                className="mt-4 inline-flex h-9 items-center rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white"
                onClick={() => window.open(downloadUrl, "_blank", "noopener,noreferrer")}
              >
                Download Original
              </button>
            </div>
          ) : viewerKind === "pdf" ? (
            <>
              <PDFViewer
                ref={pdfRef}
                contentUrl={contentUrl}
                scale={scale}
                rotation={rotation}
                onDocumentReady={handlePdfReady}
                onLoadError={handlePdfError}
              />
              <ChunkNavigator
                chunkId={activeChunkId}
                chunks={meta?.items ?? []}
                pdfRef={pdfRef}
                ready={metaReady && pdfReady}
                onMissing={handleMissing}
                onLocated={handleLocated}
              />
            </>
          ) : (
            <div className="rounded-lg border border-dashed border-border-default px-6 py-10 text-center">
              <p className="text-body-sm font-medium text-primary">
                Bản xem chưa sẵn sàng
              </p>
              <button
                type="button"
                className="mt-4 inline-flex h-9 items-center rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white"
                onClick={() => window.open(downloadUrl, "_blank", "noopener,noreferrer")}
              >
                Download Original
              </button>
            </div>
          )}
        </div>

        <AIContextPanel
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
                : null
          }
          matchIndex={matchIndex >= 0 ? matchIndex : 0}
          matchCount={matches.length}
          onPrev={() => goMatch(matchIndex - 1)}
          onNext={() => goMatch(matchIndex + 1)}
        />
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
    <ul className={cn("flex flex-col gap-0.5", depth > 0 && "ml-2 border-l border-border-default pl-2")}>
      {nodes.map((node) => (
        <li key={node.key}>
          <button
            type="button"
            className={cn(
              "w-full rounded-md px-2 py-1 text-left text-caption transition-colors",
              activeKey === node.key
                ? "bg-accent-primary-soft font-semibold text-accent-primary"
                : "text-secondary hover:bg-surface hover:text-primary",
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
    const label = chunk.heading_path || chunk.section_path || chunk.section;
    if (!label || seen.has(label)) continue;
    seen.add(label);
    out.push({
      key: label,
      label,
      page: chunk.page_number,
    });
  }
  return out.slice(0, 50);
}

function mapHeadingTree(nodes: Array<Record<string, unknown>>): TocNode[] {
  return nodes.map((n, i) => {
    const title = String(n.title || n.text || n.name || `Mục ${i + 1}`);
    const childrenRaw = n.children;
    const children = Array.isArray(childrenRaw)
      ? mapHeadingTree(childrenRaw as Array<Record<string, unknown>>)
      : undefined;
    return {
      key: `${title}:${i}`,
      label: title,
      page: typeof n.page_number === "number" ? n.page_number : null,
      children,
    };
  });
}
