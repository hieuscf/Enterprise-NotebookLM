/**
 * =============================================================================
 * File: ReportPreviewEvidence.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Evidence list for CMP-25 clause and report-level preview.
 * Responsibilities:
 *   - Show backend evidence metadata and verification state
 *   - Offer exact source navigation only when page or chunk is present
 * Dependencies:
 *   - comparison-badges, comparison-report-preview exactSourceHref
 * Public Exports:
 *   - ReportPreviewEvidence
 * Database/Table: N/A
 * Related Modules: ReportPreviewClauseDetail, ComparisonReportPreview
 * Important Notes: Never navigate to page 1 as a guess. Unverified evidence
 *   must not share the verified trust signal. Render text, never raw HTML.
 * =============================================================================
 */

"use client";

import { Check, ExternalLink } from "lucide-react";
import Link from "next/link";

import { EvidenceStateBadge } from "@/features/comparisons/comparison-badges";
import { displayClauseId } from "@/features/comparisons/comparison-summary";
import {
  emptyClauseMessage,
  exactSourceHref,
  evidenceVerificationLabel,
  isVerifiedEvidence,
  sourceLocationLabel,
} from "@/features/reports/comparison-report-preview";
import { cn } from "@/lib/utils";
import type { EvidenceUiState } from "@/features/comparisons/comparison-summary";
import type { ReportPreviewEvidence as Evidence } from "@/types/reports";

type Props = {
  workspaceId: string;
  evidence: Evidence[];
  heading?: string;
};

function asEvidenceState(state: string | null | undefined): EvidenceUiState {
  const key = String(state ?? "").toLowerCase();
  if (key === "verified") return "verified";
  if (key === "partial") return "partial";
  if (key === "unavailable") return "unavailable";
  return "unverified";
}

export function ReportPreviewEvidence({
  workspaceId,
  evidence,
  heading = "Bằng chứng",
}: Props) {
  if (evidence.length === 0) {
    return (
      <section aria-label={heading}>
        <h3 className="text-body-sm font-semibold text-primary">{heading}</h3>
        <p className="mt-1 text-body-sm text-secondary">{emptyClauseMessage("evidence")}</p>
      </section>
    );
  }

  return (
    <section aria-label={heading}>
      <h3 className="text-body-sm font-semibold text-primary">{heading}</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {evidence.map((item, index) => {
          const href = exactSourceHref(workspaceId, item);
          const verified = isVerifiedEvidence(item.verification_state);
          const state = asEvidenceState(item.verification_state);
          return (
            <li
              key={`${item.document_id ?? "ev"}-${item.clause_id ?? index}`}
              className={cn(
                "rounded-md border px-3 py-2.5",
                verified
                  ? "border-success/30 bg-success/5"
                  : "border-warning/25 bg-warning/5",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <EvidenceStateBadge state={state} />
                <span className="text-caption font-medium text-secondary">
                  {evidenceVerificationLabel(item.verification_state)}
                </span>
              </div>
              <p className="mt-1 text-body-sm text-primary">
                {sourceLocationLabel(item) ||
                  (item.clause_id ? `Điều ${displayClauseId(item.clause_id)}` : "Bằng chứng")}
              </p>
              {item.display_text ? (
                <p className="mt-1 whitespace-pre-wrap text-body-sm text-secondary">
                  {item.display_text}
                </p>
              ) : null}
              {href ? (
                <Link
                  href={href}
                  className="mt-2 inline-flex items-center gap-1 text-caption font-medium text-accent-primary hover:underline"
                >
                  Mở nguồn
                  <ExternalLink className="h-3 w-3" aria-hidden />
                </Link>
              ) : (
                <p className="mt-2 text-caption text-tertiary">
                  Không đủ vị trí chính xác để mở tài liệu nguồn.
                </p>
              )}
              {verified ? (
                <p className="sr-only">
                  <Check className="inline h-3 w-3" aria-hidden /> Đã xác minh
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
