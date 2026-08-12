/**
 * =============================================================================
 * File: ChatCitationContext.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Shared citation / source-panel UI state for the Research Workspace.
 * Responsibilities:
 *   - active / hovered citation; source panel open; sidebar collapse
 *   - Derive active citation view-model without duplicating message state
 * Dependencies:
 *   - citation-mapper, citation-types
 * Public Exports:
 *   - ChatCitationProvider, useChatCitationUi
 * Database/Table: N/A
 * Related Modules: ChatLayout, CitationChip, SourcePanel
 * Important Notes: Presentation state only — does not own message/stream data.
 * =============================================================================
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { CitationViewModel } from "@/features/chat/citation/citation-types";

type ChatCitationUiValue = {
  activeCitationId: string | null;
  hoveredCitationId: string | null;
  sourcePanelOpen: boolean;
  chatSidebarCollapsed: boolean;
  sourcePanelMobileOpen: boolean;
  /** Citations for the message currently driving the source panel. */
  panelCitations: CitationViewModel[];
  setPanelCitations: (citations: CitationViewModel[]) => void;
  setHoveredCitationId: (id: string | null) => void;
  activateCitation: (citation: CitationViewModel, options?: { openPanel?: boolean }) => void;
  clearActiveCitation: () => void;
  setSourcePanelOpen: (open: boolean) => void;
  setChatSidebarCollapsed: (collapsed: boolean) => void;
  setSourcePanelMobileOpen: (open: boolean) => void;
  highlightedCitationId: string | null;
};

const ChatCitationContext = createContext<ChatCitationUiValue | null>(null);

export function ChatCitationProvider({ children }: { children: ReactNode }) {
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);
  const [hoveredCitationId, setHoveredCitationId] = useState<string | null>(null);
  const [sourcePanelOpen, setSourcePanelOpen] = useState(true);
  const [chatSidebarCollapsed, setChatSidebarCollapsed] = useState(false);
  const [sourcePanelMobileOpen, setSourcePanelMobileOpen] = useState(false);
  const [panelCitations, setPanelCitations] = useState<CitationViewModel[]>([]);

  const activateCitation = useCallback(
    (citation: CitationViewModel, options?: { openPanel?: boolean }) => {
      setActiveCitationId(citation.id);
      setPanelCitations((prev) => {
        if (prev.some((c) => c.id === citation.id)) return prev;
        // Prefer keeping the message's citation set; caller usually sets panel first.
        return prev.length > 0 ? prev : [citation];
      });
      if (options?.openPanel !== false) {
        setSourcePanelOpen(true);
        setSourcePanelMobileOpen(true);
      }
    },
    [],
  );

  const clearActiveCitation = useCallback(() => {
    setActiveCitationId(null);
  }, []);

  const highlightedCitationId = hoveredCitationId ?? activeCitationId;

  const value = useMemo<ChatCitationUiValue>(
    () => ({
      activeCitationId,
      hoveredCitationId,
      sourcePanelOpen,
      chatSidebarCollapsed,
      sourcePanelMobileOpen,
      panelCitations,
      setPanelCitations,
      setHoveredCitationId,
      activateCitation,
      clearActiveCitation,
      setSourcePanelOpen,
      setChatSidebarCollapsed,
      setSourcePanelMobileOpen,
      highlightedCitationId,
    }),
    [
      activeCitationId,
      hoveredCitationId,
      sourcePanelOpen,
      chatSidebarCollapsed,
      sourcePanelMobileOpen,
      panelCitations,
      activateCitation,
      clearActiveCitation,
      highlightedCitationId,
    ],
  );

  return (
    <ChatCitationContext.Provider value={value}>{children}</ChatCitationContext.Provider>
  );
}

export function useChatCitationUi(): ChatCitationUiValue {
  const ctx = useContext(ChatCitationContext);
  if (!ctx) {
    throw new Error("useChatCitationUi must be used within ChatCitationProvider");
  }
  return ctx;
}

/** Optional hook for components that may render outside the provider. */
export function useChatCitationUiOptional(): ChatCitationUiValue | null {
  return useContext(ChatCitationContext);
}
