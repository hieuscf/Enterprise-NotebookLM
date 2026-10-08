# =============================================================================
# File: test_ai_optional_architecture.py
# Module/Service: Architecture — AI-optional core
# Layer: Tests
# Purpose: Prove core document flows work with AI off; analysis is on-demand.
# Responsibilities:
#   - Tests 1–14 from the AI-optional refactor plan
# Dependencies:
#   - pytest, in-memory fakes (no live LLM/Qdrant/LlamaParse)
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: REFACTOR_PLAN.md
# Important Notes: Upload must never enqueue run_pipeline.
# =============================================================================

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.integrations.ai.exceptions import (
    AI_CAPABILITY_UNAVAILABLE,
    AI_DISABLED,
    AIGatewayError,
)
from app.integrations.ai.gateway import get_ai_gateway
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    AiAnalysisStatus,
    DocumentVersionStatus,
    FileType,
    PipelineStatus,
    ReportFormat,
    ReportSourceType,
    ReportStatus,
)
from app.models.pipeline import PipelineRun
from app.repositories.retrieval import MetadataDocumentRow
from app.schemas.search import SearchRequest
from app.services.analysis.analysis_service import AnalysisService
from app.services.comparison.result_schemas import comparison_result_to_dict, parse_comparison_result
from app.services.documents import DocumentIngestionService
from app.services.search import SearchService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_stream(self, *, object_key: str, stream, length: int, content_type: str = "") -> str:
        self.objects[object_key] = stream.read(length)
        return object_key

    def delete_object(self, object_key: str) -> None:
        self.objects.pop(object_key, None)

    def download_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]


class FakeDocRepo:
    def __init__(self) -> None:
        self.documents: dict[uuid.UUID, Document] = {}
        self.versions: dict[uuid.UUID, DocumentVersion] = {}
        self.events: list[dict] = []

    async def create_document(self, *, workspace_id, title, file_type) -> Document:
        doc = Document(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            title=title,
            file_type=file_type,
            current_version_id=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.documents[doc.id] = doc
        return doc

    async def get_document(self, workspace_id, document_id) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return doc

    async def next_version_number(self, document_id) -> int:
        nums = [v.version_number for v in self.versions.values() if v.document_id == document_id]
        return (max(nums) if nums else 0) + 1

    async def clear_current_flags(self, document_id) -> None:
        for ver in self.versions.values():
            if ver.document_id == document_id:
                ver.is_current = False

    async def get_version(self, workspace_id, document_id, version_id) -> DocumentVersion | None:
        ver = self.versions.get(version_id)
        if ver is None or ver.document_id != document_id:
            return None
        return ver

    async def create_version(
        self,
        *,
        document_id,
        uploaded_by,
        version_number,
        storage_path,
        file_size_bytes,
        checksum_sha256,
        is_current,
        status=DocumentVersionStatus.ready,
        ai_analysis_status=AiAnalysisStatus.not_analyzed,
    ) -> DocumentVersion:
        ver = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            uploaded_by=uploaded_by,
            version_number=version_number,
            storage_path=storage_path,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            page_count=None,
            status=status,
            ai_analysis_status=ai_analysis_status,
            is_current=is_current,
            created_at=datetime.now(UTC),
        )
        self.versions[ver.id] = ver
        return ver

    async def add_version_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def count_analyzed_versions(self, workspace_id) -> int:
        return sum(
            1
            for v in self.versions.values()
            if v.ai_analysis_status == AiAnalysisStatus.ready
            and self.documents[v.document_id].workspace_id == workspace_id
        )


class FakePipelineRepo:
    def __init__(self) -> None:
        self.runs: list[PipelineRun] = []

    async def create_run(self, document_version_id) -> PipelineRun:
        run = PipelineRun(
            id=uuid.uuid4(),
            document_version_id=document_version_id,
            status=PipelineStatus.pending,
            retry_count=0,
        )
        self.runs.append(run)
        return run

    async def get_latest_run_with_stages(self, version_id) -> PipelineRun | None:
        matches = [r for r in self.runs if r.document_version_id == version_id]
        return matches[-1] if matches else None


async def _chunks(data: bytes):
    yield data


def _off_settings() -> Settings:
    return Settings(ai_enabled=False)


def _wire_upload(session, storage, docs, pipeline, *, enqueue=True) -> DocumentIngestionService:
    service = DocumentIngestionService(session, storage, enqueue=enqueue)
    service._docs = docs
    service._pipeline = pipeline
    return service


@pytest.mark.asyncio
async def test_1_upload_succeeds_when_ai_disabled(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_upload(session, storage, docs, pipeline)
    monkeypatch.setattr("app.workers.previews.generate_preview.delay", lambda _v: None)
    monkeypatch.setattr(
        "app.workers.pipeline.run_pipeline.delay",
        lambda _r: (_ for _ in ()).throw(AssertionError("pipeline must not run on upload")),
    )

    result = await service.upload_new(
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        title="Contract",
        filename="contract.pdf",
        file_chunks=_chunks(b"%PDF-1.4 body"),
    )
    assert result.version.status == DocumentVersionStatus.ready
    assert result.pipeline_run is None


@pytest.mark.asyncio
async def test_2_create_document_version(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_upload(session, storage, docs, pipeline)
    monkeypatch.setattr("app.workers.previews.generate_preview.delay", lambda _v: None)

    first = await service.upload_new(
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        title="Doc",
        filename="a.txt",
        file_chunks=_chunks(b"v1"),
    )
    second = await service.upload_new_version(
        workspace_id=first.document.workspace_id,
        document_id=first.document.id,
        uploaded_by=uuid.uuid4(),
        filename="a.txt",
        file_chunks=_chunks(b"v2"),
    )
    assert second.version.version_number == 2
    assert second.version.status == DocumentVersionStatus.ready


@pytest.mark.asyncio
async def test_3_download_original_from_object_storage(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_upload(session, storage, docs, pipeline)
    monkeypatch.setattr("app.workers.previews.generate_preview.delay", lambda _v: None)
    payload = b"original-bytes"
    result = await service.upload_new(
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        title="Doc",
        filename="a.txt",
        file_chunks=_chunks(payload),
    )
    assert storage.download_bytes(result.version.storage_path) == payload
    assert result.version.checksum_sha256 == hashlib.sha256(payload).hexdigest()


@pytest.mark.asyncio
async def test_8_upload_does_not_trigger_analysis(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_upload(session, storage, docs, pipeline)
    monkeypatch.setattr("app.workers.previews.generate_preview.delay", lambda _v: None)
    pipeline_calls: list[str] = []
    monkeypatch.setattr(
        "app.workers.pipeline.run_pipeline.delay",
        lambda rid: pipeline_calls.append(rid),
    )
    result = await service.upload_new(
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        title="Doc",
        filename="a.txt",
        file_chunks=_chunks(b"hello"),
    )
    assert result.version.ai_analysis_status == AiAnalysisStatus.not_analyzed
    assert pipeline_calls == []
    assert pipeline.runs == []


@pytest.mark.asyncio
async def test_9_and_13_request_analysis_queued_ai_off_and_on(monkeypatch) -> None:
    session = FakeSession()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    ws = uuid.uuid4()
    doc = await docs.create_document(workspace_id=ws, title="Doc", file_type=FileType.txt)
    ver = await docs.create_version(
        document_id=doc.id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="k",
        file_size_bytes=1,
        checksum_sha256="a",
        is_current=True,
    )

    off = AnalysisService(session, settings=_off_settings(), enqueue=True)
    off._docs = docs
    off._pipeline = pipeline
    with pytest.raises(AIGatewayError) as exc:
        await off.request_analysis(workspace_id=ws, document_id=doc.id, version_id=ver.id)
    assert exc.value.code == AI_DISABLED
    assert ver.ai_analysis_status == AiAnalysisStatus.not_analyzed

    enqueued: list[str] = []
    monkeypatch.setattr("app.workers.pipeline.run_pipeline.delay", lambda rid: enqueued.append(rid))
    on = AnalysisService(session, settings=Settings(ai_enabled=True), enqueue=True)
    on._docs = docs
    on._pipeline = pipeline
    snap = await on.request_analysis(workspace_id=ws, document_id=doc.id, version_id=ver.id)
    assert snap.version.ai_analysis_status == AiAnalysisStatus.queued
    assert enqueued == [str(snap.pipeline_run.id)]

    again = await on.request_analysis(workspace_id=ws, document_id=doc.id, version_id=ver.id)
    assert again.pipeline_run.id == snap.pipeline_run.id
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_14_new_version_not_analyzed_old_stays_ready(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_upload(session, storage, docs, pipeline)
    monkeypatch.setattr("app.workers.previews.generate_preview.delay", lambda _v: None)

    first = await service.upload_new(
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        title="Doc",
        filename="a.txt",
        file_chunks=_chunks(b"v1"),
    )
    first.version.ai_analysis_status = AiAnalysisStatus.ready
    first.version.analyzed_at = datetime.now(UTC)

    second = await service.upload_new_version(
        workspace_id=first.document.workspace_id,
        document_id=first.document.id,
        uploaded_by=uuid.uuid4(),
        filename="a.txt",
        file_chunks=_chunks(b"v2"),
    )
    assert first.version.ai_analysis_status == AiAnalysisStatus.ready
    assert second.version.ai_analysis_status == AiAnalysisStatus.not_analyzed


@pytest.mark.asyncio
async def test_5_basic_search_without_ai() -> None:
    ws = uuid.uuid4()
    doc_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(side_effect=AssertionError("hybrid must not run"))
    history = MagicMock()
    created = MagicMock(id=uuid.uuid4(), query_text="Contract", results_count=1)
    history.create = AsyncMock(return_value=created)
    retrieval = MagicMock()
    retrieval.list_documents_metadata = AsyncMock(
        return_value=[
            MetadataDocumentRow(
                document_id=doc_id,
                workspace_id=ws,
                title="Contract.pdf",
                file_type=FileType.pdf,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                uploaded_by=uuid.uuid4(),
                version_number=1,
                status="ready",
            )
        ]
    )
    service = SearchService(
        hybrid=hybrid,
        history_repo=history,
        retrieval_repo=retrieval,
        settings=_off_settings(),
    )
    resp = await service.search(
        workspace_id=ws,
        user_id=uuid.uuid4(),
        body=SearchRequest(query_text="Contract", top_k=10),
    )
    assert resp.results_count == 1
    hybrid.retrieve.assert_not_called()


def test_6_deterministic_comparison_without_ai() -> None:
    parsed = parse_comparison_result(
        {
            "similarities": ["All documents have file type pdf."],
            "differences": ["File checksums differ between documents."],
        }
    )
    payload = comparison_result_to_dict(parsed)
    assert payload["similarities"]
    assert payload["differences"]


def test_7_report_module_has_no_llm_import() -> None:
    import app.services.report_service as rs
    import inspect

    source = inspect.getsource(rs)
    assert "chat_llm" not in source
    assert "anthropic" not in source.lower()
    assert ReportStatus.pending.value == "pending"
    assert ReportFormat.markdown.value == "markdown"
    assert ReportSourceType.summary.value == "summary"


def test_10_disabled_gateway_does_not_crash() -> None:
    gw = get_ai_gateway(_off_settings())
    assert gw.is_enabled() is False
    with pytest.raises(AIGatewayError) as exc:
        gw.require_enabled(capability="Chat")
    assert exc.value.code == AI_DISABLED
    with pytest.raises(AIGatewayError) as exc2:
        gw.generate(system="s", user="u", model="m")
    assert exc2.value.code == AI_CAPABILITY_UNAVAILABLE


@pytest.mark.asyncio
async def test_11_live_gateway_generate_is_called(monkeypatch) -> None:
    called: dict[str, Any] = {}

    async def _fake_generate_async(**kwargs: Any) -> Any:
        called.update(kwargs)
        return MagicMock(parsed={"answer": "ok"}, model="test")

    monkeypatch.setattr(
        "app.integrations.ai.live.extract_structured_json_async",
        _fake_generate_async,
    )
    gw = get_ai_gateway(Settings(ai_enabled=True))
    assert gw.is_enabled() is True
    result = await gw.generate_async(system="sys", user="q", model="m")
    assert called["system"] == "sys"
    assert result.parsed["answer"] == "ok"


def test_12_provider_unavailable_core_still_constructs() -> None:
    gw = get_ai_gateway(_off_settings())
    assert gw.is_enabled() is False
    from app.main import app as fastapi_app

    assert fastapi_app.title


def test_4_rbac_roles_unchanged() -> None:
    from app.models.enums import RoleName

    assert {r.value for r in RoleName} == {"admin", "editor", "viewer"}
