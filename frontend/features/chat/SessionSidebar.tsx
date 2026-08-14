/**
 * =============================================================================
 * File: SessionSidebar.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Collapsible chat session list grouped by day (Research Workspace).
 * Responsibilities:
 *   - New Chat; Hôm nay / Hôm qua sections; active state; collapse to icons
 *   - Off-canvas drawer on mobile
 * Dependencies:
 *   - lucide-react, chat-format
 * Public Exports:
 *   - SessionSidebar
 * Database/Table: N/A
 * Related Modules: features/chat/ChatLayout
 * Important Notes: No last-message preview — not in OpenAPI ChatSession.
 * =============================================================================
 */

"use client";

import {
  Loader2,
  MessageSquare,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from "lucide-react";

import {
  formatRelativeTime,
  groupSessionsByDay,
  sessionTitleLabel,
} from "@/features/chat/chat-format";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/types/chat";

type Props = {
  sessions: ChatSession[];
  loading: boolean;
  error: string | null;
  activeSessionId: string | null;
  creating: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
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
  collapsed,
  onToggleCollapsed,
  onSelectSession,
  onNewChat,
  mobileOpen,
  onClose,
}: Props) {
  const groups = groupSessionsByDay(sessions);

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
          "fixed inset-y-0 left-0 z-40 flex h-svh shrink-0 flex-col overflow-hidden border-r border-border-default bg-surface",
          "transition-[width,transform] duration-200 lg:static lg:h-full lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "lg:w-14" : "w-[min(100%,17.5rem)] lg:w-[17.5rem]",
          "w-[min(100%,17.5rem)]",
        )}
      >
        <div
          className={cn(
            "flex shrink-0 items-center gap-2 border-b border-border-default p-2.5",
            collapsed && "lg:flex-col",
          )}
        >
          <button
            type="button"
            onClick={onNewChat}
            disabled={creating}
            title="Chat mới"
            aria-label="Chat mới"
            className={cn(
              "inline-flex items-center justify-center gap-2 rounded-md bg-accent-primary text-white",
              "transition-colors hover:bg-accent-primary-hover disabled:cursor-not-allowed disabled:opacity-60",
              collapsed
                ? "h-9 w-9 lg:w-9"
                : "h-9 flex-1 px-3 text-body-sm font-medium",
            )}
          >
            {creating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <MessageSquarePlus className="h-4 w-4" aria-hidden />
            )}
            {!collapsed ? <span className="lg:inline">Chat mới</span> : null}
          </button>

          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng danh sách phiên chat"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-secondary hover:bg-elevated lg:hidden"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>

          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Mở rộng sidebar chat" : "Thu gọn sidebar chat"}
            className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-md text-secondary hover:bg-elevated lg:flex"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" aria-hidden />
            ) : (
              <PanelLeftClose className="h-4 w-4" aria-hidden />
            )}
          </button>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2" aria-label="Phiên chat">
          {loading ? (
            <div className="flex flex-col gap-2 p-1" aria-busy aria-label="Đang tải phiên chat">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-11 animate-pulse rounded-md bg-elevated/60" />
              ))}
            </div>
          ) : error ? (
            <p className={cn("p-2 text-body-sm text-danger", collapsed && "lg:hidden")}>{error}</p>
          ) : sessions.length === 0 ? (
            <p className={cn("p-2 text-body-sm text-tertiary", collapsed && "lg:hidden")}>
              Chưa có cuộc trò chuyện nào.
            </p>
          ) : collapsed ? (
            <ul className="hidden flex-col gap-1 lg:flex">
              {sessions.map((session) => {
                const isActive = session.id === activeSessionId;
                return (
                  <li key={session.id}>
                    <button
                      type="button"
                      title={sessionTitleLabel(session)}
                      aria-label={sessionTitleLabel(session)}
                      onClick={() => onSelectSession(session.id)}
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-md transition-colors",
                        isActive
                          ? "bg-accent-primary-soft text-accent-primary"
                          : "text-secondary hover:bg-elevated hover:text-primary",
                      )}
                    >
                      <MessageSquare className="h-4 w-4" aria-hidden />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="flex flex-col gap-3">
              {groups.map((group) => (
                <div key={group.key}>
                  <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-tertiary">
                    {group.label}
                  </p>
                  <ul className="flex flex-col gap-0.5">
                    {group.sessions.map((session) => {
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
                              "flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left transition-colors",
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
                </div>
              ))}
            </div>
          )}
        </nav>
      </aside>
    </>
  );
}
