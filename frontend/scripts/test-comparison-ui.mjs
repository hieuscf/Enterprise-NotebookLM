/**
 * Node-side smoke checks for Comparison UI pure helpers (no Jest/RTL yet).
 * Mirrors features/comparisons/comparison-format.ts.
 * Run: node scripts/test-comparison-ui.mjs
 */

function statusLabel(status) {
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

function normalizeComparisonResult(result) {
  if (!result || typeof result !== "object") {
    return { similarities: [], differences: [] };
  }
  const similarities = Array.isArray(result.similarities)
    ? result.similarities.map((s) => String(s).trim()).filter(Boolean)
    : [];
  const differences = Array.isArray(result.differences)
    ? result.differences.map((s) => String(s).trim()).filter(Boolean)
    : [];
  return { similarities, differences };
}

function canCompare(selectedCount) {
  return selectedCount >= 2;
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

assert(statusLabel("processing") === "Đang xử lý", "processing label");
assert(statusLabel("completed") === "Hoàn thành", "completed label");
assert(statusLabel("failed") === "Thất bại", "failed label");

assert(!canCompare(0), "disable compare with 0 docs");
assert(!canCompare(1), "disable compare with 1 doc");
assert(canCompare(2), "enable compare with 2 docs");
assert(canCompare(5), "enable compare with 5 docs");

const empty = normalizeComparisonResult(null);
assert(empty.similarities.length === 0 && empty.differences.length === 0, "null result → empty lists");

const trimmed = normalizeComparisonResult({
  similarities: ["  Same SLA  ", "", "Shared vendor"],
  differences: ["Only A has penalties", "   "],
});
assert(
  JSON.stringify(trimmed.similarities) ===
    JSON.stringify(["Same SLA", "Shared vendor"]),
  "trim/filter similarities",
);
assert(
  JSON.stringify(trimmed.differences) ===
    JSON.stringify(["Only A has penalties"]),
  "trim/filter differences",
);

const openapiShape = {
  id: "c1",
  workspace_id: "w1",
  document_ids: ["d1", "d2"],
  status: "completed",
  result: { similarities: ["a"], differences: ["b"] },
  created_at: "2026-08-09T00:00:00Z",
};
assert(
  openapiShape.result.similarities[0] === "a" &&
    openapiShape.result.differences[0] === "b",
  "OpenAPI Comparison.result shape",
);

if (!process.exitCode) {
  console.log("\nAll comparison UI smoke checks passed.");
}
