/**
 * =============================================================================
 * File: JsonViewer.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Lightweight read-only collapsible JSON tree (no extra dependency).
 * Responsibilities:
 *   - Render objects/arrays/primitives; collapse/expand nested nodes
 * Dependencies:
 *   - React, lib/utils
 * Public Exports:
 *   - JsonViewer
 * Database/Table: N/A
 * Related Modules: ExtractionContent
 * Important Notes: No package.json JSON-viewer dependency — local viewer only.
 *   Does not mutate input; does not JSON.parse already-parsed objects.
 * =============================================================================
 */

"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

type Props = {
  value: unknown;
  className?: string;
  defaultExpanded?: boolean;
};

export function JsonViewer({ value, className, defaultExpanded = true }: Props) {
  return (
    <div
      className={cn(
        "overflow-x-auto rounded-md border border-border-default bg-elevated/30 p-3 font-mono text-caption text-primary",
        className,
      )}
      aria-label="JSON viewer"
    >
      <JsonNode value={value} path="$" depth={0} defaultExpanded={defaultExpanded} />
    </div>
  );
}

function JsonNode({
  value,
  path,
  depth,
  defaultExpanded,
}: {
  value: unknown;
  path: string;
  depth: number;
  defaultExpanded: boolean;
}) {
  const [open, setOpen] = useState(defaultExpanded && depth < 2);

  if (value === null) {
    return <span className="text-tertiary">null</span>;
  }
  if (typeof value === "boolean") {
    return <span className="text-accent-primary">{String(value)}</span>;
  }
  if (typeof value === "number") {
    return <span className="text-success">{String(value)}</span>;
  }
  if (typeof value === "string") {
    return <span className="text-secondary">&quot;{value}&quot;</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>[]</span>;
    return (
      <span>
        <button
          type="button"
          aria-expanded={open}
          aria-label={`${open ? "Thu gọn" : "Mở rộng"} mảng ${path}`}
          onClick={() => setOpen((v) => !v)}
          className="mr-1 rounded px-1 text-tertiary hover:bg-elevated hover:text-primary"
        >
          {open ? "▼" : "▶"}
        </button>
        <span className="text-tertiary">[{value.length}]</span>
        {open ? (
          <ul className="ml-4 mt-1 space-y-0.5 border-l border-border-default pl-3">
            {value.map((item, idx) => (
              <li key={`${path}.${idx}`}>
                <span className="text-tertiary">{idx}: </span>
                <JsonNode
                  value={item}
                  path={`${path}[${idx}]`}
                  depth={depth + 1}
                  defaultExpanded={defaultExpanded}
                />
              </li>
            ))}
          </ul>
        ) : null}
      </span>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span>{"{}"}</span>;
    return (
      <span>
        <button
          type="button"
          aria-expanded={open}
          aria-label={`${open ? "Thu gọn" : "Mở rộng"} đối tượng ${path}`}
          onClick={() => setOpen((v) => !v)}
          className="mr-1 rounded px-1 text-tertiary hover:bg-elevated hover:text-primary"
        >
          {open ? "▼" : "▶"}
        </button>
        <span className="text-tertiary">{"{…}"}</span>
        {open ? (
          <ul className="ml-4 mt-1 space-y-0.5 border-l border-border-default pl-3">
            {entries.map(([key, child]) => (
              <li key={`${path}.${key}`}>
                <span className="font-medium text-primary">{key}</span>
                <span className="text-tertiary">: </span>
                <JsonNode
                  value={child}
                  path={`${path}.${key}`}
                  depth={depth + 1}
                  defaultExpanded={defaultExpanded}
                />
              </li>
            ))}
          </ul>
        ) : null}
      </span>
    );
  }
  return <span>{String(value)}</span>;
}
