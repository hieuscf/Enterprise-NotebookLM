# =============================================================================
# File: constants.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Shared OCR constants, block-type alias, and precompiled regexes.
# Responsibilities:
#   - Define BlockType and tuning thresholds (no magic numbers in logic)
#   - Hold Unicode translation tables and compiled cleaning/detection regexes
# Dependencies:
#   - re, typing
# Public Exports:
#   - BlockType, HEADER_FOOTER_*, SOFT/HARD_BREAK_*, HEADING_*, TABLE_*,
#     SPAN_SPACE_GAP_PT, XLSX_MAX_HEADER_SCAN, MEDIAN_SAMPLE_MAX,
#     ZERO_WIDTH_CHARS, QUOTE_TRANSLATION, DASH_TRANSLATION, BULLET_CHARS,
#     _WS_RE, _BLANK_RE, _CTRL_RE, _MULTI_SPACE_RE, _PAGE_NUM_RE,
#     _STANDALONE_PAGE_RE, _DATE_RE, _CONFIDENTIAL_RE, _NUMBERED_HEADING_RE,
#     _ALL_CAPS_WORD_RE, _LIST_ITEM_RE, _CAPTION_RE, _ROW_LABEL_RE,
#     _TABLE_KV_RE, _SECTION_MARKER_RE
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Pure constants — no I/O, no side effects.
# =============================================================================

from __future__ import annotations

import re
from typing import Literal

BlockType = Literal[
    "paragraph",
    "heading",
    "table",
    "list",
    "caption",
    "title",
    "subtitle",
    "notes",
]

HEADER_FOOTER_MIN_PAGES = 3
HEADER_FOOTER_THRESHOLD = 0.6
HEADER_FOOTER_MIN_LEN = 4
HEADER_FOOTER_MAX_LEN = 120
HEADER_FOOTER_FUZZY_RATIO = 0.88
HEADER_FOOTER_EDGE_LINES = 2

SOFT_BREAK_MAX_GAP_RATIO = 1.35
HARD_BREAK_MIN_GAP_RATIO = 1.75
HEADING_SIZE_RATIO = 1.15
HEADING_MAX_CHARS = 200
TABLE_MIN_ROWS = 2
TABLE_MIN_COLS = 2
SPAN_SPACE_GAP_PT = 1.5
XLSX_MAX_HEADER_SCAN = 20
MEDIAN_SAMPLE_MAX = 5000

ZERO_WIDTH_CHARS = (
    "\u200b"  # zero-width space
    "\u200c"  # zero-width non-joiner
    "\u200d"  # zero-width joiner
    "\ufeff"  # BOM / zero-width no-break
    "\u2060"  # word joiner
)

QUOTE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u00ab": '"',
        "\u00bb": '"',
    }
)

DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)

BULLET_CHARS = frozenset("•●○◆▪▸►‣·∙■□–-*")

_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MULTI_SPACE_RE = re.compile(r" {2,}")
_PAGE_NUM_RE = re.compile(
    r"^(?:page|trang|p\.?)\s*\d+(?:\s*(?:of|/|trên)\s*\d+)?$",
    re.IGNORECASE,
)
_STANDALONE_PAGE_RE = re.compile(r"^\d{1,4}$")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_CONFIDENTIAL_RE = re.compile(
    r"\b(?:confidential|internal\s+use\s+only|proprietary|draft)\b",
    re.IGNORECASE,
)
_NUMBERED_HEADING_RE = re.compile(
    r"^(?:"
    r"(?:chapter|section|part|article|appendix)\s+[\dIVXLCDM]+"
    r"|[\dIVXLCDM]+(?:\.\d+){0,4}\.?"
    r")(?:\s+\S.+)?$",
    re.IGNORECASE,
)
_ALL_CAPS_WORD_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s\-:,.&/()]{2,}$")
_LIST_ITEM_RE = re.compile(
    r"^(?:"
    r"[•●○◆▪▸►‣·∙■□]"
    r"|[-*–—]"
    r"|\(?\d{1,3}[.)]"
    r"|[a-zA-Z][.)]"
    r")\s+\S"
)
_CAPTION_RE = re.compile(
    r"^(?:figure|fig\.|table|tbl\.|biểu\s+đồ|bảng)\s*\d+",
    re.IGNORECASE,
)
_ROW_LABEL_RE = re.compile(r"^Row\s+(\d+)$", re.IGNORECASE)
_TABLE_KV_RE = re.compile(r"^(.+?)\s*(?:=\s*|:\s+)(.+)$")
_SECTION_MARKER_RE = re.compile(r"^\d{1,3}\.$")
