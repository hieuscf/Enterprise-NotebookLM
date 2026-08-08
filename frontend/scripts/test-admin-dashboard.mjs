/**
 * Node-side smoke checks for Admin Dashboard pure helpers (no Jest/RTL yet).
 * Mirrors features/admin/admin-format.ts and hooks/useAdminCostSummary.ts —
 * keep in sync manually.
 * Run: node scripts/test-admin-dashboard.mjs
 */

function deltaOf(curr, prev) {
  if (prev === 0) return curr === 0 ? 0 : null;
  return (curr - prev) / prev;
}

function formatPercent(ratio, digits = 0) {
  if (!Number.isFinite(ratio)) return "—";
  return `${(ratio * 100).toFixed(digits)}%`;
}

function formatLatency(ms) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms >= 10000 ? 0 : 1)}s`;
}

const PIPELINE_STAGE_ORDER = [
  "document_understanding",
  "cleaning_normalize",
  "hierarchical_chunking",
  "embedding",
  "graph_extraction",
  "indexing",
];

function derivePipelineHealth(runs) {
  const byStatus = { pending: 0, running: 0, completed: 0, failed: 0 };
  for (const run of runs) byStatus[run.status] += 1;

  const stageTotals = new Map();
  for (const run of runs) {
    for (const stage of run.stages) {
      const entry = stageTotals.get(stage.stage) ?? { completed: 0, total: 0 };
      entry.total += 1;
      if (stage.status === "completed") entry.completed += 1;
      stageTotals.set(stage.stage, entry);
    }
  }

  const stageCompletion = PIPELINE_STAGE_ORDER.map((stage) => {
    const entry = stageTotals.get(stage);
    const total = entry?.total ?? 0;
    const completed = entry?.completed ?? 0;
    return { stage, completed, total, ratio: total > 0 ? completed / total : null };
  });

  return { total: runs.length, byStatus, stageCompletion };
}

function computeRangeWindows(days, now) {
  const to = new Date(now);
  const from = new Date(now);
  from.setDate(from.getDate() - (days - 1));
  const previousTo = new Date(from);
  previousTo.setDate(previousTo.getDate() - 1);
  const previousFrom = new Date(previousTo);
  previousFrom.setDate(previousFrom.getDate() - (days - 1));
  const fmt = (d) => d.toISOString().slice(0, 10);
  return {
    from: fmt(from),
    to: fmt(to),
    previousFrom: fmt(previousFrom),
    previousTo: fmt(previousTo),
  };
}

function redactQueryText(text, max = 44) {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max)}…`;
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

// deltaOf
assert(deltaOf(120, 100) === 0.2, "deltaOf: +20% growth");
assert(deltaOf(80, 100) === -0.2, "deltaOf: -20% drop");
assert(deltaOf(0, 0) === 0, "deltaOf: 0 → 0 is flat, not null");
assert(deltaOf(5, 0) === null, "deltaOf: no baseline (prev=0, curr>0) is undefined trend");

// formatPercent / formatLatency
assert(formatPercent(0.314, 1) === "31.4%", "formatPercent rounds to given digits");
assert(formatPercent(1) === "100%", "formatPercent handles 100%");
assert(formatLatency(42) === "42ms", "formatLatency: sub-second in ms");
assert(formatLatency(2400) === "2.4s", "formatLatency: seconds with 1 decimal under 10s");
assert(formatLatency(15000) === "15s", "formatLatency: whole seconds at/over 10s");
assert(formatLatency(null) === "—", "formatLatency: null → em dash");

// derivePipelineHealth
const runs = [
  {
    status: "completed",
    stages: [
      { stage: "document_understanding", status: "completed" },
      { stage: "embedding", status: "completed" },
    ],
  },
  {
    status: "failed",
    stages: [
      { stage: "document_understanding", status: "completed" },
      { stage: "embedding", status: "failed" },
    ],
  },
  { status: "running", stages: [{ stage: "document_understanding", status: "running" }] },
];
const health = derivePipelineHealth(runs);
assert(health.total === 3, "derivePipelineHealth: total run count");
assert(health.byStatus.completed === 1 && health.byStatus.failed === 1 && health.byStatus.running === 1, "derivePipelineHealth: status counts");
const embeddingStage = health.stageCompletion.find((s) => s.stage === "embedding");
assert(embeddingStage.ratio === 0.5, "derivePipelineHealth: embedding stage 1/2 completed = 50%");
const graphStage = health.stageCompletion.find((s) => s.stage === "graph_extraction");
assert(graphStage.ratio === null, "derivePipelineHealth: stage never encountered → ratio null (not 0%)");

// computeRangeWindows — 7-day window ending 2026-08-09 (fixed for determinism)
const win = computeRangeWindows(7, new Date("2026-08-09T00:00:00.000Z"));
assert(win.from === "2026-08-03" && win.to === "2026-08-09", "computeRangeWindows: current 7-day window");
assert(win.previousFrom === "2026-07-27" && win.previousTo === "2026-08-02", "computeRangeWindows: equal-length previous window, no overlap/gap");

// redactQueryText — never expose full sensitive query text on the dashboard
const long = "a".repeat(80);
assert(redactQueryText(long).length === 45, "redactQueryText: truncates long query to 44 chars + ellipsis");
assert(redactQueryText("short query") === "short query", "redactQueryText: leaves short text untouched");

process.exit(process.exitCode ?? 0);
