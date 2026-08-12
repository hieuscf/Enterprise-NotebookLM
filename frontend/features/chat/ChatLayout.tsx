/**
 * =============================================================================
 * File: ChatLayout.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: 3-pane AI Research Workspace — sessions | conversation | sources.
 * Responsibilities:
 *   - Compose sidebar, conversation, source panel, sticky composer
 *   - Own collapse / mobile drawer flags via ChatCitationProvider
 * Dependencies:
 *   - SessionSidebar, ConversationPanel, MessageInput, SourcePanel
 * Public Exports:
 *   - ChatLayout
 * Database/Table: N/A
 * Related Modules: features/chat/ChatPage
 * Important Notes: Presentational — data/callbacks come from ChatPage.
 * =============================================================================
 */

"use client";

import { PanelLeft, PanelRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  ChatCitationProvider,
  useChatCitationUi,
} from "@/features/chat/ChatCitationContext";
import { ConversationPanel } from "@/features/chat/ConversationPanel";
import { EmptyChatState } from "@/features/chat/EmptyChatState";
import { MessageInput } from "@/features/chat/MessageInput";
import { SessionSidebar } from "@/features/chat/SessionSidebar";
import {
  buildDocumentMetaMap,
  documentIdsFromCitations,
  mapCitations,
} from "@/features/chat/citation/citation-mapper";
import type { ContextDocument } from "@/features/chat/DocumentContextBar";
import { sessionTitleLabel } from "@/features/chat/chat-format";
import { SourcePanel } from "@/features/chat/source/SourcePanel";
import { getDocument, listDocuments } from "@/lib/api-client";
import type { ChatMessage, ChatSession } from "@/types/chat";
import type { Document } from "@/types/documents";

type Props = {
  workspaceId: string;
  sessions: ChatSession[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  creatingSession: boolean;
  activeSessionId: string | null;
  activeSession: ChatSession | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;

  messages: ChatMessage[];
  messagesLoading: boolean;
  messagesError: string | null;

  isStreaming: boolean;
  streamError: string | null;
  stoppedMessageId: string | null;
  onSend: (content: string) => void;
  onStop: () => void;
  onRegenerate: () => void;
};

export function ChatLayout(props: Props) {
  return (
    <ChatCitationProvider>
      <ChatLayoutInner {...props} />
    </ChatCitationProvider>
  );
}

function ChatLayoutInner({
  workspaceId,
  sessions,
  sessionsLoading,
  sessionsError,
  creatingSession,
  activeSessionId,
  activeSession,
  onSelectSession,
  onNewChat,
  messages,
  messagesLoading,
  messagesError,
  isStreaming,
  streamError,
  stoppedMessageId,
  onSend,
  onStop,
  onRegenerate,
}: Props) {
  const ui = useChatCitationUi();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [workspaceDocuments, setWorkspaceDocuments] = useState<Document[]>([]);
  const [extraDocs, setExtraDocs] = useState<Document[]>([]);

  // Load workspace catalog (for context bar + titles).
  useEffect(() => {
    let active = true;
    listDocuments(workspaceId, { page: 1, pageSize: 100 })
      .then((data) => {
        if (active) setWorkspaceDocuments(data.items);
      })
      .catch(() => {
        if (active) setWorkspaceDocuments([]);
      });
    return () => {
      active = false;
    };
  }, [workspaceId]);

  const citedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const m of messages) {
      for (const id of documentIdsFromCitations(m.citations ?? [])) ids.add(id);
    }
    return Array.from(ids);
  }, [messages]);

  // Fetch any cited docs missing from the first page of the catalog.
  useEffect(() => {
    const known = new Set(workspaceDocuments.map((d) => d.id));
    const missing = citedIds.filter((id) => !known.has(id));
    if (missing.length === 0) {
      setExtraDocs([]);
      return;
    }
    let active = true;
    Promise.all(
      missing.map(async (id) => {
        try {
          return await getDocument(workspaceId, id);
        } catch {
          return {
            id,
            workspace_id: workspaceId,
            title: "Tài liệu không còn khả dụng",
            file_type: "pdf" as const,
            current_version_id: null,
            created_at: "",
            updated_at: "",
            // sentinel consumed below
            __missing: true,
          } as Document & { __missing?: boolean };
        }
      }),
    ).then((rows) => {
      if (!active) return;
      setExtraDocs(rows);
    });
    return () => {
      active = false;
    };
  }, [citedIds, workspaceDocuments, workspaceId]);

  const docsById = useMemo(() => {
    const map = buildDocumentMetaMap(
      [...workspaceDocuments, ...extraDocs].map((d) => {
        const missing = Boolean((d as Document & { __missing?: boolean }).__missing);
        return missing
          ? { ...d, title: "Tài liệu không còn khả dụng" }
          : d;
      }),
    );
    for (const doc of extraDocs) {
      if ((doc as Document & { __missing?: boolean }).__missing) {
        map.set(doc.id, {
          title: "Tài liệu không còn khả dụng",
          fileType: doc.file_type,
          missing: true,
        });
      }
    }
    for (const id of citedIds) {
      if (!map.has(id)) {
        map.set(id, { title: "Tài liệu" });
      }
    }
    return map;
  }, [workspaceDocuments, extraDocs, citedIds]);

  const usedDocuments: ContextDocument[] = useMemo(() => {
    return citedIds.map((id) => {
      const meta = docsById.get(id);
      return {
        id,
        title: meta?.title || "Tài liệu",
        fileType: meta?.fileType ? String(meta.fileType) : undefined,
      };
    });
  }, [citedIds, docsById]);

  const fallbackCitations = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m.role === "assistant" && (m.citations?.length ?? 0) > 0) {
        return mapCitations(m.citations, docsById);
      }
    }
    return [];
  }, [messages, docsById]);

  const { panelCitations, setPanelCitations } = ui;

  // Keep Source Panel seeded with the latest assistant citations.
  useEffect(() => {
    if (fallbackCitations.length === 0) return;
    if (panelCitations.length === 0) {
      setPanelCitations(fallbackCitations);
      return;
    }
    const panelMessageId = panelCitations[0]?.messageId;
    const latestMessageId = fallbackCitations[0]?.messageId;
    if (
      !isStreaming &&
      panelMessageId &&
      latestMessageId &&
      panelMessageId !== latestMessageId
    ) {
      setPanelCitations(fallbackCitations);
    }
  }, [fallbackCitations, isStreaming, panelCitations, setPanelCitations]);

  return (
    <div className="flex h-[calc(100vh-4rem)] min-h-0 bg-base">
      <SessionSidebar
        sessions={sessions}
        loading={sessionsLoading}
        error={sessionsError}
        activeSessionId={activeSessionId}
        creating={creatingSession}
        collapsed={ui.chatSidebarCollapsed}
        onToggleCollapsed={() => ui.setChatSidebarCollapsed(!ui.chatSidebarCollapsed)}
        onSelectSession={onSelectSession}
        onNewChat={onNewChat}
        mobileOpen={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-2 border-b border-border-default bg-surface px-3 py-2.5">
          <button
            type="button"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Mở danh sách phiên chat"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-secondary hover:bg-elevated lg:hidden"
          >
            <PanelLeft className="h-4 w-4" aria-hidden />
          </button>

          <div className="min-w-0 flex-1">
            <p className="truncate text-body-sm font-medium text-primary">
              {activeSession ? sessionTitleLabel(activeSession) : "AI Research Chat"}
            </p>
            <p className="truncate text-caption text-tertiary">
              Trả lời có trích dẫn từ tài liệu workspace
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              if (ui.sourcePanelOpen && typeof window !== "undefined" && window.innerWidth >= 1280) {
                ui.setSourcePanelOpen(false);
              } else {
                ui.setSourcePanelOpen(true);
                ui.setSourcePanelMobileOpen(true);
              }
            }}
            aria-label={ui.sourcePanelOpen ? "Đóng bảng nguồn" : "Mở bảng nguồn"}
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-secondary hover:bg-elevated"
          >
            <PanelRight className="h-4 w-4" aria-hidden />
          </button>
        </div>

        {activeSessionId ? (
          <>
            <ConversationPanel
              workspaceId={workspaceId}
              messages={messages}
              loading={messagesLoading}
              error={messagesError}
              isStreaming={isStreaming}
              streamError={streamError}
              stoppedMessageId={stoppedMessageId}
              onRegenerate={onRegenerate}
              docsById={docsById}
            />
            <MessageInput
              workspaceId={workspaceId}
              isStreaming={isStreaming}
              onSend={onSend}
              onStop={onStop}
              usedDocuments={usedDocuments}
              workspaceDocuments={workspaceDocuments}
            />
          </>
        ) : (
          <EmptyChatState variant="no-session" onNewChat={onNewChat} creating={creatingSession} />
        )}
      </div>

      <SourcePanel workspaceId={workspaceId} fallbackCitations={fallbackCitations} />
    </div>
  );
}
