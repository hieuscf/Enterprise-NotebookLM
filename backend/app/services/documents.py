# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Service
# Purpose: Upload, versioning, checksum, MinIO store, enqueue pipeline (FR2/UC2).
# Responsibilities:
#   - Chunked SHA-256 + MinIO upload; create documents/versions/pipeline_runs
#   - Version history + set-current (ready-only); enqueue run_pipeline
# Dependencies:
#   - app.repositories.documents, pipeline; app.adapters.minio_storage
#   - app.workers.pipeline.run_pipeline
# Public Exports:
#   - DocumentIngestionService, DocumentIngestionError
#   - detect_file_type, build_storage_path, hash_upload_stream
# Database/Table: documents, document_versions, pipeline_runs
# Related Modules: app.api.documents, System_Architecture (Document Ingestion Service)
# Important Notes:
#   - documents has no file bytes; versions own storage_path.
#   - storage_path = workspaces/{ws}/documents/{doc}/v{n}/{filename}
#   - set-current only when version.status == ready.
# =============================================================================

from __future__ import annotations

import hashlib
import tempfile
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, BinaryIO, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.minio_storage import MinioStorageAdapter
from app.core.logging import get_logger
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType, PreviewStatus
from app.models.pipeline import PipelineRun
from app.repositories.documents import DocumentRepository
from app.repositories.pipeline import PipelineRepository
from app.repositories.retrieval import ChunkHydrationRow, RetrievalRepository
from app.schemas.documents import DocumentChunkListResponse, DocumentChunkResponse
from app.services.preview_generator import PREVIEW_PDF_ARTIFACT

logger = get_logger(__name__)


class _ReadableUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


ALLOWED_EXTENSIONS: dict[str, FileType] = {
    ".pdf": FileType.pdf,
    ".docx": FileType.docx,
    ".xlsx": FileType.xlsx,
    ".pptx": FileType.pptx,
    ".txt": FileType.txt,
}

CONTENT_TYPES: dict[FileType, str] = {
    FileType.pdf: "application/pdf",
    FileType.docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileType.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileType.pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    FileType.txt: "text/plain",
}


@dataclass(frozen=True, slots=True)
class DocumentContentPayload:
    """Original (or preview PDF) bytes for the Document Viewer."""

    data: bytes
    content_type: str
    filename: str
    viewer_kind: str  # pdf | original_download
    storage_key: str


# Hash/spool in 1 MiB chunks; spool to disk when payload exceeds 8 MiB.
_HASH_CHUNK_SIZE = 1024 * 1024
_SPOOL_MAX_MEMORY = 8 * 1024 * 1024


class DocumentIngestionError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DocumentPage:
    items: list[Document]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True, slots=True)
class UploadResult:
    document: Document
    version: DocumentVersion
    pipeline_run: PipelineRun


@dataclass(frozen=True, slots=True)
class SpooledUpload:
    checksum_sha256: str
    file_size_bytes: int
    stream: BinaryIO


def detect_file_type(filename: str) -> FileType:
    lower = filename.lower()
    for ext, ft in ALLOWED_EXTENSIONS.items():
        if lower.endswith(ext):
            return ft
    raise DocumentIngestionError(
        "unsupported_file_type",
        "Supported types: PDF, DOCX, XLSX, PPTX, TXT",
        status_code=400,
    )


def build_storage_path(
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    version_number: int,
    filename: str,
) -> str:
    """MinIO key: workspaces/{workspaceId}/documents/{documentId}/v{n}/{filename}."""
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"workspaces/{workspace_id}/documents/{document_id}/v{version_number}/{safe_name}"


async def hash_upload_stream(
    chunks: AsyncIterator[bytes],
    *,
    chunk_size: int = _HASH_CHUNK_SIZE,
) -> SpooledUpload:
    """Chunked SHA-256 while spooling to memory/disk (avoids loading whole file in RAM)."""
    del chunk_size  # caller yields sized chunks; kept for API clarity
    hasher = hashlib.sha256()
    size = 0
    spool: BinaryIO = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY)
    async for chunk in chunks:
        if not chunk:
            continue
        hasher.update(chunk)
        spool.write(chunk)
        size += len(chunk)

    if size == 0:
        spool.close()
        raise DocumentIngestionError("empty_file", "Uploaded file is empty", status_code=400)

    spool.seek(0)
    return SpooledUpload(
        checksum_sha256=hasher.hexdigest(),
        file_size_bytes=size,
        stream=spool,
    )


async def iter_upload_file(
    upload: _ReadableUpload,
    *,
    chunk_size: int = _HASH_CHUNK_SIZE,
) -> AsyncIterator[bytes]:
    """Yield bytes from a Starlette/FastAPI UploadFile without reading all at once."""
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        yield chunk


class DocumentIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        storage: MinioStorageAdapter,
        *,
        enqueue: bool = True,
    ) -> None:
        self._session = session
        self._storage = storage
        self._docs = DocumentRepository(session)
        self._pipeline = PipelineRepository(session)
        self._retrieval = RetrievalRepository(session)
        self._enqueue = enqueue

    async def list_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        file_type: FileType | None = None,
    ) -> DocumentPage:
        items, total = await self._docs.list_documents(
            workspace_id,
            page=page,
            page_size=page_size,
            file_type=file_type,
        )
        return DocumentPage(items=items, page=page, page_size=page_size, total=total)

    async def get_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        doc = await self._docs.get_document(workspace_id, document_id)
        if doc is None:
            raise DocumentIngestionError("not_found", "Document not found", status_code=404)
        return doc

    async def list_document_chunks(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> DocumentChunkListResponse:
        """Return ordered chunk metadata for AI panel / deep-link (not for body render)."""
        doc = await self.get_document(workspace_id, document_id)
        target = version_id or doc.current_version_id
        rows: list[ChunkHydrationRow] = await self._retrieval.list_chunks_for_document(
            workspace_id,
            document_id,
            version_id=target,
        )
        layout_blocks: list[dict[str, Any]] = []
        heading_tree: list[dict[str, Any]] = []
        if target is not None:
            version = await self._docs.get_version(workspace_id, document_id, target)
            if version is not None and isinstance(version.layout_metadata, dict):
                raw_blocks = version.layout_metadata.get("blocks") or []
                if isinstance(raw_blocks, list):
                    layout_blocks = [b for b in raw_blocks if isinstance(b, dict)]
                raw_tree = version.layout_metadata.get("heading_tree") or []
                if isinstance(raw_tree, list):
                    heading_tree = [n for n in raw_tree if isinstance(n, dict)]

        items = [
            DocumentChunkResponse(
                id=row.chunk_id,
                document_id=row.document_id,
                document_version_id=row.document_version_id,
                chunk_index=int(row.chunk_index or 0),
                content=row.content,
                page_number=row.page_number,
                section_index=row.section_index,
                section=row.section,
                heading_path=row.heading_path,
                section_path=row.heading_path,
                bounding_box=_match_bbox(layout_blocks, row),
            )
            for row in rows
        ]
        preview_status = PreviewStatus.pending
        preview_type = None
        preview_generated_at = None
        viewer_kind = "original_download"
        if target is not None:
            version = await self._docs.get_version(workspace_id, document_id, target)
            if version is not None:
                preview_status = version.preview_status
                preview_type = version.preview_type
                preview_generated_at = version.preview_generated_at
                viewer_kind = _viewer_kind_from_preview(version)
        return DocumentChunkListResponse(
            document_id=doc.id,
            document_version_id=target,
            document_title=doc.title,
            file_type=doc.file_type.value,  # type: ignore[arg-type]
            viewer_kind=viewer_kind,  # type: ignore[arg-type]
            preview_status=preview_status.value,  # type: ignore[arg-type]
            preview_type=preview_type.value if preview_type else None,  # type: ignore[arg-type]
            preview_generated_at=preview_generated_at,
            heading_tree=heading_tree,
            items=items,
        )

    async def get_document_content(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
        prefer_preview_pdf: bool = True,
    ) -> DocumentContentPayload:
        """Load Original or Preview bytes for the Document Viewer.

        Args:
            workspace_id: Tenant scope.
            document_id: Document id.
            version_id: Optional version; default current.
            prefer_preview_pdf: When True, require completed Preview Representation.

        Returns:
            ``DocumentContentPayload`` with bytes + content type.

        Raises:
            DocumentIngestionError: Missing document/version/object, or preview
                not ready when prefer_preview_pdf=True.
        """
        doc = await self.get_document(workspace_id, document_id)
        target = version_id or doc.current_version_id
        if target is None:
            raise DocumentIngestionError(
                "not_found",
                "Document has no current version",
                status_code=404,
            )
        version = await self.get_version(workspace_id, document_id, target)
        storage_key = version.storage_path
        content_type = CONTENT_TYPES.get(doc.file_type, "application/octet-stream")
        viewer_kind = "original_download"
        filename = storage_key.rsplit("/", 1)[-1] or f"{document_id}"

        if prefer_preview_pdf:
            if version.preview_status != PreviewStatus.completed:
                raise DocumentIngestionError(
                    "preview_not_ready",
                    f"Preview status is {version.preview_status.value}",
                    status_code=409,
                )
            if not version.preview_file_path:
                raise DocumentIngestionError(
                    "preview_missing",
                    "Preview completed but preview_file_path is empty",
                    status_code=502,
                )
            storage_key = version.preview_file_path
            content_type = CONTENT_TYPES[FileType.pdf]
            viewer_kind = "pdf"
            filename = PREVIEW_PDF_ARTIFACT if doc.file_type != FileType.pdf else filename

        try:
            data = self._storage.download_bytes(storage_key)
        except Exception as exc:  # noqa: BLE001 — surface as 404/502 to client
            logger.exception(
                "document_content_download_failed",
                workspace_id=str(workspace_id),
                document_id=str(document_id),
                storage_key=storage_key,
            )
            raise DocumentIngestionError(
                "storage_unavailable",
                "Could not load document from storage",
                status_code=502,
            ) from exc

        return DocumentContentPayload(
            data=data,
            content_type=content_type,
            filename=filename,
            viewer_kind=viewer_kind,
            storage_key=storage_key,
        )

    async def delete_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> None:
        doc = await self.get_document(workspace_id, document_id)
        versions = await self._docs.list_versions(workspace_id, document_id)
        for ver in versions:
            self._storage.delete_object(ver.storage_path)
        await self._docs.delete_document(doc)

    async def list_versions(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[DocumentVersion]:
        await self.get_document(workspace_id, document_id)
        return await self._docs.list_versions(workspace_id, document_id)

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion:
        version = await self._docs.get_version(workspace_id, document_id, version_id)
        if version is None:
            raise DocumentIngestionError(
                "not_found",
                "Document version not found",
                status_code=404,
            )
        return version

    async def upload_new(
        self,
        *,
        workspace_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        title: str,
        filename: str,
        file_chunks: AsyncIterator[bytes],
    ) -> UploadResult:
        if not title.strip():
            raise DocumentIngestionError("invalid_title", "title is required", status_code=400)

        file_type = detect_file_type(filename)
        spooled = await hash_upload_stream(file_chunks)
        storage_path: str | None = None

        try:
            # 1) documents — current_version_id null until version row exists
            document = await self._docs.create_document(
                workspace_id=workspace_id,
                title=title.strip(),
                file_type=file_type,
            )
            version_number = 1
            storage_path = build_storage_path(
                workspace_id=workspace_id,
                document_id=document.id,
                version_number=version_number,
                filename=filename,
            )

            # 2) MinIO before version insert so failed upload never leaves a version row
            self._storage.upload_stream(
                object_key=storage_path,
                stream=spooled.stream,
                length=spooled.file_size_bytes,
                content_type=CONTENT_TYPES[file_type],
            )

            # 3) document_versions (processing, is_current, page_count=null)
            version = await self._docs.create_version(
                document_id=document.id,
                uploaded_by=uploaded_by,
                version_number=version_number,
                storage_path=storage_path,
                file_size_bytes=spooled.file_size_bytes,
                checksum_sha256=spooled.checksum_sha256,
                is_current=True,
            )

            # 4) documents.current_version_id
            document.current_version_id = version.id
            await self._session.flush()

            # 5) pipeline_runs pending
            run = await self._pipeline.create_run(version.id)

            # Single DB transaction boundary (request session commits after enqueue prep)
            await self._session.commit()
        except Exception:
            if storage_path is not None:
                self._storage.delete_object(storage_path)
            raise
        finally:
            spooled.stream.close()

        self._enqueue_pipeline(run.id)
        return UploadResult(document=document, version=version, pipeline_run=run)

    async def upload_new_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        filename: str,
        file_chunks: AsyncIterator[bytes],
    ) -> UploadResult:
        document = await self.get_document(workspace_id, document_id)
        file_type = detect_file_type(filename)
        if file_type != document.file_type:
            raise DocumentIngestionError(
                "file_type_mismatch",
                f"Expected {document.file_type.value}, got {file_type.value}",
                status_code=400,
            )

        spooled = await hash_upload_stream(file_chunks)
        storage_path: str | None = None

        try:
            version_number = await self._docs.next_version_number(document.id)
            storage_path = build_storage_path(
                workspace_id=workspace_id,
                document_id=document.id,
                version_number=version_number,
                filename=filename,
            )

            self._storage.upload_stream(
                object_key=storage_path,
                stream=spooled.stream,
                length=spooled.file_size_bytes,
                content_type=CONTENT_TYPES[file_type],
            )

            # Flip is_current atomically within the same transaction
            await self._docs.clear_current_flags(document.id)
            version = await self._docs.create_version(
                document_id=document.id,
                uploaded_by=uploaded_by,
                version_number=version_number,
                storage_path=storage_path,
                file_size_bytes=spooled.file_size_bytes,
                checksum_sha256=spooled.checksum_sha256,
                is_current=True,
            )
            document.current_version_id = version.id
            await self._session.flush()

            run = await self._pipeline.create_run(version.id)
            await self._session.commit()
        except Exception:
            if storage_path is not None:
                self._storage.delete_object(storage_path)
            raise
        finally:
            spooled.stream.close()

        self._enqueue_pipeline(run.id)
        return UploadResult(document=document, version=version, pipeline_run=run)

    async def set_current_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> Document:
        document = await self.get_document(workspace_id, document_id)
        version = await self.get_version(workspace_id, document_id, version_id)
        if version.status != DocumentVersionStatus.ready:
            raise DocumentIngestionError(
                "version_not_ready",
                (
                    f"Cannot set-current: version status is '{version.status.value}', "
                    "only versions with status 'ready' can become current"
                ),
                status_code=400,
            )
        return await self._docs.set_current_version(document, version)

    async def get_pipeline_status(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PipelineRun:
        await self.get_version(workspace_id, document_id, version_id)
        run = await self._pipeline.get_latest_run_with_stages(version_id)
        if run is None:
            raise DocumentIngestionError(
                "not_found",
                "No pipeline run found for this version",
                status_code=404,
            )
        return run

    def _enqueue_pipeline(self, pipeline_run_id: uuid.UUID) -> None:
        if not self._enqueue:
            return
        # Late import avoids circular import with Celery app at module load.
        from app.workers.pipeline import run_pipeline

        run_pipeline.delay(str(pipeline_run_id))
        logger.info("pipeline_enqueued", pipeline_run_id=str(pipeline_run_id))


def _viewer_kind_from_preview(version: DocumentVersion) -> str:
    if (
        version.preview_status == PreviewStatus.completed
        and version.preview_file_path
        and (version.preview_type is None or version.preview_type.value == "pdf")
    ):
        return "pdf"
    return "original_download"


def _match_bbox(
    layout_blocks: list[dict[str, Any]],
    row: ChunkHydrationRow,
) -> list[float] | None:
    """Best-effort bbox from layout blocks on the same page with text overlap."""
    if not layout_blocks:
        return None
    snippet = (row.content or "").strip()
    if len(snippet) < 12:
        return None
    needle = snippet[:80].lower()
    page = row.page_number
    best: list[float] | None = None
    best_score = 0
    for block in layout_blocks:
        if page is not None and block.get("page_number") not in (None, page):
            continue
        text = str(block.get("text") or block.get("content") or "").lower()
        if not text:
            continue
        if needle not in text and text[:40] not in needle:
            continue
        bbox = block.get("bbox")
        if not isinstance(bbox, list) or len(bbox) < 4:
            continue
        try:
            coords = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
        except (TypeError, ValueError):
            continue
        score = len(text)
        if score > best_score:
            best_score = score
            best = coords
    return best
