/**
 * =============================================================================
 * File: search-matches.ts
 * Module/Service: Search → Document Viewer
 * Layer: UI
 * Purpose: Persist Search match list for Prev/Next in AI Context Panel.
 * Public Exports:
 *   - saveSearchMatches, loadSearchMatches, SearchMatchEntry
 * =============================================================================
 */

import type { RetrievalMethod } from "@/types/search";

const PREFIX = "enlm:search-matches:";

export type SearchMatchEntry = {
  chunkId: string;
  documentId: string;
  pageNumber?: number | null;
  score?: number | null;
  retrievalMethod?: RetrievalMethod | null;
  textSnippet?: string | null;
  documentTitle?: string | null;
};

export function saveSearchMatches(
  workspaceId: string,
  documentId: string,
  matches: SearchMatchEntry[],
  activeChunkId: string,
): void {
  try {
    sessionStorage.setItem(
      `${PREFIX}${workspaceId}:${documentId}`,
      JSON.stringify({ matches, activeChunkId, savedAt: Date.now() }),
    );
  } catch {
    /* ignore */
  }
}

export function loadSearchMatches(
  workspaceId: string,
  documentId: string,
): { matches: SearchMatchEntry[]; activeChunkId: string | null } | null {
  try {
    const raw = sessionStorage.getItem(`${PREFIX}${workspaceId}:${documentId}`);
    if (!raw) return null;
    return JSON.parse(raw) as {
      matches: SearchMatchEntry[];
      activeChunkId: string | null;
    };
  } catch {
    return null;
  }
}
