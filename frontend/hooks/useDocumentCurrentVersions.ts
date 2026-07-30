/**
 * =============================================================================
 * File: useDocumentCurrentVersions.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Fill in each document row's current-version status badge without
 *          blocking the table render (FR2 Part 2 — mitigates an N+1 gap in
 *          the current API contract: GET /documents does not embed version
 *          status, only current_version_id).
 * Responsibilities:
 *   - For each Document with a current_version_id, fetch
 *     GET .../versions/{versionId} with bounded concurrency (4 in flight)
 *   - Skip refetching a document whose resolved version id hasn't changed
 *   - Expose per-document {version, loading, error} for the badge to render
 * Dependencies:
 *   - lib/api-client.getDocumentVersion
 * Public Exports:
 *   - useDocumentCurrentVersions, type CurrentVersionState
 * Database/Table: document_versions
 * Related Modules: features/documents/DocumentList
 * Important Notes: TODO(FR2 backend): the cleanest long-term fix is for
 *   DocumentListResponse.items[] to embed current_version_status /
 *   current_version_number directly — flagged to the team, not done here
 *   since it requires a backend + OpenAPI contract change.
 * =============================================================================
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { getDocumentVersion } from "@/lib/api-client";
import type { Document, DocumentVersion } from "@/types/documents";

const MAX_CONCURRENT_VERSION_FETCHES = 4;

export type CurrentVersionState = {
  version: DocumentVersion | null;
  loading: boolean;
  error: boolean;
};

export function useDocumentCurrentVersions(
  workspaceId: string,
  documents: Document[],
): Record<string, CurrentVersionState> {
  const [map, setMap] = useState<Record<string, CurrentVersionState>>({});
  const mapRef = useRef<Record<string, CurrentVersionState>>({});

  useEffect(() => {
    let cancelled = false;

    const targets = documents.filter((doc) => {
      if (!doc.current_version_id) return false;
      const existing = mapRef.current[doc.id];
      return !existing || existing.version?.id !== doc.current_version_id;
    });
    if (targets.length === 0) return;

    function patch(documentId: string, state: CurrentVersionState) {
      mapRef.current = { ...mapRef.current, [documentId]: state };
      setMap(mapRef.current);
    }

    for (const doc of targets) patch(doc.id, { version: null, loading: true, error: false });

    let cursor = 0;
    async function worker() {
      while (!cancelled) {
        const i = cursor;
        cursor += 1;
        if (i >= targets.length) return;
        const doc = targets[i];
        try {
          const version = await getDocumentVersion(
            workspaceId,
            doc.id,
            doc.current_version_id as string,
          );
          if (!cancelled) patch(doc.id, { version, loading: false, error: false });
        } catch {
          if (!cancelled) patch(doc.id, { version: null, loading: false, error: true });
        }
      }
    }

    const workerCount = Math.min(MAX_CONCURRENT_VERSION_FETCHES, targets.length);
    void Promise.all(Array.from({ length: workerCount }, () => worker()));

    return () => {
      cancelled = true;
    };
  }, [workspaceId, documents]);

  return map;
}
