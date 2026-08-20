/**
 * Node-side smoke checks for Summary UI pure helpers (no Jest/RTL yet).
 * Mirrors features/summaries/summary-format.ts — keep in sync manually.
 * Run: node scripts/test-summary-ui.mjs
 */

function styleLabel(style) {
  const map = {
    short: "Tóm tắt ngắn",
    detailed: "Tóm tắt chi tiết",
    by_topic: "Theo chủ đề",
    bullet_points: "Gạch đầu dòng",
  };
  return map[style] ?? style;
}

function isOldVersion(summary, currentVersionId) {
  if (!currentVersionId) return false;
  return summary.source_version_id !== currentVersionId;
}

function getCurrentSummary(summaries, currentVersionId, selectedStyle, selectedLanguage = "vi") {
  if (!currentVersionId) return null;
  const matches = summaries.filter(
    (s) =>
      s.status === "completed" &&
      s.style === selectedStyle &&
      (s.target_language ?? "vi") === selectedLanguage &&
      s.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

function buildCopyText(summary) {
  if (summary.style === "by_topic" && summary.sections && summary.sections.length > 0) {
    return summary.sections.map((s) => `${s.title}\n${s.content}`.trim()).join("\n\n");
  }
  return (summary.content ?? "").trim();
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

// --- style labels ----------------------------------------------------------
assert(styleLabel("short") === "Tóm tắt ngắn", "short label");
assert(styleLabel("detailed") === "Tóm tắt chi tiết", "detailed label");
assert(styleLabel("by_topic") === "Theo chủ đề", "by_topic label");
assert(styleLabel("bullet_points") === "Gạch đầu dòng", "bullet_points label");

// --- current-version selection --------------------------------------------
const V1 = "v1";
const V2 = "v2";
const summaries = [
  {
    id: "a",
    style: "short",
    status: "completed",
    source_version_id: V1,
    target_language: "vi",
    created_at: "2026-08-01T10:00:00Z",
    content: "old short",
    sections: null,
  },
  {
    id: "b",
    style: "short",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-02T10:00:00Z",
    content: "new short",
    sections: null,
  },
  {
    id: "c",
    style: "detailed",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-03T10:00:00Z",
    content: "detailed v2",
    sections: null,
  },
  {
    id: "d",
    style: "short",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-04T10:00:00Z",
    content: "newer short",
    sections: null,
  },
  {
    id: "e",
    style: "short",
    status: "completed",
    source_version_id: V2,
    target_language: "en",
    created_at: "2026-08-05T10:00:00Z",
    content: "english short [1]",
    sections: null,
  },
];

const current = getCurrentSummary(summaries, V2, "short");
assert(current && current.id === "d", "Picks newest completed short for V2 (vi default)");
assert(
  getCurrentSummary(summaries, V2, "short", "en")?.id === "e",
  "Picks English short separately from Vietnamese",
);
assert(
  getCurrentSummary(summaries, V2, "short", "en")?.content.includes("[1]"),
  "Citation marker preserved in English selection",
);
assert(
  getCurrentSummary(summaries, V2, "detailed")?.id === "c",
  "Picks detailed for V2",
);
assert(
  getCurrentSummary(summaries, V2, "bullet_points") === null,
  "Missing style on current version → null (no auto old-version)",
);
assert(
  getCurrentSummary(summaries, V2, "by_topic") === null,
  "Missing by_topic on V2 → null",
);
assert(
  getCurrentSummary(summaries, V2, "detailed", "en") === null,
  "No English detailed → null (does not show Vietnamese under English)",
);

// Race: older VI response must not replace newer EN selection key
const selectedLanguage = "en";
const displayed = getCurrentSummary(summaries, V2, "short", selectedLanguage);
assert(displayed?.id === "e", "Race-safe selection uses selected language key");
assert(displayed?.target_language === "en", "generatedLanguage matches selectedLanguage");


// --- old-version badge -----------------------------------------------------
assert(isOldVersion({ source_version_id: V1 }, V2) === true, "V1 is old vs V2");
assert(isOldVersion({ source_version_id: V2 }, V2) === false, "V2 is current");

// --- by_topic copy uses structured sections --------------------------------
const topicSummary = {
  style: "by_topic",
  content: null,
  sections: [
    { title: "Tài chính", content: "Doanh thu tăng." },
    { title: "Rủi ro", content: "Cần theo dõi." },
  ],
};
assert(
  buildCopyText(topicSummary) === "Tài chính\nDoanh thu tăng.\n\nRủi ro\nCần theo dõi.",
  "by_topic copy joins backend sections",
);

const bullet = {
  style: "bullet_points",
  content: "- Một\n- Hai\n- Ba",
  sections: null,
};
assert(buildCopyText(bullet) === "- Một\n- Hai\n- Ba", "bullet_points copies markdown list");

if (process.exitCode) {
  console.error("\nsummary-ui tests failed");
} else {
  console.log("\nAll summary-ui checks passed");
}
