/**
 * Node-side smoke checks for Chat UI pure helpers (no Jest/RTL yet).
 * Mirrors scripts/test-search-ui.mjs / test-content-location.mjs — logic is
 * re-implemented in plain JS here (no TS import) and must stay in sync with
 * features/chat/chat-format.ts and lib/chat.api.ts's dispatchFrame().
 * Run: node scripts/test-chat-ui.mjs
 */

function sessionTitleLabel(session) {
  const trimmed = (session.title ?? "").trim();
  return trimmed || "Cuộc trò chuyện mới";
}

function buildChatCitationHref(workspaceId, citation) {
  if (!citation.document_id) return null;
  return `/workspaces/${workspaceId}/documents/${citation.document_id}`;
}

function formatRelativeTime(isoDate, nowMs) {
  const target = new Date(isoDate).getTime();
  if (Number.isNaN(target)) return "";
  const diffSec = Math.floor((nowMs - target) / 1000);
  if (diffSec < 5) return "Vừa xong";
  if (diffSec < 60) return `${diffSec} giây trước`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} phút trước`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} giờ trước`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay} ngày trước`;
  return null; // falls back to toLocaleDateString in the real implementation
}

/** Mirrors dispatchFrame() in lib/chat.api.ts — same SSE frame contract. */
function parseFrame(frame) {
  const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
  if (!dataLine) return null;
  const jsonText = dataLine.slice("data:".length).trim();
  if (!jsonText) return null;
  try {
    return JSON.parse(jsonText);
  } catch {
    return null;
  }
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

// --- sessionTitleLabel -------------------------------------------------
assert(
  sessionTitleLabel({ title: null }) === "Cuộc trò chuyện mới",
  "Null title → fallback label",
);
assert(
  sessionTitleLabel({ title: "  " }) === "Cuộc trò chuyện mới",
  "Blank title → fallback label",
);
assert(
  sessionTitleLabel({ title: "Hỏi về hợp đồng" }) === "Hỏi về hợp đồng",
  "Real title is used as-is",
);

// --- buildChatCitationHref ----------------------------------------------
assert(
  buildChatCitationHref("ws-1", { document_id: "doc-1" }) ===
    "/workspaces/ws-1/documents/doc-1",
  "Citation with document_id → document deep-link (no chunk/page — not in contract)",
);
assert(
  buildChatCitationHref("ws-1", { document_id: null }) === null,
  "Citation without document_id → no link",
);

// --- formatRelativeTime ---------------------------------------------------
const now = Date.parse("2026-08-06T12:00:00Z");
assert(
  formatRelativeTime("2026-08-06T11:59:58Z", now) === "Vừa xong",
  "< 5s → Vừa xong",
);
assert(
  formatRelativeTime("2026-08-06T11:55:00Z", now) === "5 phút trước",
  "5 min ago → 5 phút trước",
);
assert(
  formatRelativeTime("2026-08-06T09:00:00Z", now) === "3 giờ trước",
  "3 hours ago → 3 giờ trước",
);

// --- SSE frame contract (event: {type}\ndata: {json}\n\n) -----------------
assert(
  parseFrame('event: token\ndata: {"type":"token","text":"Xin ch\\u00e0o"}').type ===
    "token",
  "token frame parses",
);
const citationsFrame = parseFrame(
  'event: citations\ndata: {"type":"citations","citations":[{"id":"c1"}]}',
);
assert(
  citationsFrame.type === "citations" && citationsFrame.citations.length === 1,
  "citations frame carries the citations array",
);
const generationFrame = parseFrame(
  'event: generation\ndata: {"type":"generation","generation":null,"message":{"id":"m1","content":"Hello"}}',
);
assert(
  generationFrame.type === "generation" && generationFrame.message.id === "m1",
  "generation frame carries the authoritative final message",
);
assert(parseFrame('event: done\ndata: {"type":"done"}').type === "done", "done frame parses");
const errorFrame = parseFrame(
  'event: error\ndata: {"type":"error","code":"pipeline_error","message":"Lỗi hệ thống"}',
);
assert(
  errorFrame.type === "error" && errorFrame.message === "Lỗi hệ thống",
  "error frame carries a user-facing message",
);
assert(parseFrame("garbage without data line") === null, "malformed frame → null (ignored)");

if (process.exitCode) {
  process.exit(process.exitCode);
}
console.log("All chat UI checks passed.");
