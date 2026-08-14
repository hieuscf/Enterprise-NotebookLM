/**
 * =============================================================================
 * File: citations.ts
 * Module/Service: Chat / Citation
 * Layer: UI
 * Purpose: TypeScript types for Citation + ContentLocation (OpenAPI).
 * Responsibilities:
 *   - Mirror backend CitationResponse / ContentLocation schemas
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml
 * Public Exports:
 *   - ContentLocation, Citation
 * Database/Table: N/A
 * Related Modules: lib/content-location, features/citation
 * Important Notes: chunk_id + location enable deterministic Document Viewer deep-links.
 * =============================================================================
 */

export type { ContentLocation } from "@/lib/content-location";

export type Citation = {
  id: string;
  message_id: string;
  retrieval_id: string;
  document_id: string;
  /** Source chunk via retrievals — preferred deep-link key. */
  chunk_id?: string | null;
  /** Exact version used when the answer was generated. */
  document_version_id?: string | null;
  text_snippet: string;
  verified: boolean;
  order_index: number;
  location?: {
    page_number?: number | null;
    section_index?: number | null;
    section_title?: string | null;
  } | null;
  locator?: import("@/types/canonical").CitationLocator | null;
};
