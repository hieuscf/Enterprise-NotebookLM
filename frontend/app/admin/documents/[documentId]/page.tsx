/**
 * =============================================================================
 * File: page.tsx (/admin/documents/[documentId])
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Route entry for enterprise document detail (Manage).
 * Responsibilities:
 *   - Pass documentId from route params into AdminDocumentDetailView
 * Dependencies:
 *   - features/admin/AdminDocumentDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/admin/documents/page.tsx
 * Important Notes: Platform Manage only — enforced in layout + backend API.
 * =============================================================================
 */

import { AdminDocumentDetailView } from "@/features/admin/AdminDocumentDetailView";

type Props = {
  params: Promise<{ documentId: string }>;
};

export default async function AdminDocumentDetailPage({ params }: Props) {
  const { documentId } = await params;
  return <AdminDocumentDetailView documentId={documentId} />;
}
