# =============================================================================
# File: live_llamaparse_timeout_fallback.py
# Purpose: Live document proof for LlamaParse client-poll-timeout → local OCR
#   fallback → Layout Analysis → hierarchical chunking (no Celery required).
# Usage:
#   cd backend && python scripts/live_llamaparse_timeout_fallback.py
# =============================================================================

from __future__ import annotations

import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fitz  # pymupdf

from app.ai.hierarchical_chunking import run_hierarchical_chunking
from app.ai.hierarchical_chunking.types import ChunkingInput
from app.ai.layout import build_layout_analysis
from app.clients.llamaparse_client import LlamaParseClient
from app.core.config import Settings
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.services.document_understanding import (
    PARSER_LOCAL_OCR,
    DocumentUnderstandingService,
    LlamaParseDocumentParser,
    LocalOcrDocumentParser,
)


def _build_pdf() -> bytes:
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "1. Gioi thieu", fontsize=16)
    page1.insert_text((72, 110), "Doan mo dau ve Enterprise NotebookLM.", fontsize=11)
    page1.insert_text((72, 140), "1.1 Muc tieu", fontsize=14)
    page1.insert_text((72, 170), "Noi dung muc tieu cua he thong.", fontsize=11)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "2. Ket luan", fontsize=16)
    page2.insert_text((72, 110), "Tong ket ngan gon.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


class _StubClient(LlamaParseClient):
    def __init__(self, settings: Settings, handler: Any) -> None:
        super().__init__(settings)
        self._handler = handler

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self._handler),
            base_url="https://parse.test",
            headers={"Accept": "application/json"},
        )


def main() -> int:
    pdf_bytes = _build_pdf()
    print("=== LIVE TRACE: LlamaParse timeout -> local OCR fallback ===")
    print(f"1) Upload (simulated source bytes): {len(pdf_bytes)} bytes PDF")

    posts = {"files": 0, "parse": 0, "cancel": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/beta/files":
            posts["files"] += 1
            print("2) LlamaParse submit: POST /api/v1/beta/files → file-live-1")
            return httpx.Response(200, json={"id": "file-live-1"})
        if path == "/api/v2/parse" and request.method == "POST":
            posts["parse"] += 1
            print("3) LlamaParse submit: POST /api/v2/parse → job pjb-live-timeout-1")
            return httpx.Response(200, json={"id": "pjb-live-timeout-1", "status": "PENDING"})
        if path.endswith("/cancel"):
            posts["cancel"] += 1
            print("4) Client budget expired -> best-effort cancel pjb-live-timeout-1")
            return httpx.Response(200, json={"id": "pjb-live-timeout-1", "status": "CANCELLED"})
        # Stay RUNNING until polling budget expires.
        return httpx.Response(
            200,
            json={"job": {"id": "pjb-live-timeout-1", "status": "RUNNING"}},
        )

    settings = Settings(
        _env_file=None,
        document_parser="llamaparse",
        llamaparse_api_key="llx-live-test",
        llamaparse_base_url="https://parse.test",
        llamaparse_timeout_seconds=2,
        llamaparse_max_retries=1,
        llamaparse_poll_interval_seconds=0.2,
        llamaparse_fallback_to_local_ocr=True,
        llamaparse_retry_min_wait=0,
        llamaparse_retry_max_wait=0,
    )

    client = _StubClient(settings, handler)
    storage = MagicMock()
    storage.download_bytes.return_value = pdf_bytes
    uploaded: dict[str, bytes] = {}

    def _upload(*, object_key: str, data: bytes, content_type: str = "") -> str:
        uploaded[object_key] = data
        return object_key

    storage.upload_bytes.side_effect = _upload

    service = DocumentUnderstandingService(
        storage=storage,
        settings=settings,
        parser=LlamaParseDocumentParser(client, settings),
        fallback_parser=LocalOcrDocumentParser(),
    )

    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/live_report.pdf",
        file_size_bytes=len(pdf_bytes),
        checksum_sha256="live",
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=doc_id,
        workspace_id=uuid.uuid4(),
        current_version_id=version_id,
        title="Live Report",
        file_type=FileType.pdf,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    t0 = time.perf_counter()
    result = service.execute(
        document_version_id=version_id,
        version=version,
        document=document,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    meta = result.stage_metadata
    print("5) Timeout diagnostics:")
    print(f"   remote_status={meta.get('remote_status')} client_timeout={meta.get('client_timeout')}")
    print(f"   llamaparse_job_id={meta.get('llamaparse_job_id')} fallback={meta.get('fallback')}")
    print("6) Local OCR fallback completed")
    print(f"   parser={result.parser} page_count={meta.get('page_count')} blocks={meta.get('block_count')}")
    print(f"   duration_ms={elapsed_ms}")

    assert posts["files"] == 1, "must not duplicate LlamaParse file upload"
    assert posts["parse"] == 1, "must not duplicate LlamaParse job submission"
    assert result.parser == PARSER_LOCAL_OCR
    assert meta["fallback"] is True
    assert meta["fallback_reason"] == "timeout"
    assert meta["client_timeout"] is True
    assert meta["remote_status"] == "RUNNING"
    assert meta["llamaparse_job_id"] == "pjb-live-timeout-1"

    # Layout (already done inside service) + chunking proof
    md = uploaded[result.markdown_storage_path].decode("utf-8")
    analysis = build_layout_analysis(
        markdown=md,
        item_pages=[],  # service already persisted layout; re-check markdown path
        reported_page_count=meta["page_count"],
    )
    print("7) Layout Analysis OK")
    print(f"   layout_source={result.layout_metadata.get('source')} sections={analysis.section_count}")

    chunks_plan = run_hierarchical_chunking(
        ChunkingInput(
            markdown=md,
            layout_metadata=result.layout_metadata,
            file_type=FileType.pdf,
        )
    )
    print("8) Chunking OK")
    print(f"   chunk_count={len(chunks_plan.planned_chunks)}")
    print("9) Embedding/Indexing: skipped in this script (unchanged stages; DU output is ready)")
    print("10) Completed — document would continue pipeline without Celery re-queue")
    print()
    print("TRACE SUMMARY:")
    print(
        "Upload -> LlamaParse submit (1 job) -> poll timeout (RUNNING) -> "
        "local OCR fallback -> layout -> chunk -> (embedding/indexing unchanged)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
