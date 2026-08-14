/**
 * =============================================================================
 * File: AIContextPanel.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Right inspector — AI Context + Document metadata tabs.
 * Responsibilities:
 *   - Meaningful empty / selected states; matched chunks; source citation
 *   - Document inspector fields (no internal IDs/checksums)
 * Dependencies:
 *   - lucide-react, content-location helpers
 * Public Exports:
 *   - AIContextPanel, SearchMatchContext
 * Database/Table: N/A
 * Related Modules: DocumentViewer
 * Important Notes: Data from AI Representation / version meta only.
 * =============================================================================
 */

"use client";

import {
  ChevronDown,
  ChevronUp,
  Copy,
  MessageSquare,
  Network,
  ScrollText,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { formatContentLocationLabel } from "@/lib/content-location";
import { formatRetrievalMethodLabel } from "@/lib/search-highlight";
import { formatBytes } from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { Document, DocumentChunk, DocumentVersion } from "@/types/documents";
import type { RetrievalMethod } from "@/types/search";

export type SearchMatchContext = {
  chunkId: string;
  score?: number | null;
  retrievalMethod?: RetrievalMethod | null;
  textSnippet?: string | null;
  documentTitle?: string | null;
};

type Props = {
  workspaceId: string;
  documentId: string;
  document: Document | null;
  currentVersion: DocumentVersion | null;
  chunk: DocumentChunk | null;
  match: SearchMatchContext | null;
  matchIndex: number;
  matchCount: number;
  onPrev: () => void;
  onNext: () => void;
  onOpenVersionHistory?: () => void;
  onAskAi?: (text: string) => void;
};

type TabId = "ai" | "document";

export function AIContextPanel({
  workspaceId,
  documentId,
  document,
  currentVersion,
  chunk,
  match,
  matchIndex,
  matchCount,
  onPrev,
  onNext,
  onOpenVersionHistory,
  onAskAi,
}: Props) {
  const [tab, setTab] = useState<TabId>("ai");

  const loc = chunk
    ? formatContentLocationLabel({
        page_number: chunk.page_number,
        section_index: chunk.section_index,
        section_title: chunk.section,
      })
    : null;

  const snippet = match?.textSnippet || chunk?.content || null;
  const hasContext = Boolean(snippet || chunk || matchCount > 0);

  return (
    <aside className="flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-border-default bg-surface">
      <div
        role="tablist"
        aria-label="Inspector"
        className="flex shrink-0 border-b border-border-default"
      >
        {(
          [
            { id: "ai" as const, label: "AI Context" },
            { id: "document" as const, label: "Document" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "flex-1 px-3 py-2.5 text-caption font-semibold tracking-wide uppercase transition-colors",
              tab === t.id
                ? "border-b-2 border-accent-primary text-accent-primary"
                : "text-tertiary hover:text-secondary",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {tab === "ai" ? (
          <div className="flex flex-col gap-4">
            {!hasContext ? (
              <div className="rounded-md border border-dashed border-border-default px-3 py-5">
                <p className="text-body-sm font-medium text-primary">AI Context</p>
                <p className="mt-1.5 text-caption leading-relaxed text-secondary">
                  Select a section from the outline or open a search match to
                  inspect its AI context.
                </p>
                <ul className="mt-3 space-y-1 text-caption text-tertiary">
                  <li>• Matched chunks</li>
                  <li>• Source references</li>
                  <li>• Citation location</li>
                </ul>
              </div>
            ) : (
              <>
                {matchCount > 0 ? (
                  <div className="flex items-center gap-2 rounded-md border border-border-default bg-elevated/40 px-2 py-1.5">
                    <button
                      type="button"
                      className="rounded p-1 text-secondary hover:bg-elevated disabled:opacity-40"
                      disabled={matchIndex <= 0}
                      onClick={onPrev}
                      aria-label="Previous match"
                    >
                      <ChevronUp className="h-4 w-4" aria-hidden />
                    </button>
                    <span className="flex-1 text-center text-caption tabular-nums text-secondary">
                      {matchIndex + 1} / {matchCount}
                    </span>
                    <button
                      type="button"
                      className="rounded p-1 text-secondary hover:bg-elevated disabled:opacity-40"
                      disabled={matchIndex >= matchCount - 1}
                      onClick={onNext}
                      aria-label="Next match"
                    >
                      <ChevronDown className="h-4 w-4" aria-hidden />
                    </button>
                  </div>
                ) : null}

                {snippet ? (
                  <section>
                    <p className="text-caption font-medium text-tertiary">
                      Selected text
                    </p>
                    <blockquote className="mt-1.5 whitespace-pre-wrap rounded-md border border-border-default bg-elevated/30 px-3 py-2.5 text-body-sm leading-relaxed text-secondary">
                      “{snippet.length > 420 ? `${snippet.slice(0, 420)}…` : snippet}”
                    </blockquote>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        onClick={() => onAskAi?.(snippet)}
                        className="inline-flex h-7 items-center gap-1 rounded-md border border-border-default px-2 text-caption font-medium text-secondary hover:bg-elevated"
                      >
                        <MessageSquare className="h-3 w-3" aria-hidden />
                        Ask AI
                      </button>
                      <Link
                        href={`/workspaces/${workspaceId}/summaries?documentId=${documentId}`}
                        className="inline-flex h-7 items-center gap-1 rounded-md border border-border-default px-2 text-caption font-medium text-secondary hover:bg-elevated"
                      >
                        <ScrollText className="h-3 w-3" aria-hidden />
                        Summarize
                      </Link>
                      <button
                        type="button"
                        onClick={() => void navigator.clipboard.writeText(snippet)}
                        className="inline-flex h-7 items-center gap-1 rounded-md border border-border-default px-2 text-caption font-medium text-secondary hover:bg-elevated"
                      >
                        <Copy className="h-3 w-3" aria-hidden />
                        Copy
                      </button>
                    </div>
                  </section>
                ) : null}

                <section className="border-t border-border-default pt-3">
                  <p className="text-caption font-medium text-tertiary">
                    Matched chunk
                  </p>
                  {match?.score != null ? (
                    <p className="mt-1 text-body-sm font-medium text-primary">
                      {Math.round(match.score * 100)}% relevance
                    </p>
                  ) : null}
                  {match?.retrievalMethod ? (
                    <p className="mt-0.5 text-caption text-secondary">
                      {formatRetrievalMethodLabel(match.retrievalMethod)}
                    </p>
                  ) : null}
                  {loc ? (
                    <p className="mt-0.5 text-caption text-secondary">{loc}</p>
                  ) : null}
                  {(chunk?.section_path ||
                    chunk?.heading_path ||
                    chunk?.section) && (
                    <p className="mt-1 text-caption text-tertiary">
                      {cleanHeading(
                        chunk.section_path ||
                          chunk.heading_path ||
                          chunk.section ||
                          "",
                      )}
                    </p>
                  )}
                </section>

                <section className="border-t border-border-default pt-3">
                  <p className="text-caption font-medium text-tertiary">Source</p>
                  <p className="mt-1 text-body-sm font-medium text-primary">
                    {match?.documentTitle || document?.title || "Document"}
                  </p>
                  {chunk?.page_number ? (
                    <p className="text-caption text-secondary">
                      Page {chunk.page_number}
                    </p>
                  ) : null}
                  <p className="mt-1.5 inline-flex items-center gap-1.5 text-caption font-medium text-success">
                    <span
                      aria-hidden
                      className="h-1.5 w-1.5 rounded-full bg-success"
                    />
                    Verified source
                  </p>
                </section>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <p className="text-body-sm font-medium text-primary">
                {document?.title ?? "Document"}
              </p>
            </div>
            <dl className="space-y-3 text-caption">
              <MetaRow label="Type" value={document?.file_type?.toUpperCase()} />
              <MetaRow
                label="Pages"
                value={
                  currentVersion?.page_count != null
                    ? String(currentVersion.page_count)
                    : "—"
                }
              />
              <MetaRow
                label="Size"
                value={
                  currentVersion?.file_size_bytes != null
                    ? formatBytes(currentVersion.file_size_bytes)
                    : "—"
                }
              />
              <MetaRow
                label="Uploaded"
                value={
                  currentVersion?.created_at
                    ? formatShortDate(currentVersion.created_at)
                    : document?.created_at
                      ? formatShortDate(document.created_at)
                      : "—"
                }
              />
              <MetaRow
                label="Version"
                value={
                  currentVersion
                    ? `v${currentVersion.version_number}`
                    : "—"
                }
              />
              <MetaRow
                label="Status"
                value={
                  currentVersion?.status === "ready"
                    ? "Ready"
                    : currentVersion?.status === "processing"
                      ? "Processing"
                      : currentVersion?.status === "failed"
                        ? "Failed"
                        : "—"
                }
              />
            </dl>

            {onOpenVersionHistory ? (
              <button
                type="button"
                onClick={onOpenVersionHistory}
                className="h-9 rounded-md border border-border-default text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary"
              >
                Version history
              </button>
            ) : null}

            <section className="border-t border-border-default pt-3">
              <p className="text-caption font-medium text-tertiary">Knowledge</p>
              <p className="mt-1 text-caption leading-relaxed text-secondary">
                Explore entities and relationships extracted from this document
                in the Knowledge Graph.
              </p>
              <Link
                href={`/workspaces/${workspaceId}/graph`}
                className="mt-2 inline-flex items-center gap-1.5 text-caption font-medium text-accent-primary hover:underline"
              >
                <Network className="h-3.5 w-3.5" aria-hidden />
                Explore graph →
              </Link>
            </section>
          </div>
        )}
      </div>
    </aside>
  );
}

function MetaRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-tertiary">{label}</dt>
      <dd className="text-right font-medium text-primary">{value || "—"}</dd>
    </div>
  );
}

function formatShortDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function cleanHeading(raw: string): string {
  return raw.replace(/^#{1,6}\s*/, "").trim();
}
