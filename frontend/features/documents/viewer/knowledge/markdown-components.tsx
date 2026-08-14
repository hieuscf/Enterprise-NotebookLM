/**
 * =============================================================================
 * File: markdown-components.tsx
 * Module/Service: Document Viewer
 * Layer: UI
 * Purpose: Shared react-markdown component map for Knowledge View lists/tables.
 * Responsibilities:
 *   - Semantic HTML for GFM tables, lists, links, code
 *   - URL sanitization (no javascript: / data: HTML)
 * Dependencies:
 *   - react-markdown, document-structure
 * Public Exports:
 *   - knowledgeMarkdownComponents, knowledgeUrlTransform
 * Database/Table: N/A
 * Related Modules: KnowledgeView DocumentBlocks
 * Important Notes: Do not wrap text in extra spans — citation Range needs
 *   deterministic text nodes.
 * =============================================================================
 */

import type { Components } from "react-markdown";

import { isSafeHref } from "./document-structure";

export function knowledgeUrlTransform(url: string): string {
  if (!url) return "";
  if (url.startsWith("#")) return url;
  if (isSafeHref(url)) return url;
  return "";
}

export const knowledgeMarkdownComponents: Components = {
  h1: ({ children }) => <h1 className="knowledge-h knowledge-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="knowledge-h knowledge-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="knowledge-h knowledge-h3">{children}</h3>,
  h4: ({ children }) => <h4 className="knowledge-h knowledge-h4">{children}</h4>,
  h5: ({ children }) => <h5 className="knowledge-h knowledge-h4">{children}</h5>,
  h6: ({ children }) => <h6 className="knowledge-h knowledge-h4">{children}</h6>,
  p: ({ children }) => <p className="knowledge-p">{children}</p>,
  ul: ({ children }) => <ul className="knowledge-ul">{children}</ul>,
  ol: ({ children }) => <ol className="knowledge-ol">{children}</ol>,
  li: ({ children }) => <li className="knowledge-li">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="knowledge-quote">{children}</blockquote>
  ),
  hr: () => <hr className="knowledge-hr" />,
  a: ({ href, children }) => {
    const safe = href && isSafeHref(href) ? href : undefined;
    if (!safe) return <span>{children}</span>;
    return (
      <a href={safe} className="knowledge-a" rel="noreferrer" target="_blank">
        {children}
      </a>
    );
  },
  pre: ({ children }) => <pre className="knowledge-pre">{children}</pre>,
  code: ({ className, children }) => {
    const inline = !className;
    if (inline) return <code className="knowledge-code-inline">{children}</code>;
    return <code className="knowledge-code-block">{children}</code>;
  },
  table: ({ children }) => (
    <div className="knowledge-table-scroll">
      <table className="knowledge-table">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => <th>{children}</th>,
  td: ({ children }) => <td>{children}</td>,
  img: ({ src, alt }) => {
    if (!src) return null;
    /* Document figures may be remote; next/image is not configured for them. */
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt={alt ?? ""} className="knowledge-img" />
    );
  },
};
