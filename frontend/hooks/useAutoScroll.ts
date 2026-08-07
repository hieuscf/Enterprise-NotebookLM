/**
 * =============================================================================
 * File: useAutoScroll.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Auto-scroll a message list to the bottom on new content, but only
 *          while the user is already at the bottom (FR4 §3/§10).
 * Responsibilities:
 *   - Track whether the scroll container is near the bottom
 *   - Scroll to bottom when `trigger` changes and the user was at bottom
 *   - Expose a "new content available" flag when the user has scrolled up
 * Dependencies:
 *   - None (plain DOM scroll math)
 * Public Exports:
 *   - useAutoScroll
 * Database/Table: N/A
 * Related Modules: features/chat/ConversationPanel
 * Important Notes: `trigger` should change on every token/message so the
 *   effect can decide to scroll — pass e.g. `messages.length + streamedChars`.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const BOTTOM_THRESHOLD_PX = 80;

export function useAutoScroll(trigger: unknown) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isAtBottomRef = useRef(true);
  const [hasNewContent, setHasNewContent] = useState(false);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
    isAtBottomRef.current = true;
    setHasNewContent(false);
  }, []);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom <= BOTTOM_THRESHOLD_PX;
    isAtBottomRef.current = atBottom;
    if (atBottom) setHasNewContent(false);
  }, []);

  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollToBottom();
    } else {
      setHasNewContent(true);
    }
    // Intentionally depends on the opaque `trigger` value only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trigger]);

  return { containerRef, handleScroll, hasNewContent, scrollToBottom };
}
