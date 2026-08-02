# =============================================================================
# File: preview_generator.py
# Module/Service: Preview Generator (Document Ingestion)
# Layer: Service
# Purpose: Build Preview Representation (document.pdf) from Original file.
# Responsibilities:
#   - PDF → identity / copy as preview
#   - DOCX/PPTX/XLSX/TXT → LibreOffice convert-to-pdf, else text PDF fallback
#   - Persist preview_* columns; soft-fail so AI pipeline can continue
# Dependencies:
#   - MinioStorageAdapter, PyMuPDF, optional LibreOffice (soffice)
# Public Exports:
#   - PreviewGeneratorService, PreviewGenerateResult, PREVIEW_PDF_ARTIFACT
# Database/Table: document_versions (preview_*)
# Related Modules: app.workers.stages.preview_generation, Document Viewer
# Important Notes: Viewer never uses markdown; only preview when completed.
# =============================================================================

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import fitz

from app.adapters.minio_storage import MinioStorageAdapter
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.models.enums import FileType, PreviewStatus, PreviewType
from app.workers.artifacts import version_output_key
from app.workers.pipeline_errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)

PREVIEW_PDF_ARTIFACT = "document.pdf"
_SOFFICE_CANDIDATES = (
    "soffice",
    "libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


@dataclass(frozen=True)
class PreviewGenerateResult:
    preview_status: PreviewStatus
    preview_type: PreviewType | None
    preview_file_path: str | None
    engine: str
    error_message: str | None = None

    def as_metadata(self) -> dict[str, Any]:
        return {
            "preview_status": self.preview_status.value,
            "preview_type": self.preview_type.value if self.preview_type else None,
            "preview_file_path": self.preview_file_path,
            "engine": self.engine,
            "error_message": self.error_message,
        }


class PreviewGeneratorService:
    """Generate and persist Preview Representation for one document version."""

    def __init__(self, storage: MinioStorageAdapter) -> None:
        self._storage = storage

    def generate_for_version(self, document_version_id: UUID) -> PreviewGenerateResult:
        with get_sync_session() as session:
            version = session.get(DocumentVersion, document_version_id)
            if version is None:
                raise DataPipelineError(f"document_version not found: {document_version_id}")
            document = session.get(Document, version.document_id)
            if document is None:
                raise DataPipelineError(f"document not found for version: {document_version_id}")

            version.preview_status = PreviewStatus.processing
            version.preview_file_path = None
            version.preview_type = None
            version.preview_generated_at = None
            session.flush()

            storage_path = version.storage_path
            file_type = document.file_type
            session.expunge(document)
            session.expunge(version)

        try:
            raw = self._download(storage_path)
            pdf_bytes, engine = self._to_pdf_bytes(raw, file_type=file_type, filename=storage_path)
            preview_key = self._persist_preview(
                storage_path=storage_path,
                file_type=file_type,
                pdf_bytes=pdf_bytes,
            )
            result = PreviewGenerateResult(
                preview_status=PreviewStatus.completed,
                preview_type=PreviewType.pdf,
                preview_file_path=preview_key,
                engine=engine,
            )
        except TransientPipelineError:
            raise
        except Exception as exc:  # noqa: BLE001 — soft-fail preview; AI continues
            logger.exception(
                "preview_generation_failed",
                document_version_id=str(document_version_id),
            )
            result = PreviewGenerateResult(
                preview_status=PreviewStatus.failed,
                preview_type=None,
                preview_file_path=None,
                engine="none",
                error_message=str(exc)[:2000],
            )

        with get_sync_session() as session:
            version = session.get(DocumentVersion, document_version_id)
            if version is None:
                raise DataPipelineError(f"document_version not found: {document_version_id}")
            version.preview_status = result.preview_status
            version.preview_type = result.preview_type
            version.preview_file_path = result.preview_file_path
            version.preview_generated_at = (
                datetime.now(UTC) if result.preview_status == PreviewStatus.completed else None
            )
            session.flush()

        return result

    def _download(self, storage_path: str) -> bytes:
        try:
            return self._storage.download_bytes(storage_path)
        except Exception as exc:  # noqa: BLE001
            raise TransientPipelineError(
                f"Failed to download original for preview: {storage_path}"
            ) from exc

    def _persist_preview(
        self,
        *,
        storage_path: str,
        file_type: FileType,
        pdf_bytes: bytes,
    ) -> str:
        # PDF original: preview may alias the same object (no duplicate).
        if file_type == FileType.pdf:
            return storage_path

        preview_key = version_output_key(storage_path, PREVIEW_PDF_ARTIFACT)
        try:
            self._storage.upload_bytes(
                object_key=preview_key,
                data=pdf_bytes,
                content_type="application/pdf",
            )
        except Exception as exc:  # noqa: BLE001
            raise TransientPipelineError(
                f"Failed to upload preview PDF: {preview_key}"
            ) from exc
        return preview_key

    def _to_pdf_bytes(
        self,
        data: bytes,
        *,
        file_type: FileType,
        filename: str,
    ) -> tuple[bytes, str]:
        if file_type == FileType.pdf:
            # Validate PDF; return original bytes for alias path (not re-uploaded).
            try:
                doc = fitz.open(stream=data, filetype="pdf")
                doc.close()
            except Exception as exc:
                raise ValueError(f"Invalid PDF original: {exc}") from exc
            return data, "identity"

        suffix = Path(filename).suffix.lower() or f".{file_type.value}"
        loft = _try_libreoffice_convert(data, suffix=suffix)
        if loft is not None:
            return loft, "libreoffice"

        pages = _extract_text_pages(data, file_type=file_type)
        return _render_text_pdf(pages), "text_fallback"


def _find_soffice() -> str | None:
    env = os.environ.get("LIBREOFFICE_PATH") or os.environ.get("SOFFICE_PATH")
    if env and Path(env).exists():
        return env
    for candidate in _SOFFICE_CANDIDATES:
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate if Path(candidate).exists() else (shutil.which(candidate) or candidate)
    return None


def _try_libreoffice_convert(data: bytes, *, suffix: str) -> bytes | None:
    soffice = _find_soffice()
    if soffice is None:
        return None
    with tempfile.TemporaryDirectory(prefix="enlm-preview-") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / f"source{suffix}"
        src.write_bytes(data)
        # Each run needs its own profile; concurrent workers sharing the default
        # UserInstallation make soffice exit 1 without converting.
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "HOME": str(tmp_path),
            "SAL_DISABLE_JAVALDX": "1",
        }
        try:
            completed = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--nologo",
                    "--nolockcheck",
                    "--norestore",
                    "--nofirststartwizard",
                    f"-env:UserInstallation={profile_dir.as_uri()}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(src),
                ],
                check=False,
                capture_output=True,
                timeout=180,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("libreoffice_preview_unavailable", error=str(exc))
            return None
        if completed.returncode != 0:
            logger.warning(
                "libreoffice_preview_failed",
                returncode=completed.returncode,
                stderr=(completed.stderr or b"")[:500].decode("utf-8", errors="replace"),
            )
            return None
        pdfs = list(tmp_path.glob("*.pdf"))
        if not pdfs:
            return None
        return pdfs[0].read_bytes()


def _extract_text_pages(data: bytes, *, file_type: FileType) -> list[str]:
    """Best-effort text pages for fallback PDF (layout not preserved)."""
    if file_type == FileType.docx:
        from app.ai.ocr.docx_parser import _parse_docx

        blocks, _ = _parse_docx(data)
        return _blocks_to_pages(blocks, group_by="section")
    if file_type == FileType.pptx:
        from app.ai.ocr.pptx_parser import _parse_pptx

        blocks, _ = _parse_pptx(data)
        return _blocks_to_pages(blocks, group_by="page")
    if file_type == FileType.xlsx:
        from app.ai.ocr.xlsx_parser import _parse_xlsx

        blocks, _ = _parse_xlsx(data)
        return _blocks_to_pages(blocks, group_by="page")
    if file_type == FileType.txt:
        from app.ai.ocr.txt_parser import _parse_txt

        blocks, _ = _parse_txt(data)
        text = "\n\n".join(b.text for b in blocks if b.text)
        return [text] if text.strip() else ["(empty document)"]
    raise ValueError(f"Unsupported file type for preview: {file_type}")


def _blocks_to_pages(blocks: list[Any], *, group_by: str) -> list[str]:
    buckets: dict[int, list[str]] = {}
    for block in blocks:
        text = (getattr(block, "text", None) or "").strip()
        if not text:
            continue
        if group_by == "page":
            key = int(getattr(block, "page_number", None) or 1)
        else:
            key = int(getattr(block, "section_index", None) or 1)
        buckets.setdefault(key, []).append(text)
    if not buckets:
        return ["(empty document)"]
    return ["\n\n".join(buckets[k]) for k in sorted(buckets)]


def _render_text_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    try:
        for content in pages:
            page = doc.new_page(width=595, height=842)  # A4
            rect = fitz.Rect(48, 48, 547, 794)
            page.insert_textbox(
                rect,
                content[:12000],
                fontsize=10,
                fontname="helv",
                align=fitz.TEXT_ALIGN_LEFT,
            )
        return doc.tobytes()
    finally:
        doc.close()
