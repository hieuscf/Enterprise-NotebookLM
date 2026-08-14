/**
 * =============================================================================
 * File: SectionItem.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: One outline node — title, citation, body blocks, nested children.
 * Responsibilities:
 *   - Dispatch paragraph / bullet / table blocks
 *   - Recurse for arbitrary heading depth
 * Dependencies:
 *   - SectionTitle, SectionCitationBadge, ParagraphContent, BulletList, StructuredTable
 * Public Exports:
 *   - SectionItem
 * Database/Table: N/A
 * Related Modules: SectionExtractionAnswer
 * Important Notes: Never wrap numbered headings in <ol>.
 * =============================================================================
 */

import type { SectionNode } from "@/features/chat/section-extraction/section-extraction-adapter";
import { BulletList } from "@/features/chat/section-extraction/BulletList";
import { ParagraphContent } from "@/features/chat/section-extraction/ParagraphContent";
import { SectionCitationBadge } from "@/features/chat/section-extraction/SectionCitationBadge";
import { SectionTitle } from "@/features/chat/section-extraction/SectionTitle";
import { StructuredTable } from "@/features/chat/section-extraction/StructuredTable";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  node: SectionNode;
  /** Visual nesting from the outline tree (1 = root), not a list index. */
  level?: number;
};

export function SectionItem({ workspaceId, node, level = 1 }: Props) {
  const indent = Math.max(0, level - 1);

  return (
    <section
      className={cn("section-item", indent > 0 && "border-l border-border-default/80")}
      style={indent > 0 ? { marginLeft: indent * 12, paddingLeft: 12 } : undefined}
      data-section-number={node.number ?? undefined}
      data-section-depth={level}
    >
      <SectionTitle
        number={node.number}
        title={node.title}
        depth={level}
        trailing={
          <SectionCitationBadge workspaceId={workspaceId} citations={node.citations} />
        }
      />

      {node.blocks.length > 0 ? (
        <div className="mt-2 space-y-2">
          {node.blocks.map((block, index) => {
            if (block.kind === "paragraph") {
              return <ParagraphContent key={`p-${index}`} text={block.text} />;
            }
            if (block.kind === "bullets") {
              return <BulletList key={`b-${index}`} items={block.items} />;
            }
            return <StructuredTable key={`t-${index}`} table={block.table} />;
          })}
        </div>
      ) : null}

      {node.children.length > 0 ? (
        <div className="mt-4 space-y-4">
          {node.children.map((child) => (
            <SectionItem
              key={child.key}
              workspaceId={workspaceId}
              node={child}
              level={level + 1}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
