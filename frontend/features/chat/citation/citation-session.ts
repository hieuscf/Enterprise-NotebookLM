/**
 * =============================================================================
 * File: citation-session.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Persist citation open-context across navigation to Document Viewer.
 * Responsibilities:
 *   - sessionStorage payload for highlight (snippet, page, citation id)
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - saveCitationFocus, loadCitationFocus, clearCitationFocus, CitationFocusPayload
 * Database/Table: N/A
 * Related Modules: chat-format, DocumentDetailView, SnippetNavigator
 * Important Notes: Avoid putting long snippets in the URL.
 * =============================================================================
 */

const PREFIX = "enlm:citation-focus:";

export type CitationFocusPayload = {
  citationId: string;
  documentId: string;
  textSnippet: string;
  page?: number | null;
  chunkId?: string | null;
  versionId?: string | null;
  verified?: boolean;
  documentTitle?: string;
  locator?: import("@/types/canonical").CitationLocator | null;
  savedAt: number;
};

export function saveCitationFocus(
  workspaceId: string,
  payload: Omit<CitationFocusPayload, "savedAt">,
): void {
  try {
    const full: CitationFocusPayload = { ...payload, savedAt: Date.now() };
    sessionStorage.setItem(`${PREFIX}${workspaceId}:${payload.citationId}`, JSON.stringify(full));
    sessionStorage.setItem(`${PREFIX}${workspaceId}:latest`, payload.citationId);
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadCitationFocus(
  workspaceId: string,
  citationId: string,
): CitationFocusPayload | null {
  try {
    const raw = sessionStorage.getItem(`${PREFIX}${workspaceId}:${citationId}`);
    if (!raw) return null;
    return JSON.parse(raw) as CitationFocusPayload;
  } catch {
    return null;
  }
}

export function clearCitationFocus(workspaceId: string, citationId: string): void {
  try {
    sessionStorage.removeItem(`${PREFIX}${workspaceId}:${citationId}`);
  } catch {
    /* ignore */
  }
}
