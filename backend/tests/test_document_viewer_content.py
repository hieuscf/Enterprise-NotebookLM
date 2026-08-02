# =============================================================================
# File: test_document_viewer_content.py
# Module/Service: Document Ingestion Service
# Layer: Tests
# Purpose: Unit tests for Original Document Viewer helpers (bbox + viewer_kind).
# =============================================================================

from __future__ import annotations

from types import SimpleNamespace

from app.models.enums import PreviewStatus, PreviewType
from app.services.documents import _match_bbox, _viewer_kind_from_preview


def test_match_bbox_returns_overlapping_block() -> None:
    row = SimpleNamespace(
        content="Rate limiting protects the API Gateway under burst traffic.",
        page_number=3,
    )
    blocks = [
        {
            "page_number": 3,
            "text": "Rate limiting protects the API Gateway under burst traffic. Defaults apply.",
            "bbox": [0.1, 0.2, 0.8, 0.05],
        },
        {
            "page_number": 3,
            "text": "Unrelated footnote",
            "bbox": [0.0, 0.9, 1.0, 0.05],
        },
    ]
    assert _match_bbox(blocks, row) == [0.1, 0.2, 0.8, 0.05]


def test_match_bbox_skips_wrong_page() -> None:
    row = SimpleNamespace(
        content="Rate limiting protects the API Gateway under burst traffic.",
        page_number=2,
    )
    blocks = [
        {
            "page_number": 3,
            "text": "Rate limiting protects the API Gateway under burst traffic.",
            "bbox": [0.1, 0.2, 0.8, 0.05],
        },
    ]
    assert _match_bbox(blocks, row) is None


def test_viewer_kind_requires_completed_preview() -> None:
    pending = SimpleNamespace(
        preview_status=PreviewStatus.pending,
        preview_file_path=None,
        preview_type=None,
    )
    assert _viewer_kind_from_preview(pending) == "original_download"

    ready = SimpleNamespace(
        preview_status=PreviewStatus.completed,
        preview_file_path="workspaces/ws/docs/d/v1/document.pdf",
        preview_type=PreviewType.pdf,
    )
    assert _viewer_kind_from_preview(ready) == "pdf"
