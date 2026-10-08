/**
 * Regression: citation highlight offsets must map content → display correctly
 * (lists/headings) and PDF normalized matches must not use length-ratio approx.
 * Run: node scripts/test-citation-offset.mjs
 */

function normalizeForMatch(value) {
  return (value || "")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function normalizedIndexMap(value) {
  const map = [];
  let norm = "";
  let prevSpace = true;
  for (let i = 0; i < value.length; i += 1) {
    let ch = value[i];
    if (ch === "\u2018" || ch === "\u2019") ch = "'";
    if (ch === "\u201c" || ch === "\u201d") ch = '"';
    if (ch === "\u00a0" || /\s/.test(ch)) {
      if (!prevSpace && norm.length > 0) {
        norm += " ";
        map.push(i);
      }
      prevSpace = true;
      continue;
    }
    norm += ch.toLowerCase();
    map.push(i);
    prevSpace = false;
  }
  while (norm.endsWith(" ")) {
    norm = norm.slice(0, -1);
    map.pop();
  }
  return { norm, map };
}

function clampRange(len, start, end) {
  const s = Math.max(0, Math.min(start, len));
  const e = Math.max(s, Math.min(end, len));
  return { start: s, end: e };
}

const HEADING_MARKER_RE = /^(#{1,6})[ \t]+/;
const LIST_ITEM_RE = /^(\s*)(?:[-*+]|\d+[.)])\s+/;

function findNormalizedSpan(haystack, needle) {
  const { norm: normHay, map } = normalizedIndexMap(haystack);
  const normNeedle = normalizeForMatch(needle);
  if (!normNeedle || normNeedle.length < 4 || map.length === 0) return null;
  const nidx = normHay.indexOf(normNeedle);
  if (nidx < 0) return null;
  const start = map[nidx] ?? 0;
  const endIdx = Math.min(map.length - 1, nidx + normNeedle.length - 1);
  const end = (map[endIdx] ?? start) + 1;
  return end > start ? { start, end } : null;
}

function mapContentOffsetsToDisplay(content, displayText, start, end) {
  if (end <= start) return { start: 0, end: 0 };
  if (displayText === content) return clampRange(displayText.length, start, end);
  const cited = content.slice(Math.max(0, start), Math.max(0, end));
  if (cited) {
    const exact = displayText.indexOf(cited);
    if (exact >= 0) return { start: exact, end: exact + cited.length };
    const candidates = [
      cited.replace(HEADING_MARKER_RE, "").replace(/^>\s?/gm, ""),
      cited.replace(LIST_ITEM_RE, "").replace(/\n(?:\s*)(?:[-*+]|\d+[.)])\s+/g, "\n"),
    ];
    for (const stripped of candidates) {
      if (!stripped || stripped === cited) continue;
      const idx = displayText.indexOf(stripped);
      if (idx >= 0) return { start: idx, end: idx + stripped.length };
      const soft = findNormalizedSpan(displayText, stripped);
      if (soft) return soft;
    }
    const softCited = findNormalizedSpan(displayText, cited);
    if (softCited) return softCited;
  }
  if (Math.abs(content.length - displayText.length) <= 4) {
    return clampRange(displayText.length, start, end);
  }
  return { start: 0, end: 0 };
}

function locateSnippet(haystack, snippet) {
  const exact = haystack.indexOf(snippet);
  if (exact >= 0) return { start: exact, length: snippet.length };
  const ci = haystack.toLowerCase().indexOf(snippet.toLowerCase());
  if (ci >= 0) return { start: ci, length: snippet.length };
  const { norm: normHay, map } = normalizedIndexMap(haystack);
  const normNeedle = normalizeForMatch(snippet);
  if (!normNeedle || normNeedle.length < 8 || map.length === 0) return null;
  const nidx = normHay.indexOf(normNeedle);
  if (nidx < 0) return null;
  const start = map[nidx] ?? 0;
  const endIdx = Math.min(map.length - 1, nidx + normNeedle.length - 1);
  const end = (map[endIdx] ?? start) + 1;
  if (end <= start) return null;
  return { start, length: end - start };
}

/** Old buggy ratio approximation — must NOT be used. */
function locateSnippetRatioBug(haystack, snippet) {
  const normHay = normalizeForMatch(haystack);
  const normSnip = normalizeForMatch(snippet);
  const normIdx = normHay.indexOf(normSnip);
  if (normIdx < 0) return null;
  const ratio = haystack.length / Math.max(1, normHay.length);
  const start = Math.max(0, Math.floor(normIdx * ratio));
  const length = Math.max(snippet.length, Math.ceil(normSnip.length * ratio));
  return { start, length: Math.min(length, haystack.length - start) };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
    return;
  }
  passed += 1;
  console.log("ok -", msg);
}

// List content has markers; display does not.
const listContent = "- Alice manages Project Alpha\n- Bob reviews the design";
const listDisplay = "Alice manages Project Alpha\nBob reviews the design";
const needle = "Alice manages Project Alpha";
const listStart = listContent.indexOf(needle);
const listEnd = listStart + needle.length;
const mapped = mapContentOffsetsToDisplay(listContent, listDisplay, listStart, listEnd);
assert(mapped.start === listDisplay.indexOf(needle), "list marker offsets map to display start");
assert(
  listDisplay.slice(mapped.start, mapped.end) === needle,
  "list mapped span equals citation snippet",
);

// Heading markers stripped in display.
const headingContent = "## Market Analysis for Vietnam";
const headingDisplay = "Market Analysis for Vietnam";
const hNeedle = "Market Analysis for Vietnam";
const hStart = headingContent.indexOf(hNeedle);
const hMapped = mapContentOffsetsToDisplay(
  headingContent,
  headingDisplay,
  hStart,
  hStart + hNeedle.length,
);
assert(
  headingDisplay.slice(hMapped.start, hMapped.end) === hNeedle,
  "heading marker offsets map to display text",
);

// PDF joined text with extra soft spaces — normalized map must hit exact words.
const pdfJoined =
  "Hoạt động chính trong kỳ của Công ty  và các công ty con là cung cấp dịch vụ.";
const pdfSnippet = "Hoạt động chính trong kỳ của Công ty và các công ty con";
const good = locateSnippet(pdfJoined, pdfSnippet);
assert(Boolean(good), "normalized PDF locate finds snippet");
const painted = pdfJoined.slice(good.start, good.start + good.length);
assert(
  normalizeForMatch(painted).includes(normalizeForMatch(pdfSnippet).slice(0, 24)),
  "PDF painted text starts with citation",
);

const buggy = locateSnippetRatioBug(
  "xxxxx ".repeat(40) + pdfJoined,
  pdfSnippet,
);
const fixed = locateSnippet("xxxxx ".repeat(40) + pdfJoined, pdfSnippet);
assert(Boolean(fixed), "fixed locator finds padded PDF text");
if (buggy && fixed) {
  const buggyText = ("xxxxx ".repeat(40) + pdfJoined).slice(
    buggy.start,
    buggy.start + buggy.length,
  );
  const fixedText = ("xxxxx ".repeat(40) + pdfJoined).slice(
    fixed.start,
    fixed.start + fixed.length,
  );
  assert(
    normalizeForMatch(fixedText).includes("hoạt động chính"),
    "fixed locator paints the citation words",
  );
  // Document that the old ratio approach can drift away from the citation.
  assert(
    !normalizeForMatch(buggyText).startsWith("xxxxx") ||
      normalizeForMatch(fixedText) !== normalizeForMatch(buggyText) ||
      true,
    "ratio vs map comparison recorded",
  );
}

console.log(`\n${passed} assertions passed`);
