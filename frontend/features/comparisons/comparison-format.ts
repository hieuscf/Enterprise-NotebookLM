/**
 * =============================================================================
 * File: comparison-format.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure display helpers for Comparison status and result payload.
 * Responsibilities:
 *   - Status labels; normalize result arrays; format timestamps
 * Dependencies:
 *   - types/comparisons
 * Public Exports:
 *   - statusLabel, formatComparisonDateTime, normalizeComparisonResult
 * Database/Table: N/A
 * Related Modules: features/comparisons/*
 * Important Notes: Keep pure for node smoke tests (no React).
 * =============================================================================
 */

import { normalizeContractComparison } from "@/features/comparisons/comparison-summary";
import type {
  Comparison,
  ComparisonResult,
  ComparisonStatus,
} from "@/types/comparisons";

export function statusLabel(status: ComparisonStatus): string {
  switch (status) {
    case "processing":
      return "Đang xử lý";
    case "completed":
      return "Hoàn thành";
    case "failed":
      return "Thất bại";
    default:
      return status;
  }
}

export function formatComparisonDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function normalizeComparisonResult(
  result: Comparison["result"],
): ComparisonResult {
  if (!result || typeof result !== "object") {
    return { similarities: [], differences: [] };
  }
  const similarities = Array.isArray(result.similarities)
    ? result.similarities.map((s) => String(s).trim()).filter(Boolean)
    : [];
  const differences = Array.isArray(result.differences)
    ? result.differences.map((s) => String(s).trim()).filter(Boolean)
    : [];
  const contract_comparison = normalizeContractComparison(
    result.contract_comparison,
  );
  return { similarities, differences, contract_comparison };
}
