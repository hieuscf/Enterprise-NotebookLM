/**
 * =============================================================================
 * File: admin-pipeline.ts
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Pure helpers for `/admin/pipeline` — status labels, stage progress,
 *          duration/relative time, overview rollups, metadata extraction.
 * Responsibilities:
 *   - Map pipeline status → English label + badge classes
 *   - Derive current stage / progress markers from pipeline_stage_logs
 *   - Format durations (including in-progress runs) and relative timestamps
 *   - Extract readable OCR/cleaning metrics from stage metadata when present
 * Dependencies:
 *   - lib/pipeline-stages (PIPELINE_STAGE_ORDER), admin-format.formatLatency
 * Public Exports:
 *   - PIPELINE_STATUS_LABEL, PIPELINE_STATUS_BADGE_CLASS, STAGE_SHORT_LABEL
 *   - derivePipelineOverview, pipelineRunDurationLabel, formatRelativeAgo
 *   - stageProgressForRun, failedStageOf, extractOcrMetrics, formatFullTs
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: features/admin/AdminPipeline*
 * Important Notes: Never invent progress % or fake metrics — only derive from
 *   returned stage logs / timestamps.
 * =============================================================================
 */

import { formatLatency } from "@/features/admin/admin-format";
import { PIPELINE_STAGE_ORDER } from "@/lib/pipeline-stages";
import type {
  FileType,
  PipelineRun,
  PipelineStageLog,
  PipelineStageName,
  PipelineStageNameV3,
  PipelineStatus,
} from "@/types/documents";

export const PIPELINE_STATUS_LABEL: Record<PipelineStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export const PIPELINE_STATUS_BADGE_CLASS: Record<PipelineStatus, string> = {
  pending: "bg-elevated text-tertiary",
  running: "bg-info/10 text-info",
  completed: "bg-success/10 text-success",
  failed: "bg-danger-soft text-danger",
};

/** Compact English labels for dense progress strips. */
export const STAGE_SHORT_LABEL: Record<PipelineStageNameV3, string> = {
  preview_generation: "Preview",
  document_understanding: "Layout",
  cleaning_normalize: "Clean",
  hierarchical_chunking: "Chunk",
  embedding: "Embed",
  graph_extraction: "Graph",
  indexing: "Index",
};

export const STAGE_FULL_LABEL: Record<PipelineStageNameV3, string> = {
  preview_generation: "Preview Generation",
  document_understanding: "Document Understanding",
  cleaning_normalize: "OCR & Cleaning",
  hierarchical_chunking: "Chunking",
  embedding: "Embedding",
  graph_extraction: "Graph Extraction",
  indexing: "Indexing",
};

/** Legacy stage labels retained for historical runs. */
export const STAGE_LABEL_ANY: Record<PipelineStageName, string> = {
  ...STAGE_FULL_LABEL,
  ocr_cleaning: "OCR & Cleaning",
  chunking: "Chunking",
};

export type StageProgressMarker = "completed" | "running" | "failed" | "pending" | "skipped";

export type StageProgressItem = {
  stage: PipelineStageNameV3;
  label: string;
  shortLabel: string;
  marker: StageProgressMarker;
  log: PipelineStageLog | null;
};

export type PipelineOverviewStats = {
  running: number;
  completed: number;
  failed: number;
  pending: number;
  total: number;
  avgDurationMs: number | null;
  sampleCapped: boolean;
};

export type OcrMetrics = {
  page_count?: number;
  char_count?: number;
  segment_count?: number;
  heading_count?: number;
  table_count?: number;
};

export function documentLabel(run: PipelineRun): string {
  const title = run.document_title?.trim();
  if (title) return title;
  return `Version ${run.document_version_id.slice(0, 8)}`;
}

export function versionLabel(run: PipelineRun): string {
  if (run.version_number != null) return `v${run.version_number}`;
  return run.document_version_id.slice(0, 8);
}

export function fileTypeBadge(run: PipelineRun): FileType | null {
  return run.file_type ?? null;
}

export function formatFullTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatRelativeAgo(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "—";
  try {
    const date = new Date(iso);
    const diffMs = now.getTime() - date.getTime();
    if (!Number.isFinite(diffMs)) return iso;
    const abs = Math.abs(diffMs);
    if (abs < 45_000) return "just now";
    if (abs < 3_600_000) {
      const mins = Math.max(1, Math.round(abs / 60_000));
      return `${mins}m ago`;
    }
    if (abs < 86_400_000) {
      const hours = Math.max(1, Math.round(abs / 3_600_000));
      return `${hours}h ago`;
    }
    const days = Math.max(1, Math.round(abs / 86_400_000));
    return `${days}d ago`;
  } catch {
    return iso;
  }
}

export function runDurationMs(run: PipelineRun, now = Date.now()): number | null {
  if (!run.started_at) return null;
  const start = new Date(run.started_at).getTime();
  if (!Number.isFinite(start)) return null;
  const end = run.completed_at ? new Date(run.completed_at).getTime() : now;
  if (!Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}

export function pipelineRunDurationLabel(run: PipelineRun, now = Date.now()): string {
  const ms = runDurationMs(run, now);
  if (ms === null) return "—";
  const base = formatLatency(ms);
  if (run.status === "running" || (run.status === "pending" && !run.completed_at)) {
    return `${base} · running`;
  }
  return base;
}

export function derivePipelineOverview(
  runs: PipelineRun[],
  sampleCapped: boolean,
  now = Date.now(),
): PipelineOverviewStats {
  const stats: PipelineOverviewStats = {
    running: 0,
    completed: 0,
    failed: 0,
    pending: 0,
    total: runs.length,
    avgDurationMs: null,
    sampleCapped,
  };
  const completedDurations: number[] = [];
  for (const run of runs) {
    stats[run.status] += 1;
    if (run.status === "completed") {
      const ms = runDurationMs(run, now);
      if (ms !== null) completedDurations.push(ms);
    }
  }
  if (completedDurations.length > 0) {
    stats.avgDurationMs =
      completedDurations.reduce((a, b) => a + b, 0) / completedDurations.length;
  }
  return stats;
}

function logByStage(stages: PipelineStageLog[]): Map<PipelineStageName, PipelineStageLog> {
  const map = new Map<PipelineStageName, PipelineStageLog>();
  for (const log of stages) {
    map.set(log.stage, log);
  }
  return map;
}

/**
 * Build stage progress from pipeline_stage_logs — never guess from wall-clock.
 * Stages without a log remain pending (or skipped after a failed earlier stage).
 */
export function stageProgressForRun(run: PipelineRun): StageProgressItem[] {
  const byStage = logByStage(run.stages);
  let seenFailed = false;
  return PIPELINE_STAGE_ORDER.map((stage) => {
    const log = byStage.get(stage) ?? null;
    let marker: StageProgressMarker = "pending";
    if (log) {
      marker = log.status;
      if (log.status === "failed") seenFailed = true;
    } else if (seenFailed || run.status === "failed") {
      marker = "skipped";
    } else if (run.status === "completed") {
      // Completed run without a log for this stage — treat as pending/missing.
      marker = "pending";
    }
    return {
      stage,
      label: STAGE_FULL_LABEL[stage],
      shortLabel: STAGE_SHORT_LABEL[stage],
      marker,
      log,
    };
  });
}

export function currentStageOf(run: PipelineRun): StageProgressItem | null {
  const progress = stageProgressForRun(run);
  const running = progress.find((p) => p.marker === "running");
  if (running) return running;
  const failed = progress.find((p) => p.marker === "failed");
  if (failed) return failed;
  return null;
}

export function failedStageOf(run: PipelineRun): PipelineStageLog | null {
  return run.stages.find((s) => s.status === "failed") ?? null;
}

export function extractOcrMetrics(metadata: Record<string, unknown> | null | undefined): OcrMetrics {
  if (!metadata || typeof metadata !== "object") return {};
  const keys = [
    "page_count",
    "char_count",
    "segment_count",
    "heading_count",
    "table_count",
  ] as const;
  const out: OcrMetrics = {};
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
    }
  }
  return out;
}

export function isOcrLikeStage(stage: PipelineStageName): boolean {
  return (
    stage === "ocr_cleaning" ||
    stage === "cleaning_normalize" ||
    stage === "document_understanding"
  );
}

export function matchesPipelineSearch(run: PipelineRun, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystacks = [
    run.id,
    run.document_version_id,
    run.document_id ?? "",
    run.document_title ?? "",
  ];
  return haystacks.some((h) => h.toLowerCase().includes(q));
}

export function formatCount(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}
