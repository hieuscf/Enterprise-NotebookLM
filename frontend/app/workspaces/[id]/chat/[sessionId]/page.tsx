/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/chat/[sessionId])
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Route entry for one AI Chat session — bookmarkable/shareable URL
 *          per session (FR4/FR10 §Switch Session), mirroring the existing
 *          documents/[documentId] page pattern.
 * Responsibilities:
 *   - Pass workspace id + session id to ChatPage
 * Dependencies:
 *   - features/chat/ChatPage
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/chat/page.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { ChatPage } from "@/features/chat/ChatPage";

type PageProps = {
  params: Promise<{ id: string; sessionId: string }>;
};

export default async function ChatSessionPage({ params }: PageProps) {
  const { id, sessionId } = await params;
  return <ChatPage workspaceId={id} sessionId={sessionId} />;
}
