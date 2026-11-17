"""Turn an uploaded file into text segments. Each segment carries a locator (page, sheet, rows, ...)
so answers can point back to where the text came from.

Segments are yielded lazily so large spreadsheets and PDFs never have to fit in memory at once.
"""
import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from src.rag.errors import PermanentError

logger = logging.getLogger(__name__)

TEXT_EXTS = {".txt", ".md", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_EXTS = {".pdf", ".docx", ".xlsx"} | TEXT_EXTS | IMAGE_EXTS

ROWS_PER_SEGMENT = 50
MAX_PIXELS = 40_000_000  # reject decompression bombs before OCR


@dataclass
class Segment:
    text: str
    locator: dict = field(default_factory=dict)


def supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTS


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1258", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PermanentError("unreadable_text_encoding")


def _pdf_segments(path: str, max_pages: int) -> Iterator[Segment]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt("")
    except Exception as exc:
        raise PermanentError("invalid_or_encrypted_pdf") from exc
    if len(reader.pages) == 0:
        raise PermanentError("empty_pdf")
    if len(reader.pages) > max_pages:
        raise PermanentError("too_many_pages")
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:
            logger.warning("Skipping unreadable PDF page %d: %s", number, exc)
            continue
        if text:
            yield Segment(text, {"page": number})


def _text_segments(path: str) -> Iterator[Segment]:
    data = Path(path).read_bytes()
    text = _decode_text(data)
    if Path(path).suffix.lower() == ".csv":
        rows = list(csv.reader(io.StringIO(text)))
        header = rows[0] if rows else []
        for start in range(0, len(rows), ROWS_PER_SEGMENT):
            block = rows[start:start + ROWS_PER_SEGMENT]
            lines = [" | ".join(f"{h}: {v}" for h, v in zip(header, row)) if header else " | ".join(row)
                     for row in block]
            yield Segment("\n".join(lines), {"rows": f"{start + 1}-{start + len(block)}"})
        return
    # Plain text and markdown: one segment per ~2000 characters, split on blank lines.
    buffer, size = [], 0
    for paragraph in text.split("\n\n"):
        buffer.append(paragraph)
        size += len(paragraph)
        if size >= 2000:
            yield Segment("\n\n".join(buffer), {})
            buffer, size = [], 0
    if buffer and any(p.strip() for p in buffer):
        yield Segment("\n\n".join(buffer), {})


def _docx_segments(path: str) -> Iterator[Segment]:
    import docx

    try:
        document = docx.Document(path)
    except Exception as exc:
        raise PermanentError("invalid_docx") from exc
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                paragraphs.append(" | ".join(cells))
    for start in range(0, len(paragraphs), ROWS_PER_SEGMENT):
        block = paragraphs[start:start + ROWS_PER_SEGMENT]
        yield Segment("\n".join(block), {"paragraphs": f"{start + 1}-{start + len(block)}"})


def _xlsx_segments(path: str) -> Iterator[Segment]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise PermanentError("invalid_xlsx") from exc
    try:
        for sheet in workbook.worksheets:
            header = None
            block, start = [], 1
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = ["" if v is None else str(v) for v in row]
                if not any(values):
                    continue
                if header is None:
                    header = values
                    continue
                if not block:
                    start = row_number
                block.append(" | ".join(f"{h}: {v}" for h, v in zip(header, values) if v))
                if len(block) >= ROWS_PER_SEGMENT:
                    yield Segment("\n".join(block), {"sheet": sheet.title, "rows": f"{start}-{row_number}"})
                    block = []
            if block:
                yield Segment("\n".join(block), {"sheet": sheet.title, "rows": f"{start}-end"})
    finally:
        workbook.close()


def _image_segments(path: str, ocr_langs: str) -> Iterator[Segment]:
    from PIL import Image
    import pytesseract

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image.convert("RGB"), lang=ocr_langs).strip()
    except Image.DecompressionBombError as exc:
        raise PermanentError("image_too_large") from exc
    except Exception as exc:
        raise PermanentError("invalid_image") from exc
    if not text:
        raise PermanentError("no_text_in_image")
    yield Segment(text, {"image": Path(path).name})


def iter_segments(path: str, filename: str, max_pages: int, ocr_langs: str) -> Iterator[Segment]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _pdf_segments(path, max_pages)
    if ext in TEXT_EXTS:
        return _text_segments(path)
    if ext == ".docx":
        return _docx_segments(path)
    if ext == ".xlsx":
        return _xlsx_segments(path)
    if ext in IMAGE_EXTS:
        return _image_segments(path, ocr_langs)
    raise PermanentError("unsupported_file_type")
