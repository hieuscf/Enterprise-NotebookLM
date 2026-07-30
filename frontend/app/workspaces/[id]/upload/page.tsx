/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/upload)
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Route entry for the document upload page (FR2 / UC2).
 * Responsibilities:
 *   - Pass route param to DocumentUploadView
 * Dependencies:
 *   - features/documents/DocumentUploadView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx (nav entry), app/workspaces/[id]/page.tsx
 * Important Notes: Editor/admin only for the actual mutation; backend enforces RBAC.
 * =============================================================================
 */

import { DocumentUploadView } from "@/features/documents/DocumentUploadView";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function DocumentUploadPage({ params }: PageProps) {
  const { id } = await params;
  return <DocumentUploadView workspaceId={id} />;
}
