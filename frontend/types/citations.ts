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
 * Important Notes: location may be null for legacy chunks.
 * =============================================================================
 */

export type { ContentLocation } from "@/lib/content-location";

export type Citation = {
  id: string;
  message_id: string;
  retrieval_id: string;
  document_id: string;
  text_snippet: string;
  verified: boolean;
  order_index: number;
  location?: {
    page_number?: number | null;
    section_index?: number | null;
    section_title?: string | null;
  } | null;
};
