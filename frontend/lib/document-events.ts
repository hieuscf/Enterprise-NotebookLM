/**
 * =============================================================================
 * File: document-events.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Tiny cross-feature pub/sub so the Upload page can announce a newly
 *          ready document without a global cache/query layer (FR2).
 * Responsibilities:
 *   - notifyDocumentReady(documentId) — called when a pipeline run completes
 *   - subscribeDocumentReady(handler) — Document list page (Part 2) subscribes
 *     to append/refresh the affected row without a full reload
 * Dependencies:
 *   - None (plain EventTarget, browser-only)
 * Public Exports:
 *   - notifyDocumentReady, subscribeDocumentReady
 * Database/Table: N/A
 * Related Modules: features/documents/PipelineStatusTracker,
 *   features/documents/DocumentListView (Part 2, not built yet)
 * Important Notes: In-memory only (per browser tab) — not a replacement for
 *   reloading the list on navigation; purely a same-session UX nicety.
 * =============================================================================
 */

const DOCUMENT_READY_EVENT = "document-ready";

type DocumentReadyDetail = { documentId: string };

const target: EventTarget | null =
  typeof window !== "undefined" ? new EventTarget() : null;

export function notifyDocumentReady(documentId: string): void {
  target?.dispatchEvent(
    new CustomEvent<DocumentReadyDetail>(DOCUMENT_READY_EVENT, {
      detail: { documentId },
    }),
  );
}

/** Returns an unsubscribe function. No-op on the server. */
export function subscribeDocumentReady(
  handler: (documentId: string) => void,
): () => void {
  if (!target) return () => {};
  const listener = (event: Event) => {
    const detail = (event as CustomEvent<DocumentReadyDetail>).detail;
    handler(detail.documentId);
  };
  target.addEventListener(DOCUMENT_READY_EVENT, listener);
  return () => target.removeEventListener(DOCUMENT_READY_EVENT, listener);
}
