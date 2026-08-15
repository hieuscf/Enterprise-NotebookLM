/**
 * =============================================================================
 * File: comparison-badges.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Shared status / risk / evidence badges for CMP-17 and CMP-18.
 * Responsibilities:
 *   - Render clause status, risk level, and citation verification with text+icon
 * Dependencies:
 *   - comparison-summary helpers, lucide-react, design tokens
 * Public Exports:
 *   - StatusBadge, RiskBadge, EvidenceStateBadge, riskToneClass
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, ClauseComparisonView
 * Important Notes: Color is never the only indicator.
 * =============================================================================
 */

"use client";

import { AlertTriangle, Check, Minus, Pencil, Plus, ShieldAlert } from "lucide-react";

import {
  clauseStatusLabel,
  evidenceStateLabel,
  riskLevelLabel,
  type EvidenceUiState,
} from "@/features/comparisons/comparison-summary";
import { cn } from "@/lib/utils";

export function riskToneClass(level: string): string {
  const key = level.toUpperCase();
  if (key === "CRITICAL") return "border-danger/35 bg-danger-soft text-danger";
  if (key === "HIGH") return "border-warning/35 bg-warning/10 text-warning";
  if (key === "MEDIUM") return "border-citation/35 bg-citation-soft text-citation";
  return "border-border-default bg-elevated text-secondary";
}

export function StatusBadge({ status }: { status: string }) {
  const key = status.toUpperCase();
  const Icon =
    key === "ADDED" ? Plus : key === "REMOVED" ? Minus : key === "MODIFIED" ? Pencil : Check;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-caption font-semibold",
        key === "MODIFIED" && "border-warning/30 bg-warning/10 text-warning",
        key === "ADDED" && "border-info/30 bg-info/10 text-info",
        key === "REMOVED" && "border-danger/30 bg-danger-soft text-danger",
        key === "UNCHANGED" && "border-border-default bg-elevated text-tertiary",
        key === "UNRESOLVED" && "border-warning/30 bg-warning/5 text-secondary",
      )}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {clauseStatusLabel(status)}
    </span>
  );
}

export function RiskBadge({ level }: { level: string | null }) {
  if (!level) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-caption font-semibold",
        riskToneClass(level),
      )}
    >
      <ShieldAlert className="h-3 w-3" aria-hidden />
      {riskLevelLabel(level)}
    </span>
  );
}

export function EvidenceStateBadge({ state }: { state: EvidenceUiState }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-caption font-semibold",
        state === "verified" && "border-success/30 bg-success/10 text-success",
        state === "partial" && "border-warning/30 bg-warning/10 text-warning",
        state === "unverified" && "border-warning/30 bg-warning/5 text-secondary",
        state === "unavailable" && "border-border-default bg-elevated text-tertiary",
      )}
    >
      {state === "verified" ? (
        <Check className="h-3 w-3" aria-hidden />
      ) : (
        <AlertTriangle className="h-3 w-3" aria-hidden />
      )}
      {evidenceStateLabel(state)}
    </span>
  );
}
