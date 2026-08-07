/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/chat)
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Route entry for AI Chat — no session selected yet (FR4 / UC4).
 * Responsibilities:
 *   - Pass workspace id to ChatPage with sessionId=null; ChatPage handles
 *     auto-redirect to the most recent session or the empty "New Chat" state.
 * Dependencies:
 *   - features/chat/ChatPage
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/chat/[sessionId]/page.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { ChatPage } from "@/features/chat/ChatPage";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ChatIndexPage({ params }: PageProps) {
  const { id } = await params;
  return <ChatPage workspaceId={id} sessionId={null} />;
}
