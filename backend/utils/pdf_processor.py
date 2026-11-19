"""PDF/image intake helpers with safe per-page failure handling."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageStat

from backend.schemas import PageRecord


def _image_quality(image_bytes: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        width, height = image.size
        if width < 500 or height < 500:
            return "BLURRY_RESCAN_NEEDED"
        contrast = ImageStat.Stat(image).stddev[0]
        if contrast < 18:
            return "BLURRY_RESCAN_NEEDED"
        if width < 1000 or height < 1000 or contrast < 35:
            return "MEDIUM"
        return "HIGH"
    except (OSError, ValueError):
        return "BLURRY_RESCAN_NEEDED"


def pages_from_upload(filename: str, data: bytes, mime_type: str) -> list[PageRecord]:
    """Convert each supported upload into page records, preserving PDF text."""
    suffix = Path(filename).suffix.lower()
    result: list[PageRecord] = []
    if suffix == ".pdf":
        try:
            with fitz.open(stream=data, filetype="pdf") as document:
                for index, page in enumerate(document):
                    try:
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                        image_bytes = pixmap.tobytes("png")
                        result.append(PageRecord(
                            page_id=f"{filename}:{index + 1}",
                            filename=filename,
                            page_number=index + 1,
                            mime_type="image/png",
                            image_base64=base64.b64encode(image_bytes).decode("ascii"),
                            text=page.get_text("text").strip(),
                            quality=_image_quality(image_bytes),
                        ))
                    except (RuntimeError, ValueError, OSError) as exc:
                        result.append(PageRecord(
                            page_id=f"{filename}:{index + 1}",
                            filename=filename,
                            page_number=index + 1,
                            mime_type="application/octet-stream",
                            text="",
                            quality="BLURRY_RESCAN_NEEDED",
                            page_summary=f"Page rendering failed: {exc}",
                        ))
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise ValueError(f"{filename} is not a readable PDF: {exc}") from exc
    else:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            image = Image.open(io.BytesIO(data)).convert("RGB")
            output = io.BytesIO()
            image.save(output, format="PNG")
            png_bytes = output.getvalue()
            result.append(PageRecord(
                page_id=f"{filename}:1",
                filename=filename,
                page_number=1,
                mime_type="image/png",
                image_base64=base64.b64encode(png_bytes).decode("ascii"),
                quality=_image_quality(png_bytes),
            ))
        except (OSError, ValueError) as exc:
            raise ValueError(f"{filename} is not a readable image: {exc}") from exc
    return result
