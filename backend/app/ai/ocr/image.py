# =============================================================================
# File: image.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Optional Tesseract image OCR for scanned PDFs (OCR P3).
# Responsibilities:
#   - Render PDF pages via PyMuPDF → Tesseract text when no text layer
#   - Auto-detect Windows Tesseract install + tessdata; only when ENABLE_IMAGE_OCR
# Dependencies:
#   - PyMuPDF, pytesseract, Pillow, system Tesseract binary
#   - app.core.config.Settings
# Public Exports:
#   - parse_pdf_via_image_ocr, image_ocr_available, configure_tesseract
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Default OFF — does not change production behavior until enabled.
# =============================================================================

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings

_WINDOWS_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def image_ocr_available() -> bool:
    """True when Python packages for image OCR import successfully."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def configure_tesseract(settings: Settings | None = None) -> str:
    """Resolve tesseract binary + tessdata; configure pytesseract.

    Returns:
        Absolute path to ``tesseract`` executable.

    Raises:
        ValueError: Binary not found on PATH or known install locations.
    """
    import pytesseract

    from app.core.config import get_settings

    cfg = settings or get_settings()
    cmd = _resolve_tesseract_cmd(cfg.tesseract_cmd)
    # Real package: pytesseract.pytesseract.tesseract_cmd; tolerate flat mocks in tests.
    target = getattr(pytesseract, "pytesseract", pytesseract)
    setattr(target, "tesseract_cmd", cmd)

    tessdata = _resolve_tessdata_prefix(cfg.tessdata_prefix, cmd)
    if tessdata is not None:
        os.environ["TESSDATA_PREFIX"] = str(tessdata)

    return cmd


def _resolve_tesseract_cmd(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return str(path)
        raise ValueError(f"TESSERACT_CMD does not point to a file: {explicit}")

    which = shutil.which("tesseract")
    if which:
        return which

    for candidate in _WINDOWS_TESSERACT_CANDIDATES:
        if candidate.is_file():
            return str(candidate)

    raise ValueError(
        "ENABLE_IMAGE_OCR=true but the Tesseract binary was not found on PATH. "
        "Install Tesseract OCR (e.g. winget install UB-Mannheim.TesseractOCR) "
        "or set TESSERACT_CMD to the full path of tesseract.exe."
    )


def _resolve_tessdata_prefix(explicit: str | None, tesseract_cmd: str) -> Path | None:
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            return path
        raise ValueError(f"TESSDATA_PREFIX is not a directory: {explicit}")

    # Prefer user override with eng+vie packs when present.
    local = Path.home() / "AppData" / "Local" / "Tesseract-OCR" / "tessdata"
    if local.is_dir() and (local / "eng.traineddata").is_file():
        return local

    sibling = Path(tesseract_cmd).resolve().parent / "tessdata"
    if sibling.is_dir() and (sibling / "eng.traineddata").is_file():
        return sibling

    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix:
        path = Path(env_prefix)
        if path.is_dir():
            return path
    return None


def parse_pdf_via_image_ocr(
    data: bytes,
    *,
    settings: Settings | None = None,
    parsed_block_cls: type[Any],
) -> tuple[list[Any], int]:
    """OCR each PDF page as an image; return ``(blocks, page_count)``.

    Args:
        data: Raw PDF bytes.
        settings: App settings (ENABLE_IMAGE_OCR must already be true).
        parsed_block_cls: ``_ParsedBlock`` class from ``app.ai.ocr``.

    Raises:
        ValueError: Missing deps, Tesseract failure, or unreadable PDF.
    """
    import fitz  # PyMuPDF

    from app.core.config import get_settings

    cfg = settings or get_settings()
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise ValueError(
            "ENABLE_IMAGE_OCR=true but pytesseract/Pillow are not installed. "
            f"Install backend requirements and system Tesseract. Detail: {exc}"
        ) from exc

    try:
        configure_tesseract(cfg)
    except ValueError:
        raise

    lang = _resolve_ocr_lang(cfg.image_ocr_lang)

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Failed to open PDF for image OCR: {exc}") from exc

    blocks: list[Any] = []
    try:
        page_count = len(doc)
        if page_count == 0:
            return [], 0

        zoom = max(cfg.image_ocr_dpi, 72) / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        limit = min(page_count, max(cfg.image_ocr_max_pages, 1))

        for page_no in range(1, limit + 1):
            page = doc[page_no - 1]
            try:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
            except Exception as exc:
                raise ValueError(
                    f"Failed to render PDF page {page_no} for image OCR: {exc}"
                ) from exc

            try:
                text = pytesseract.image_to_string(
                    image,
                    lang=lang,
                    timeout=cfg.image_ocr_timeout_seconds,
                )
            except pytesseract.TesseractNotFoundError as exc:
                raise ValueError(
                    "ENABLE_IMAGE_OCR=true but the Tesseract binary was not found "
                    "on PATH. Install Tesseract OCR on the worker host or set "
                    "TESSERACT_CMD."
                ) from exc
            except Exception as exc:
                raise ValueError(
                    f"Tesseract image OCR failed on PDF page {page_no}: {exc}"
                ) from exc

            body = (text or "").strip()
            if not body:
                continue
            blocks.append(
                parsed_block_cls(
                    text=body,
                    page_number=page_no,
                    section=None,
                    block_type="paragraph",
                )
            )
        return blocks, page_count
    finally:
        doc.close()


def _resolve_ocr_lang(requested: str) -> str:
    """Drop missing language packs so eng+vie degrades to eng when needed."""
    parts = [p.strip() for p in (requested or "eng").split("+") if p.strip()]
    if not parts:
        return "eng"

    prefix = os.environ.get("TESSDATA_PREFIX")
    if not prefix:
        return "+".join(parts)

    available: list[str] = []
    for code in parts:
        trained = Path(prefix) / f"{code}.traineddata"
        if trained.is_file():
            available.append(code)
    return "+".join(available) if available else "eng"
