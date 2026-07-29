# =============================================================================
# File: test_hierarchical_chunking.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Unit tests for hierarchical chunking pure functions and stage.
# Dependencies:
#   - pytest
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.*
# Important Notes: No live MinIO/Postgres/LLM in CI.
# =============================================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.ai.hierarchical_chunking.block_parser import attach_content_blocks, map_layout_type
from app.ai.hierarchical_chunking.chunk_planner import plan_hierarchical_chunks
from app.ai.hierarchical_chunking.heading_tree_builder import build_heading_tree, heading_depth
from app.ai.hierarchical_chunking.markdown_parser import parse_markdown_lines
from app.ai.hierarchical_chunking.pipeline import run_hierarchical_chunking
from app.ai.hierarchical_chunking.types import ChunkingInput
from app.models.documents import Document, DocumentVersion
from app.models.enums import ChunkLayoutType, DocumentVersionStatus, FileType
from app.models.knowledge import DocumentChunk
from app.workers.pipeline_errors import DataPipelineError
from app.workers.stages.hierarchical_chunking import stage_hierarchical_chunking

SAMPLE_MARKDOWN = """# Chapter

Intro paragraph under chapter.

## Marketing

Marketing body with enough text to chunk.

### Digital

Digital channel details.

| KPI | Value |
| --- | --- |
| CTR | 4% |

# Appendix

Closing section.
"""


def test_heading_depth_maps_markdown_levels() -> None:
    assert heading_depth(1) == 0
    assert heading_depth(2) == 1
    assert heading_depth(3) == 2


def test_build_heading_tree_nested_paths() -> None:
    lines = parse_markdown_lines(SAMPLE_MARKDOWN)
    root = build_heading_tree(lines)

    titles = [child.title for child in root.children]
    assert titles == ["Chapter", "Appendix"]

    chapter = root.children[0]
    assert chapter.heading_path == "Chapter"
    assert [child.title for child in chapter.children] == ["Marketing"]

    marketing = chapter.children[0]
    assert marketing.heading_path == "Chapter > Marketing"
    assert marketing.children[0].heading_path == "Chapter > Marketing > Digital"


def test_attach_content_blocks_uses_layout_metadata_types() -> None:
    lines = parse_markdown_lines(SAMPLE_MARKDOWN)
    root = build_heading_tree(lines)
    layout_metadata = {
        "blocks": [
            {"order_index": 0, "block_type": "paragraph", "page_number": 1},
            {"order_index": 1, "block_type": "paragraph", "page_number": 1},
            {"order_index": 2, "block_type": "paragraph", "page_number": 2},
            {"order_index": 3, "block_type": "paragraph", "page_number": 2},
            {"order_index": 4, "block_type": "table", "page_number": 2},
            {"order_index": 5, "block_type": "paragraph", "page_number": 3},
        ]
    }
    attach_content_blocks(
        root=root,
        lines=lines,
        layout_metadata=layout_metadata,
        file_type=FileType.pdf,
    )

    chapter = root.children[0]
    assert chapter.content_blocks
    assert chapter.content_blocks[0].layout_type == ChunkLayoutType.paragraph
    assert chapter.content_blocks[0].page_number == 1

    digital_section = chapter.children[0].children[0]
    table_blocks = [b for b in digital_section.content_blocks if b.layout_type == ChunkLayoutType.table]
    assert table_blocks


def test_plan_hierarchical_chunks_parent_relationships() -> None:
    lines = parse_markdown_lines(SAMPLE_MARKDOWN)
    root = build_heading_tree(lines)
    attach_content_blocks(root=root, lines=lines, layout_metadata=None, file_type=FileType.pdf)
    planned = plan_hierarchical_chunks(root)

    by_temp = {chunk.temp_id: chunk for chunk in planned}
    headings = [c for c in planned if c.layout_type == ChunkLayoutType.heading]
    assert headings

    chapter = next(c for c in headings if c.content == "Chapter")
    marketing = next(c for c in headings if c.content == "Marketing")
    assert chapter.parent_temp_id is None
    assert marketing.parent_temp_id == chapter.temp_id

    marketing_children = [c for c in planned if c.parent_temp_id == marketing.temp_id]
    assert marketing_children
    assert any(
        c.content == "Digital" and c.layout_type == ChunkLayoutType.heading
        for c in marketing_children
    )
    content_children = [c for c in marketing_children if c.layout_type != ChunkLayoutType.heading]
    assert content_children


def test_run_hierarchical_chunking_preserves_heading_chunks() -> None:
    plan = run_hierarchical_chunking(
        ChunkingInput(
            markdown=SAMPLE_MARKDOWN,
            layout_metadata=None,
            file_type=FileType.docx,
        ),
    )

    assert plan.metrics.chunks_created >= 4
    assert plan.metrics.heading_chunk_count >= 4
    paths = {chunk.heading_path for chunk in plan.planned_chunks if chunk.layout_type == ChunkLayoutType.heading}
    assert "Chapter > Marketing > Digital" in paths


def test_map_layout_type_rejects_unknown_values_to_paragraph() -> None:
    assert map_layout_type("table") == ChunkLayoutType.table
    assert map_layout_type("unknown-type") == ChunkLayoutType.paragraph


def _rows() -> tuple[DocumentVersion, Document]:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/report.pdf",
        markdown_storage_path="workspaces/ws/documents/doc/v1/document.md",
        layout_metadata={"blocks": []},
        file_size_bytes=1024,
        checksum_sha256="x",
        page_count=3,
        parser="llamaparse",
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=doc_id,
        workspace_id=uuid.uuid4(),
        current_version_id=version_id,
        title="Report",
        file_type=FileType.pdf,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return version, document


@contextmanager
def _session_for(version: DocumentVersion, document: Document, created: list[DocumentChunk]):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: {
        DocumentVersion: version,
        Document: document,
    }.get(model)

    class FakeKnowledge:
        def clear_version_artifacts(self, _vid: uuid.UUID) -> None:
            created.clear()

        def create_chunk(self, **kwargs: Any) -> DocumentChunk:
            chunk = DocumentChunk(
                id=uuid.uuid4(),
                document_version_id=kwargs["document_version_id"],
                chunk_index=kwargs["chunk_index"],
                content=kwargs["content"],
                page_number=kwargs.get("page_number"),
                section_index=kwargs.get("section_index"),
                section=kwargs.get("section"),
                token_count=kwargs.get("token_count"),
                parent_chunk_id=kwargs.get("parent_chunk_id"),
                heading_path=kwargs.get("heading_path"),
                depth=kwargs.get("depth"),
                layout_type=kwargs.get("layout_type"),
                created_at=datetime.now(UTC),
            )
            created.append(chunk)
            return chunk

    with patch(
        "app.services.hierarchical_chunking.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    ):
        yield session


def test_stage_hierarchical_chunking_persists_parent_and_heading_path() -> None:
    version, document = _rows()
    created: list[DocumentChunk] = []
    storage = MagicMock()
    storage.download_bytes.return_value = SAMPLE_MARKDOWN.encode("utf-8")

    module = "app.workers.stages.hierarchical_chunking"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document, created)),
    ):
        meta = stage_hierarchical_chunking(version.id)

    assert meta["chunks_created"] == len(created)
    assert meta["chunk_count"] == len(created)
    assert meta["heading_chunk_count"] >= 4
    headings = [c for c in created if c.layout_type == ChunkLayoutType.heading]
    assert headings
    assert any(c.heading_path == "Chapter > Marketing" for c in headings)
    assert any(c.parent_chunk_id is not None for c in created)
    assert any(c.layout_type == ChunkLayoutType.paragraph for c in created)


def test_stage_fails_without_markdown_path() -> None:
    version, document = _rows()
    version.markdown_storage_path = None
    created: list[DocumentChunk] = []
    storage = MagicMock()

    module = "app.workers.stages.hierarchical_chunking"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document, created)),
    ):
        with pytest.raises(DataPipelineError, match="markdown_storage_path missing"):
            stage_hierarchical_chunking(version.id)
