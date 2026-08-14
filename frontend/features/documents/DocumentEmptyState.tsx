/**
 * =============================================================================
 * File: DocumentEmptyState.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Elegant empty state for the Workspace document library.
 * Responsibilities:
 *   - Explain knowledge-base value; CTA to upload when permitted
 * Dependencies:
 *   - next/link, lucide-react
 * Public Exports:
 *   - DocumentEmptyState
 * Database/Table: N/A
 * Related Modules: features/documents/DocumentList
 * Important Notes: No giant illustration — quiet editorial empty state.
 * =============================================================================
 */

import { Plus } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  canUpload?: boolean;
};

export function DocumentEmptyState({ workspaceId, canUpload = true }: Props) {
  return (
    <section className="rounded-md border border-dashed border-border-strong bg-surface px-6 py-16 text-center">
      <p className="text-caption font-medium tracking-wide text-accent-primary uppercase">
        Documents
      </p>
      <h2 className="mt-2 text-h2 text-primary">
        Build your Workspace knowledge base
      </h2>
      <p className="mx-auto mt-2 max-w-md text-body-sm text-secondary">
        Upload documents to make them searchable, available to AI Chat, and
        connected to the Knowledge Graph.
      </p>
      <p className="mt-3 text-caption text-tertiary">
        Supported · PDF · DOCX · XLSX · PPTX · TXT
      </p>
      {canUpload ? (
        <Link
          href={`/workspaces/${workspaceId}/upload`}
          className={cn(
            "mt-6 inline-flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
            "text-body-sm font-medium text-white hover:bg-accent-primary-hover",
          )}
        >
          <Plus className="h-4 w-4" aria-hidden />
          Upload your first document
        </Link>
      ) : (
        <p className="mt-6 text-body-sm text-tertiary">
          Contact a Workspace editor or admin to upload documents.
        </p>
      )}
    </section>
  );
}
