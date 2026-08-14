/**
 * =============================================================================
 * File: DocumentBlocks.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Semantic block renderers for Canonical Knowledge Document.
 * Responsibilities:
 *   - Heading / paragraph / list / table / figure / quote / rule / code
 *   - Preserve data-block-id and deterministic text nodes for citations
 * Dependencies:
 *   - react-markdown, remark-gfm, document-structure, markdown-components
 * Public Exports:
 *   - DocumentBlock, DocumentHeader
 * Database/Table: N/A
 * Related Modules: DocumentRenderer, KnowledgeView
 * Important Notes: Presentation only — never rewrite Canonical Markdown.
 * =============================================================================
 */

"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { CanonicalBlock } from "@/types/canonical";

import {
  classifyParagraphKind,
  displayCodeText,
  displayHeadingText,
  displayQuoteText,
  parseFigure,
  parseListModel,
  parseMarkdownTable,
} from "./document-structure";
import {
  knowledgeMarkdownComponents,
  knowledgeUrlTransform,
} from "./markdown-components";

type BlockProps = {
  block: CanonicalBlock;
  role?: "letterhead" | "title" | "subtitle" | "section";
};

export const DocumentBlock = memo(function DocumentBlock({
  block,
  role = "section",
}: BlockProps) {
  if (block.block_type === "heading") {
    return <HeadingBlock block={block} role={role} />;
  }
  if (block.block_type === "table") {
    return <TableBlock block={block} />;
  }
  if (block.block_type === "list") {
    return <ListBlock block={block} />;
  }
  if (block.block_type === "figure") {
    return <FigureBlock block={block} />;
  }
  return <ParagraphBlock block={block} />;
});

export const DocumentHeader = memo(function DocumentHeader({
  blocks,
  titleBlockId,
  subtitleBlockId,
}: {
  blocks: CanonicalBlock[];
  titleBlockId: string | null;
  subtitleBlockId: string | null;
}) {
  if (!blocks.length) return null;
  return (
    <header className="knowledge-letterhead">
      {blocks.map((block) => {
        const role =
          block.id === titleBlockId
            ? "title"
            : block.id === subtitleBlockId
              ? "subtitle"
              : "letterhead";
        return <DocumentBlock key={block.id} block={block} role={role} />;
      })}
    </header>
  );
});

function HeadingBlock({ block, role }: BlockProps) {
  const level = Math.min(6, Math.max(1, block.heading_level ?? 2));
  const text = displayHeadingText(block.content);

  if (role === "letterhead") {
    return (
      <p data-block-id={block.id} id={block.id} className="knowledge-letterhead-line">
        {text}
      </p>
    );
  }
  if (role === "subtitle") {
    return (
      <p data-block-id={block.id} id={block.id} className="knowledge-doc-subtitle">
        {text}
      </p>
    );
  }

  const className = cn(
    "knowledge-h",
    role === "title" && "knowledge-doc-title",
    role === "section" && level <= 1 && "knowledge-h1",
    role === "section" && level === 2 && "knowledge-h2",
    role === "section" && level === 3 && "knowledge-h3",
    role === "section" && level >= 4 && "knowledge-h4",
  );

  const headingLevel = role === "title" ? 1 : level;
  const shared = {
    "data-block-id": block.id,
    id: block.id,
    className,
  };

  if (headingLevel === 1) return <h1 {...shared}>{text}</h1>;
  if (headingLevel === 2) return <h2 {...shared}>{text}</h2>;
  if (headingLevel === 3) return <h3 {...shared}>{text}</h3>;
  if (headingLevel === 4) return <h4 {...shared}>{text}</h4>;
  if (headingLevel === 5) return <h5 {...shared}>{text}</h5>;
  return <h6 {...shared}>{text}</h6>;
}

function ParagraphBlock({ block }: BlockProps) {
  const kind = classifyParagraphKind(block.content);

  if (kind === "rule") {
    return (
      <hr
        data-block-id={block.id}
        id={block.id}
        className="knowledge-hr"
        aria-hidden
      />
    );
  }

  if (kind === "quote") {
    const text = displayQuoteText(block.content);
    return (
      <blockquote data-block-id={block.id} id={block.id} className="knowledge-quote">
        {text}
      </blockquote>
    );
  }

  if (kind === "code") {
    const text = displayCodeText(block.content);
    return (
      <pre data-block-id={block.id} id={block.id} className="knowledge-pre">
        <code className="knowledge-code-block">{text}</code>
      </pre>
    );
  }

  return (
    <p data-block-id={block.id} id={block.id} className="knowledge-p">
      {block.content}
    </p>
  );
}

function ListBlock({ block }: BlockProps) {
  const model = parseListModel(block.content);
  const nested = /(?:^|\n)\s{2,}(?:[-*+]|\d+[.)])\s+/.test(block.content);
  if (nested) {
    return (
      <div data-block-id={block.id} id={block.id} className="knowledge-md-host">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          urlTransform={knowledgeUrlTransform}
          components={knowledgeMarkdownComponents}
        >
          {block.content}
        </ReactMarkdown>
      </div>
    );
  }

  const ListTag = model.ordered ? "ol" : "ul";
  return (
    <ListTag
      data-block-id={block.id}
      id={block.id}
      className={model.ordered ? "knowledge-ol" : "knowledge-ul"}
    >
      {model.items.map((item, i) => (
        <li key={`${block.id}-${i}`} className="knowledge-li">
          {item}
        </li>
      ))}
    </ListTag>
  );
}

function TableBlock({ block }: BlockProps) {
  const table = parseMarkdownTable(block.content);
  if (!table) {
    return (
      <div data-block-id={block.id} id={block.id} className="knowledge-md-host">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          urlTransform={knowledgeUrlTransform}
          components={knowledgeMarkdownComponents}
        >
          {block.content}
        </ReactMarkdown>
      </div>
    );
  }

  const alignClass = (i: number) => {
    const a = table.alignments[i] ?? "left";
    if (a === "right") return "text-right";
    if (a === "center") return "text-center";
    return "text-left";
  };

  return (
    <div
      data-block-id={block.id}
      id={block.id}
      className="knowledge-table-scroll"
    >
      <table className="knowledge-table">
        <thead>
          <tr>
            {table.headers.map((h, i) => (
              <th key={`${block.id}-h-${i}`} className={alignClass(i)}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={`${block.id}-r-${r}`}>
              {row.map((cell, c) => (
                <td key={`${block.id}-c-${r}-${c}`} className={alignClass(c)}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FigureBlock({ block }: BlockProps) {
  const figure = parseFigure(block.content);
  if (!figure) {
    return (
      <figure data-block-id={block.id} id={block.id} className="knowledge-figure">
        {block.content || "Figure"}
      </figure>
    );
  }
  return (
    <figure data-block-id={block.id} id={block.id} className="knowledge-figure">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={figure.src} alt={figure.alt} className="knowledge-img" />
      {figure.caption ? <figcaption>{figure.caption}</figcaption> : null}
    </figure>
  );
}
