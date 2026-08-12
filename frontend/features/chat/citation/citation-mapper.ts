/**
 * =============================================================================
 * File: citation-mapper.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Map API Citation → CitationViewModel; group by document.
 * Responsibilities:
 *   - Single adapter for document title / page enrichment (no mapping in JSX)
 *   - Group citations for Source Panel
 * Dependencies:
 *   - types/citations, citation-types, chat-format, content-location
 * Public Exports:
 *   - mapCitation, mapCitations, groupCitationsByDocument, documentIdsFromCitations
 * Database/Table: N/A
 * Related Modules: ChatCitationContext, SourcePanel, AnswerContent
 * Important Notes: Never invent citations; missing title → fallback label.
 * =============================================================================
 */

import { citationDisplayIndex } from "@/features/chat/chat-format";
import type {
  CitationViewModel,
  SourceDocumentGroup,
} from "@/features/chat/citation/citation-types";
import type { Citation } from "@/types/citations";
import type { Document, FileType } from "@/types/documents";

export type DocumentMetaLookup = {
  title: string;
  fileType?: FileType | string;
  missing?: boolean;
};

export function mapCitation(
  citation: Citation,
  docsById: Map<string, DocumentMetaLookup>,
): CitationViewModel {
  const docId = citation.document_id || "";
  const meta = docId ? docsById.get(docId) : undefined;
  const page = citation.location?.page_number ?? null;
  const sectionIndex = citation.location?.section_index ?? null;

  return {
    id: citation.id,
    messageId: citation.message_id,
    retrievalId: citation.retrieval_id,
    documentId: docId,
    documentTitle: meta?.title?.trim() || (docId ? "Tài liệu" : "Tài liệu không còn khả dụng"),
    fileType: meta?.fileType,
    page,
    sectionIndex,
    sectionTitle: citation.location?.section_title ?? null,
    location: citation.location ?? null,
    textSnippet: citation.text_snippet || "",
    verified: Boolean(citation.verified),
    orderIndex: citation.order_index,
    displayIndex: citationDisplayIndex(citation),
    documentMissing: !docId || Boolean(meta?.missing),
  };
}

export function mapCitations(
  citations: Citation[],
  docsById: Map<string, DocumentMetaLookup>,
): CitationViewModel[] {
  return [...citations]
    .sort((a, b) => a.order_index - b.order_index)
    .map((c) => mapCitation(c, docsById));
}

export function buildDocumentMetaMap(documents: Document[]): Map<string, DocumentMetaLookup> {
  const map = new Map<string, DocumentMetaLookup>();
  for (const doc of documents) {
    map.set(doc.id, { title: doc.title, fileType: doc.file_type });
  }
  return map;
}

export function documentIdsFromCitations(citations: Citation[]): string[] {
  const ids = new Set<string>();
  for (const c of citations) {
    if (c.document_id) ids.add(c.document_id);
  }
  return Array.from(ids);
}

/** Group citations by document; preserve first-seen document order by min orderIndex. */
export function groupCitationsByDocument(
  citations: CitationViewModel[],
): SourceDocumentGroup[] {
  const byDoc = new Map<string, CitationViewModel[]>();
  const order: string[] = [];

  for (const c of citations) {
    const key = c.documentId || `missing:${c.id}`;
    if (!byDoc.has(key)) {
      byDoc.set(key, []);
      order.push(key);
    }
    byDoc.get(key)!.push(c);
  }

  return order.map((key) => {
    const items = byDoc.get(key)!;
    const first = items[0];
    const pages = Array.from(
      new Set(
        items
          .map((c) => c.page)
          .filter((p): p is number => typeof p === "number" && p > 0),
      ),
    ).sort((a, b) => a - b);

    return {
      documentId: first.documentId,
      documentTitle: first.documentTitle,
      fileType: first.fileType,
      documentMissing: first.documentMissing,
      citations: items,
      pages,
    };
  });
}

export function findCitationByDisplayIndex(
  citations: CitationViewModel[],
  displayIndex: number,
): CitationViewModel | undefined {
  return citations.find((c) => c.displayIndex === displayIndex);
}
