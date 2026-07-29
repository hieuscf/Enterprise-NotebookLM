# =============================================================================
# File: test_markdown_cleaning.py
# Module/Service: Pipeline Worker — Cleaning & Normalize ([AI])
# Layer: Service
# Purpose: Unit tests for rule-based Markdown cleaning pure functions.
# Responsibilities:
#   - Verify header/footer, watermark, whitespace, table normalization
#   - Ensure heading structure survives cleaning
# Dependencies:
#   - pytest, app.ai.markdown_cleaning
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.ai.markdown_cleaning, app.workers.stages.cleaning_normalize
# Important Notes: No MinIO/DB — pure function tests only.
# =============================================================================

from __future__ import annotations

from app.ai.markdown_cleaning import (
    clean_markdown,
    fix_broken_encoding,
    normalize_markdown_tables,
    normalize_whitespace,
    remove_repeated_headers_footers,
    remove_watermarks_and_page_numbers,
)

SAMPLE_WITH_NOISE = """Company Report — CONFIDENTIAL

# 1. Giới thiệu

Đoạn mở đầu về hệ thống.

Footer Line 2024
1

## 1.1 Mục tiêu

Nội dung mục tiêu.

Footer Line 2024
2

| Chỉ số | Giá trị |
| Độ chính xác | 92% |

Footer Line 2024
3

# 2. Kết luận

Tổng kết.
Footer Line 2024
"""


def test_remove_repeated_headers_footers_drops_frequent_short_lines() -> None:
    text = "\n".join(
        [
            "Header Noise",
            "# Real Title",
            "Body one",
            "Header Noise",
            "Body two",
            "Header Noise",
        ]
    )

    cleaned = remove_repeated_headers_footers(text, min_repeat_count=3)

    assert "Header Noise" not in cleaned
    assert "# Real Title" in cleaned
    assert "Body one" in cleaned


def test_remove_repeated_headers_footers_keeps_headings() -> None:
    text = "# Title\n# Title\n# Title\n\nParagraph"
    cleaned = remove_repeated_headers_footers(text, min_repeat_count=2)
    assert cleaned.count("# Title") == 3


def test_remove_watermarks_and_page_numbers() -> None:
    text = "\n".join(
        [
            "CONFIDENTIAL",
            "# Section",
            "Content here",
            "42",
            "Page 7",
            "Trang 12",
            "- 3 -",
            "Keep this paragraph",
        ]
    )

    cleaned = remove_watermarks_and_page_numbers(text)

    assert "CONFIDENTIAL" not in cleaned
    assert "42" not in cleaned.splitlines()
    assert "Page 7" not in cleaned
    assert "Trang 12" not in cleaned
    assert "- 3 -" not in cleaned
    assert "# Section" in cleaned
    assert "Keep this paragraph" in cleaned


def test_normalize_whitespace_collapses_blank_lines_and_spaces() -> None:
    text = "# Heading  \n\n\n\nPara   with   spaces  \n\n\n\nNext"
    cleaned = normalize_whitespace(text)

    assert cleaned == "# Heading\n\nPara with spaces\n\nNext"


def test_fix_broken_encoding_strips_zero_width_and_nbsp() -> None:
    text = "Hello\u200bWorld\u00a0!"
    assert fix_broken_encoding(text) == "HelloWorld !"


def test_normalize_markdown_tables_inserts_delimiter_row() -> None:
    text = "| A | B |\n| one | two |"
    cleaned = normalize_markdown_tables(text)

    lines = cleaned.splitlines()
    assert lines[0] == "| A | B |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| one | two |"


def test_normalize_markdown_tables_fixes_mismatched_delimiter() -> None:
    text = "| A | B | C |\n| --- | --- |"
    cleaned = normalize_markdown_tables(text)
    assert cleaned.splitlines()[1] == "| --- | --- | --- |"


def test_clean_markdown_end_to_end_preserves_headings_and_tables() -> None:
    cleaned, stats = clean_markdown(SAMPLE_WITH_NOISE)

    assert "# 1. Giới thiệu" in cleaned
    assert "## 1.1 Mục tiêu" in cleaned
    assert "# 2. Kết luận" in cleaned
    assert "| --- |" in cleaned
    assert "Footer Line 2024" not in cleaned
    assert "CONFIDENTIAL" not in cleaned
    assert stats.chars_after < stats.chars_before
    assert stats.lines_removed >= 4


def test_clean_markdown_does_not_drop_all_content() -> None:
    cleaned, _stats = clean_markdown("# Only Heading\n\nParagraph.")
    assert "# Only Heading" in cleaned
    assert "Paragraph." in cleaned
