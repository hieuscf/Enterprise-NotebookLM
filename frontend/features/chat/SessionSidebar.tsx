/**
 * =============================================================================
 * File: SessionSidebar.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Chat session list — title, updated time, New Chat, mobile drawer.
 * Responsibilities:
 *   - Render sessions in the exact order the backend returns them (never
 *     re-sorted client-side — updated_at DESC is already applied server-side)
 *   - Highlight the active session; "New Chat" creates + selects a session
 *   - Off-canvas drawer on mobile, static column on desktop (mirrors the
 *     app-level Sidebar's fixed/translate-x pattern — no new dependency)
 * Dependencies:
 *   - lucide-react, lib/utils, features/chat/chat-format
 * Public Exports:
 *   - SessionSidebar
 * Database/Table: N/A
 * Related Modules: features/chat/ChatLayout, hooks/useChatSessions
 * Important Notes: No "last message preview" — OpenAPI ChatSession does not
 *   expose last_message_preview/message_count (see session_service.py TODO);
 *   showing title + relative updated time only keeps the contract untouched.
 * =============================================================================
 */

"use client";

import { Loader2, MessageSquarePlus, X } from "lucide-react";

import { formatRelativeTime, sessionTitleLabel } from "@/features/chat/chat-format";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/types/chat";

type Props = {
  sessions: ChatSession[];
  loading: boolean;
  error: string | null;
  activeSessionId: string | null;
  creating: boolean;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  mobileOpen: boolean;
  onClose: () => void;
};

export function SessionSidebar({
  sessions,
  loading,
  error,
  activeSessionId,
  creating,
  onSelectSession,
  onNewChat,
  mobileOpen,
  onClose,
}: Props) {
  return (
    <>
      {mobileOpen ? (
        <div
          aria-hidden
          onClick={onClose}
          className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden"
        />
      ) : null}

      <aside
        aria-label="Danh sách phiên chat"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-border-default bg-surface",
          "transition-transform duration-200 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-default p-3">
          <button
            type="button"
            onClick={onNewChat}
            disabled={creating}
            className="flex flex-1 items-center gap-2 rounded-md bg-accent-primary px-3 py-2 text-body-sm font-medium text-white transition-colors hover:bg-accent-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            {creating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <MessageSquarePlus className="h-4 w-4" aria-hidden />
            )}
            Chat mới
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng danh sách phiên chat"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-secondary hover:bg-elevated lg:hidden"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto p-2" aria-label="Phiên chat">
          {loading ? (
            <div className="flex flex-col gap-2 p-2" aria-busy aria-label="Đang tải phiên chat">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-md bg-elevated/60" />
              ))}
            </div>
          ) : error ? (
            <p className="p-3 text-body-sm text-danger">{error}</p>
          ) : sessions.length === 0 ? (
            <p className="p-3 text-body-sm text-tertiary">Chưa có cuộc trò chuyện nào.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {sessions.map((session) => {
                const isActive = session.id === activeSessionId;
                return (
                  <li key={session.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelectSession(session.id);
                        onClose();
                      }}
                      className={cn(
                        "flex w-full flex-col gap-0.5 rounded-md px-3 py-2 text-left transition-colors",
                        isActive
                          ? "bg-accent-primary-soft text-accent-primary"
                          : "text-secondary hover:bg-elevated hover:text-primary",
                      )}
                    >
                      <span className="truncate text-body-sm font-medium">
                        {sessionTitleLabel(session)}
                      </span>
                      <span className="text-caption text-tertiary">
                        {formatRelativeTime(session.updated_at)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>
      </aside>
    </>
  );
}
