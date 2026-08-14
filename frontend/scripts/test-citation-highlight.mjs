/**
 * Node smoke tests for citation snippet → PDF text-layer highlight helpers.
 * Run: node scripts/test-citation-highlight.mjs
 */

function normalizeSnippet(value) {
  return (value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function matchSnippetInText(haystack, snippet) {
  if (!haystack || !snippet) return null;
  const exact = haystack.indexOf(snippet);
  if (exact >= 0) return { index: exact, length: snippet.length };
  const ci = haystack.toLowerCase().indexOf(snippet.toLowerCase());
  if (ci >= 0) return { index: ci, length: snippet.length };
  const normHay = normalizeSnippet(haystack);
  const normSnip = normalizeSnippet(snippet);
  if (!normSnip) return null;
  const normIdx = normHay.indexOf(normSnip);
  if (normIdx < 0) return null;
  return { index: Math.min(normIdx, Math.max(0, haystack.length - 1)), length: snippet.length };
}

function findChunkForSnippet(chunks, snippet) {
  if (!snippet.trim() || chunks.length === 0) return null;
  for (const chunk of chunks) {
    if (matchSnippetInText(chunk.content || "", snippet)) return chunk;
  }
  return null;
}

/** Minimal mirror of findSnippetRectsInTextContent for regression. */
function findSnippetRectsInTextContent(textContent, snippet, pageWidth, pageHeight) {
  if (!textContent?.items?.length || !snippet.trim()) return [];
  let joined = "";
  const spans = [];
  for (const item of textContent.items) {
    const str = item.str || "";
    if (!str) continue;
    const t = item.transform;
    const tx = t[4];
    const ty = t[5];
    const fontHeight = Math.abs(t[3] || 10);
    const width = item.width || str.length * fontHeight * 0.5;
    const left = tx;
    const top = pageHeight - ty - fontHeight;
    const charStart = joined.length;
    joined += str;
    spans.push({
      charStart,
      charEnd: joined.length,
      left,
      top,
      right: left + width,
      bottom: top + fontHeight,
    });
    joined += " ";
  }
  const idx = joined.indexOf(snippet);
  if (idx < 0) return [];
  const hit = spans.filter((s) => s.charEnd > idx && s.charStart < idx + snippet.length);
  return hit.map((s) => ({
    left: (s.left / pageWidth) * 100,
    top: (s.top / pageHeight) * 100,
    width: ((s.right - s.left) / pageWidth) * 100,
    height: ((s.bottom - s.top) / pageHeight) * 100,
  }));
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

const chunk =
  "A. Tổng quan\nHoạt động chính trong kỳ của Công ty và các công ty con là cung cấp dịch vụ.\nKết quả kinh doanh";
const citation =
  "Hoạt động chính trong kỳ của Công ty và các công ty con";

assert(chunk !== citation, "chunk.content != citation.text_snippet (sub-span)");
assert(
  findChunkForSnippet([{ id: "c1", content: chunk }], citation)?.id === "c1",
  "findChunkForSnippet locates parent chunk",
);
assert(
  matchSnippetInText(chunk, citation)?.index === chunk.indexOf(citation),
  "matchSnippetInText finds exact sub-span offset",
);

const pageW = 600;
const pageH = 800;
const textContent = {
  items: [
    { str: "Hoạt động chính trong kỳ của Công ty", transform: [1, 0, 0, 12, 100, 700], width: 280 },
    { str: "và các công ty con", transform: [1, 0, 0, 12, 100, 680], width: 140 },
  ],
};
const rects = findSnippetRectsInTextContent(
  textContent,
  "Hoạt động chính trong kỳ của Công ty và các công ty con",
  pageW,
  pageH,
);
assert(rects.length >= 1, "multi-line snippet yields ≥1 highlight rect");
assert(
  rects.every((r) => r.width < 90 && r.height < 20),
  "rects are tight (not full-page approximate band)",
);

console.log(`\n${passed} assertions passed`);
