/**
 * =============================================================================
 * File: AIContextPanel.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Right panel — AI Representation context for the focused search chunk.
 * Responsibilities:
 *   - Show matched snippet, score, section, retrieval method, page
 *   - Prev / Next match navigation (Search match list)
 * Public Exports:
 *   - AIContextPanel
 * Important Notes: Data from AI Representation only; PDF remains original.
 * =============================================================================
 */

"use client";

import { ChevronDown, ChevronUp } from "lucide-react";

import { formatContentLocationLabel } from "@/lib/content-location";
import { formatRetrievalMethodLabel } from "@/lib/search-highlight";
import type { DocumentChunk } from "@/types/documents";
import type { RetrievalMethod } from "@/types/search";

export type SearchMatchContext = {
  chunkId: string;
  score?: number | null;
  retrievalMethod?: RetrievalMethod | null;
  textSnippet?: string | null;
  documentTitle?: string | null;
};

type Props = {
  chunk: DocumentChunk | null;
  match: SearchMatchContext | null;
  matchIndex: number;
  matchCount: number;
  onPrev: () => void;
  onNext: () => void;
};

export function AIContextPanel({
  chunk,
  match,
  matchIndex,
  matchCount,
  onPrev,
  onNext,
}: Props) {
  const loc = chunk
    ? formatContentLocationLabel({
        page_number: chunk.page_number,
        section_index: chunk.section_index,
        section_title: chunk.section,
      })
    : null;

  return (
    <aside className="flex max-h-[70vh] flex-col gap-3 overflow-y-auto rounded-lg border border-border-default bg-elevated/40 p-3">
      <div>
        <p className="text-caption font-semibold uppercase tracking-wide text-tertiary">
          AI Context
        </p>
        <p className="mt-1 text-body-sm font-medium text-primary">Matched Chunk</p>
      </div>

      {matchCount > 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-border-default bg-surface px-2 py-1.5">
          <button
            type="button"
            className="rounded p-1 text-secondary hover:bg-elevated hover:text-primary disabled:opacity-40"
            disabled={matchIndex <= 0}
            onClick={onPrev}
            aria-label="Previous match"
          >
            <ChevronUp className="h-4 w-4" />
          </button>
          <span className="flex-1 text-center text-caption tabular-nums text-secondary">
            {matchIndex + 1} / {matchCount}
          </span>
          <button
            type="button"
            className="rounded p-1 text-secondary hover:bg-elevated hover:text-primary disabled:opacity-40"
            disabled={matchIndex >= matchCount - 1}
            onClick={onNext}
            aria-label="Next match"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      <dl className="space-y-2 text-caption">
        {match?.score != null ? (
          <div>
            <dt className="text-tertiary">Score</dt>
            <dd className="font-medium tabular-nums text-primary">{match.score.toFixed(3)}</dd>
          </div>
        ) : null}
        {match?.retrievalMethod ? (
          <div>
            <dt className="text-tertiary">Retrieval</dt>
            <dd className="font-medium text-primary">
              {formatRetrievalMethodLabel(match.retrievalMethod)}
            </dd>
          </div>
        ) : null}
        {loc ? (
          <div>
            <dt className="text-tertiary">Location</dt>
            <dd className="font-medium text-primary">{loc}</dd>
          </div>
        ) : null}
        {(chunk?.section_path || chunk?.heading_path || chunk?.section) && (
          <div>
            <dt className="text-tertiary">Section</dt>
            <dd className="font-medium text-primary">
              {chunk.section_path || chunk.heading_path || chunk.section}
            </dd>
          </div>
        )}
      </dl>

      <div>
        <p className="mb-1 text-caption text-tertiary">Snippet</p>
        <p className="whitespace-pre-wrap rounded-md border border-border-default bg-surface px-2.5 py-2 text-body-sm leading-relaxed text-secondary">
          {match?.textSnippet || chunk?.content || "—"}
        </p>
      </div>
    </aside>
  );
}
