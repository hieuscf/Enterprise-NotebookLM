/**
 * =============================================================================
 * File: injectCitationNodes.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Replace [n] markers inside markdown React children with CitationChip.
 * Responsibilities:
 *   - Recursively walk react-markdown children; leave unknown [n] as text
 * Dependencies:
 *   - CitationChip, CitationViewModel
 * Public Exports:
 *   - injectCitationNodes
 * Database/Table: N/A
 * Related Modules: AnswerContent
 * Important Notes: Only known display indexes become chips.
 * =============================================================================
 */

import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";

import { CitationChip } from "@/features/chat/citation/CitationChip";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";

const MARKER = /\[(\d+)\]/g;

export function injectCitationNodes(
  children: ReactNode,
  workspaceId: string,
  byDisplayIndex: Map<number, CitationViewModel>,
): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === "string" || typeof child === "number") {
      return replaceInString(String(child), workspaceId, byDisplayIndex);
    }
    if (!isValidElement(child)) return child;

    const element = child as ReactElement<{ children?: ReactNode }>;
    if (element.props.children == null) return child;

    return cloneElement(element, {
      ...element.props,
      children: injectCitationNodes(element.props.children, workspaceId, byDisplayIndex),
    });
  });
}

function replaceInString(
  text: string,
  workspaceId: string,
  byDisplayIndex: Map<number, CitationViewModel>,
): ReactNode {
  if (!text.includes("[")) return text;

  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  MARKER.lastIndex = 0;

  while ((match = MARKER.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const index = Number(match[1]);
    const citation = byDisplayIndex.get(index);
    if (citation) {
      nodes.push(
        <CitationChip
          key={`cite-${citation.id}-${match.index}`}
          workspaceId={workspaceId}
          citation={citation}
        />,
      );
    } else {
      nodes.push(match[0]);
    }
    last = match.index + match[0].length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length === 1 ? nodes[0] : nodes;
}
