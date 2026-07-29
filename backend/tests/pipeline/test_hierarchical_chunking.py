# =============================================================================
# File: test_hierarchical_chunking.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Worker
# Purpose: Pipeline-level tests for hierarchical chunking stage behaviour.
# Responsibilities:
#   - Heading tree, nested sections, splitting rules, pipeline log metadata
# Dependencies:
#   - pytest, app.ai.hierarchical_chunking.*, app.workers.stages.hierarchical_chunking
# Public Exports:
#   - N/A
# Database/Table: document_chunks (mocked persistence)
# Related Modules: app.services.hierarchical_chunking
# Important Notes: No live MinIO/Postgres in CI.
# =============================================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.ai.hierarchical_chunking.block_parser import attach_content_blocks
from app.ai.hierarchical_chunking.heading_tree_builder import build_heading_tree
from app.ai.hierarchical_chunking.markdown_parser import parse_markdown_lines
from app.ai.hierarchical_chunking.parent_resolver import resolve_parent_chunk_id
from app.ai.hierarchical_chunking.pipeline import run_hierarchical_chunking
from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.hierarchical_chunking.token_window import tail_token_text
from app.ai.hierarchical_chunking.types import ChunkingInput, PlannedChunk
from app.ai.hierarchical_chunking.chunk_planner import plan_hierarchical_chunks
from app.ai.tokens import count_tokens
from app.models.documents import Document, DocumentVersion
from app.models.enums import ChunkLayoutType, DocumentVersionStatus, FileType
from app.models.knowledge import DocumentChunk
from app.workers.pipeline_errors import DataPipelineError
from app.workers.stages.hierarchical_chunking import stage_hierarchical_chunking


def _plan_markdown(markdown: str, *, file_type: FileType = FileType.pdf) -> list[PlannedChunk]:
    """Run the pure chunking pipeline and return planned chunks."""
    result = run_hierarchical_chunking(
        ChunkingInput(markdown=markdown, layout_metadata=None, file_type=file_type),
    )
    return result.planned_chunks


def _resolve_db_parents(planned: list[PlannedChunk]) -> dict[str, uuid.UUID | None]:
    """Simulate DB insert order and resolve parent_chunk_id for each temp_id."""
    temp_to_db: dict[str, uuid.UUID] = {}
    resolved: dict[str, uuid.UUID | None] = {}
    for chunk in planned:
        parent_id = resolve_parent_chunk_id(chunk, temp_to_db)
        db_id = uuid.uuid4()
        temp_to_db[chunk.temp_id] = db_id
        resolved[chunk.temp_id] = parent_id
    return resolved


def _heading_chunks(planned: list[PlannedChunk]) -> list[PlannedChunk]:
    return [chunk for chunk in planned if chunk.layout_type == ChunkLayoutType.heading]


def _content_for_heading(planned: list[PlannedChunk], heading: PlannedChunk) -> list[PlannedChunk]:
    return [
        chunk
        for chunk in planned
        if chunk.parent_temp_id == heading.temp_id and chunk.layout_type != ChunkLayoutType.heading
    ]


def test_heading_tree_depth_path_and_parent_chunk_id() -> None:
    """Each heading level maps to depth, heading_path, and parent_chunk_id."""
    markdown = """# Alpha

Intro.

## Beta

Beta body.

### Gamma

Gamma body.
"""
    planned = _plan_markdown(markdown)
    parents = _resolve_db_parents(planned)
    headings = {chunk.content: chunk for chunk in _heading_chunks(planned)}

    alpha = headings["Alpha"]
    beta = headings["Beta"]
    gamma = headings["Gamma"]

    assert alpha.depth == 0
    assert beta.depth == 1
    assert gamma.depth == 2

    assert alpha.heading_path == "Alpha"
    assert beta.heading_path == "Alpha > Beta"
    assert gamma.heading_path == "Alpha > Beta > Gamma"

    assert parents[alpha.temp_id] is None
    assert beta.parent_temp_id == alpha.temp_id
    assert parents[beta.temp_id] is not None
    assert gamma.parent_temp_id == beta.temp_id


def test_nested_sections_build_correct_chunk_tree() -> None:
    """Content and child headings nest under the correct heading parent."""
    markdown = """# Root

Root paragraph.

## Child

Child paragraph.

### Leaf

Leaf paragraph.
"""
    planned = _plan_markdown(markdown)
    headings = {chunk.content: chunk for chunk in _heading_chunks(planned)}

    root = headings["Root"]
    child = headings["Child"]
    leaf = headings["Leaf"]

    root_content = _content_for_heading(planned, root)
    child_content = _content_for_heading(planned, child)
    leaf_content = _content_for_heading(planned, leaf)

    assert any("Root paragraph" in chunk.content for chunk in root_content)
    assert any(chunk.parent_temp_id == root.temp_id for chunk in root_content)
    assert child.parent_temp_id == root.temp_id
    assert leaf.parent_temp_id == child.temp_id
    assert not any(chunk.parent_temp_id == root.temp_id for chunk in leaf_content)
    assert any("Leaf paragraph" in chunk.content for chunk in leaf_content)
    assert not any(
        chunk.parent_temp_id == child.temp_id and chunk.layout_type == ChunkLayoutType.heading
        for chunk in planned
        if chunk.content != "Leaf"
    )


def test_large_paragraph_splits_with_overlap() -> None:
    """Paragraphs above hard_limit split into multiple chunks with token overlap."""
    body = " ".join(["tokenword"] * 1500)
    markdown = f"# Section\n\n{body}"
    budget = ChunkTokenBudget.default()
    assert count_tokens(body) > budget.hard_limit

    planned = _plan_markdown(markdown)
    paragraph_chunks = [
        chunk
        for chunk in planned
        if chunk.layout_type == ChunkLayoutType.paragraph and "tokenword" in chunk.content
    ]
    assert len(paragraph_chunks) >= 2
    assert all(chunk.token_count <= budget.hard_limit for chunk in paragraph_chunks)

    overlap = tail_token_text(paragraph_chunks[0].content, budget.overlap_tokens)
    assert overlap
    assert overlap in paragraph_chunks[1].content


def test_markdown_table_is_not_split() -> None:
    """Table blocks remain a single chunk even when many rows."""
    table = "| Col A | Col B |\n| --- | --- |\n" + "\n".join(
        f"| row-{i} | value-{i} |" for i in range(80)
    )
    markdown = f"# Metrics\n\n{table}\n"
    planned = _plan_markdown(markdown)
    table_chunks = [
        chunk
        for chunk in planned
        if chunk.layout_type == ChunkLayoutType.table or "| Col A |" in chunk.content
    ]
    assert len(table_chunks) == 1
    assert "| row-79 |" in table_chunks[0].content


def test_markdown_list_does_not_split_mid_item() -> None:
    """List items stay intact — splits occur only between items."""
    items = [
        "- First item with enough words to consume tokens alone\n"
        "  and a wrapped continuation line that must stay attached",
        "- Second item with extra words to pad token count",
        "- Third item with extra words to pad token count",
        "- Fourth item with extra words to pad token count",
    ]
    markdown = "# Tasks\n\n" + "\n".join(items) + "\n"
    budget = ChunkTokenBudget(
        target_min=15,
        target_max=25,
        hard_limit=30,
        overlap_min=3,
        overlap_max=5,
    )
    result = run_hierarchical_chunking(
        ChunkingInput(markdown=markdown, layout_metadata=None, file_type=FileType.pdf),
        budget=budget,
    )
    list_chunks = [chunk for chunk in result.planned_chunks if chunk.layout_type == ChunkLayoutType.list]
    assert len(list_chunks) >= 2

    for chunk in list_chunks:
        stripped = chunk.content.lstrip()
        if stripped.startswith("- First"):
            assert "continuation line" in chunk.content
            assert "- Second item" not in chunk.content
        if "- Second item" in chunk.content and "- Third item" in chunk.content:
            assert "- First item" not in chunk.content


def test_each_heading_produces_exactly_one_heading_chunk() -> None:
    """Every markdown heading maps to one heading-layout chunk."""
    markdown = """# One

## Two

### Three

#### Four
"""
    lines = parse_markdown_lines(markdown)
    root = build_heading_tree(lines)
    attach_content_blocks(root=root, lines=lines, layout_metadata=None, file_type=FileType.pdf)
    planned = plan_hierarchical_chunks(root)

    heading_chunks = _heading_chunks(planned)
    assert len(heading_chunks) == 4
    assert {chunk.content for chunk in heading_chunks} == {"One", "Two", "Three", "Four"}


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


def test_pipeline_log_metadata_includes_required_fields() -> None:
    """Stage metadata exposes sections_count, chunks_created, max_depth, and timing."""
    markdown = """# Chapter

Body.

## Section

More body.
"""
    version, document = _rows()
    created: list[DocumentChunk] = []
    storage = MagicMock()
    storage.download_bytes.return_value = markdown.encode("utf-8")

    module = "app.workers.stages.hierarchical_chunking"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document, created)),
    ):
        meta = stage_hierarchical_chunking(version.id)

    plan = run_hierarchical_chunking(
        ChunkingInput(markdown=markdown, layout_metadata=None, file_type=FileType.pdf),
    )
    assert meta["sections_count"] == plan.metrics.sections_count
    assert meta["chunks_created"] == len(created)
    assert meta["max_depth"] == plan.metrics.max_depth
    assert meta["avg_chunk_tokens"] == plan.metrics.avg_chunk_tokens
    assert meta["largest_chunk_tokens"] == plan.metrics.largest_chunk_tokens
    assert meta["smallest_chunk_tokens"] == plan.metrics.smallest_chunk_tokens
    assert meta["tables"] == plan.metrics.tables
    assert meta["lists"] == plan.metrics.lists
    assert meta["paragraphs"] == plan.metrics.paragraphs
    assert isinstance(meta["processing_time_ms"], int)
    assert meta["processing_time_ms"] >= 0
    assert meta["chunk_count"] == meta["chunks_created"]


def test_stage_failure_records_full_traceback() -> None:
    """Permanent failures surface a full traceback in DataPipelineError."""
    version, document = _rows()
    version.markdown_storage_path = None
    created: list[DocumentChunk] = []
    storage = MagicMock()

    module = "app.workers.stages.hierarchical_chunking"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document, created)),
    ):
        with pytest.raises(DataPipelineError) as exc_info:
            stage_hierarchical_chunking(version.id)

    message = str(exc_info.value)
    assert "Traceback" in message
    assert "markdown_storage_path missing" in message
