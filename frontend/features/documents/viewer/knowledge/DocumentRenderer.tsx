/**
 * =============================================================================
 * File: DocumentRenderer.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Map Canonical Blocks → semantic document article (presentation).
 * Responsibilities:
 *   - Group conservative document header
 *   - Render body blocks without re-parsing Canonical Markdown as source
 *   - Memoize so citation/AI context updates do not rebuild the tree
 * Dependencies:
 *   - DocumentBlocks, document-structure
 * Public Exports:
 *   - DocumentRenderer, KnowledgeSkeleton, KnowledgeEmpty, KnowledgeMarkdownFallback
 * Database/Table: N/A
 * Related Modules: KnowledgeView
 * Important Notes: Canonical blocks are the AST; this file is presentation.
 * =============================================================================
 */

"use client";

import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { CanonicalBlock } from "@/types/canonical";

import { DocumentBlock, DocumentHeader } from "./DocumentBlocks";
import { isRawMarkdownBlob, splitDocumentHeader } from "./document-structure";
import {
  knowledgeMarkdownComponents,
  knowledgeUrlTransform,
} from "./markdown-components";

type Props = {
  blocks: CanonicalBlock[];
  documentTitle?: string | null;
};

export const DocumentRenderer = memo(function DocumentRenderer({
  blocks,
  documentTitle = null,
}: Props) {
  const split = useMemo(
    () => splitDocumentHeader(blocks, documentTitle),
    [blocks, documentTitle],
  );

  if (isRawMarkdownBlob(blocks)) {
    return (
      <KnowledgeMarkdownFallback
        markdown={blocks[0].content}
        blockId={blocks[0].id}
      />
    );
  }

  return (
    <>
      <DocumentHeader
        blocks={split.header}
        titleBlockId={split.titleBlockId}
        subtitleBlockId={split.subtitleBlockId}
      />
      {split.body.map((block) => (
        <DocumentBlock
          key={block.id}
          block={block}
          role={block.id === split.titleBlockId ? "title" : "section"}
        />
      ))}
    </>
  );
});

export function KnowledgeMarkdownFallback({
  markdown,
  blockId,
}: {
  markdown: string;
  blockId?: string;
}) {
  return (
    <div data-block-id={blockId} className="knowledge-md-host">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={knowledgeUrlTransform}
        components={knowledgeMarkdownComponents}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

export function KnowledgeSkeleton() {
  return (
    <div className="knowledge-scroll" aria-busy="true" aria-live="polite">
      <article className="knowledge-canvas" aria-hidden>
        <div className="mx-auto mb-10 space-y-3">
          <div className="mx-auto h-4 w-2/3 animate-pulse rounded-sm bg-inset" />
          <div className="mx-auto h-3 w-1/2 animate-pulse rounded-sm bg-inset" />
          <div className="mx-auto h-3 w-2/5 animate-pulse rounded-sm bg-inset" />
        </div>
        <div className="space-y-4">
          <div className="h-6 w-3/5 animate-pulse rounded-sm bg-inset" />
          <div className="h-3 w-full animate-pulse rounded-sm bg-inset" />
          <div className="h-3 w-[96%] animate-pulse rounded-sm bg-inset" />
          <div className="h-3 w-[92%] animate-pulse rounded-sm bg-inset" />
          <div className="mt-8 h-5 w-2/5 animate-pulse rounded-sm bg-inset" />
          <div className="h-3 w-full animate-pulse rounded-sm bg-inset" />
          <div className="h-3 w-[94%] animate-pulse rounded-sm bg-inset" />
          <div className="h-24 w-full animate-pulse rounded-sm bg-inset" />
        </div>
        <p className="sr-only">Loading document…</p>
      </article>
    </div>
  );
}

export function KnowledgeEmpty({ message }: { message?: string }) {
  return (
    <div className="knowledge-scroll">
      <article className="knowledge-canvas flex min-h-[16rem] flex-col items-center justify-center text-center">
        <p className="font-sans text-body-sm font-medium text-primary">
          Document content is unavailable.
        </p>
        {message ? (
          <p className="mt-2 max-w-sm font-sans text-caption text-secondary">{message}</p>
        ) : null}
      </article>
    </div>
  );
}
