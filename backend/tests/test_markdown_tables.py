# =============================================================================
# File: test_markdown_tables.py
# Module/Service: Extraction Service (FR7)
# Layer: Service
# Purpose: Unit tests for GFM + HTML cell table parsers.
# =============================================================================

from __future__ import annotations

from app.services.extraction.markdown_tables import (
    looks_like_html_cell_table,
    parse_document_table,
    parse_html_cell_table,
    parse_markdown_table,
)


def test_parse_gfm_markdown_table() -> None:
    text = "| Year | Revenue |\n| --- | --- |\n| 2024 | 1000 |\n"
    parsed = parse_markdown_table(text)
    assert parsed is not None
    assert parsed["headers"] == ["Year", "Revenue"]
    assert parsed["rows"] == [{"Year": "2024", "Revenue": "1000"}]


def test_parse_html_two_headers() -> None:
    text = (
        "<th>Phase</th>\n<th>Process</th>\n"
        "<td>A</td><td>B</td>\n<td>C</td><td>D</td>"
    )
    parsed = parse_html_cell_table(text)
    assert parsed is not None
    assert parsed["headers"] == ["Phase", "Process"]
    assert len(parsed["rows"]) == 2
    assert parsed["rows"][0] == {"Phase": "A", "Process": "B"}


def test_parse_html_single_th_promotes_two_columns() -> None:
    text = "<th>Nhóm</th>\n<td>Backend</td>\n<td>Python</td>\n<td>API</td>\n<td>REST</td>"
    parsed = parse_html_cell_table(text)
    assert parsed is not None
    assert parsed["headers"] == ["Nhóm", "Chi tiết"]
    assert parsed["rows"][0] == {"Nhóm": "Backend", "Chi tiết": "Python"}


def test_parse_html_decodes_entities_and_strips_marks() -> None:
    text = (
        "<th>A</th><th>B</th>"
        "<td>Data Mapping &#x26; Alignment</td>"
        "<td><mark>hello</mark></td>"
    )
    parsed = parse_html_cell_table(text)
    assert parsed is not None
    assert parsed["rows"][0]["A"] == "Data Mapping & Alignment"
    assert parsed["rows"][0]["B"] == "hello"


def test_parse_document_table_prefers_gfm_then_html() -> None:
    assert parse_document_table("no table") is None
    assert looks_like_html_cell_table("<td>a</td><td>b</td>")
    html = "<th>X</th><th>Y</th><td>1</td><td>2</td>"
    assert parse_document_table(html)["headers"] == ["X", "Y"]
