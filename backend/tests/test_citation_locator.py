# =============================================================================
# File: test_citation_locator.py
# Module/Service: Chat / Citation Verification / Document Viewer
# Layer: Test
# Purpose: Regression tests for citation locator enrichment + bbox matching.
# Responsibilities:
#   - _match_bbox prefers tightest overlapping block (not largest text)
#   - CitationResponse accepts chunk_id / location fields
# Dependencies:
#   - pytest, app.services.documents, app.schemas.chat
# Public Exports: N/A
# Database/Table: N/A
# Related Modules: documents._match_bbox, schemas.chat.CitationResponse
# Important Notes: No DB — pure unit tests for deterministic locator helpers.
# =============================================================================

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.schemas.chat import CitationResponse
from app.schemas.content_location import ContentLocation
from app.services.documents import _match_bbox


def test_match_bbox_prefers_tightest_overlapping_block() -> None:
    row = SimpleNamespace(
        content="Hoạt động chính trong kỳ của Công ty và các công ty con",
        page_number=1,
    )
    blocks = [
        {
            "page_number": 1,
            "text": "A. Tổng quan " + row.content + " Kết quả kinh doanh dài…",
            "bbox": [0.05, 0.1, 0.9, 0.4],  # large paragraph
        },
        {
            "page_number": 1,
            "text": row.content,
            "bbox": [0.12, 0.35, 0.7, 0.04],  # tight line
        },
    ]
    bbox = _match_bbox(blocks, row)  # type: ignore[arg-type]
    assert bbox is not None
    assert bbox == [0.12, 0.35, 0.7, 0.04]


def test_match_bbox_returns_none_without_text_overlap() -> None:
    row = SimpleNamespace(content="Hoạt động chính trong kỳ", page_number=1)
    blocks = [
        {"page_number": 1, "text": "", "bbox": [0.1, 0.1, 0.5, 0.1]},
        {"page_number": 2, "text": "Hoạt động chính trong kỳ", "bbox": [0.1, 0.1, 0.5, 0.1]},
    ]
    assert _match_bbox(blocks, row) is None  # type: ignore[arg-type]


def test_citation_response_includes_locator_fields() -> None:
    from app.schemas.canonical import CitationLocator

    cid = uuid.uuid4()
    mid = uuid.uuid4()
    rid = uuid.uuid4()
    did = uuid.uuid4()
    chunk = uuid.uuid4()
    version = uuid.uuid4()
    resp = CitationResponse(
        id=cid,
        message_id=mid,
        retrieval_id=rid,
        document_id=did,
        chunk_id=chunk,
        document_version_id=version,
        text_snippet="Hoạt động chính trong kỳ",
        verified=True,
        order_index=0,
        location=ContentLocation(page_number=1, section_index=None, section_title=None),
        locator=CitationLocator(
            type="canonical",
            view="knowledge",
            confidence="exact",
            markdown_start=10,
            markdown_end=40,
            ranges=[{"block_id": "b0002", "start": 0, "end": 30}],
        ),
    )
    payload = resp.model_dump(mode="json")
    assert payload["chunk_id"] == str(chunk)
    assert payload["document_version_id"] == str(version)
    assert payload["location"]["page_number"] == 1
    assert payload["locator"]["view"] == "knowledge"
    assert payload["locator"]["ranges"][0]["block_id"] == "b0002"
