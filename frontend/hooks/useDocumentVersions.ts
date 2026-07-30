/**
 * =============================================================================
 * File: useDocumentVersions.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Client hook to load one document's version history (FR2 Part 2).
 * Responsibilities:
 *   - Fetch GET .../documents/{documentId}/versions; expose loading/error/reload
 *   - Defensive sort newest-first (API already orders by version_number desc)
 * Dependencies:
 *   - lib/api-client.listDocumentVersions
 * Public Exports:
 *   - useDocumentVersions
 * Database/Table: document_versions
 * Related Modules: features/documents/DocumentVersionHistory
 * Important Notes: N/A
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError, listDocumentVersions } from "@/lib/api-client";
import type { DocumentVersion } from "@/types/documents";

export function useDocumentVersions(workspaceId: string, documentId: string) {
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocumentVersions(workspaceId, documentId);
      setVersions([...data].sort((a, b) => b.version_number - a.version_number));
    } catch (err) {
      setVersions([]);
      setError(
        err instanceof ApiClientError ? err.message : "Không tải được lịch sử version.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId, documentId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { versions, loading, error, reload };
}
