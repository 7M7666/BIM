from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import re

import pymupdf


class PDFParseError(ValueError):
    """Raised when an uploaded PDF cannot be parsed."""


@dataclass(frozen=True, slots=True)
class DrawingPage:
    page_number: int
    text: str
    sheet_title: str | None = None
    drawing_number: str | None = None


def sheet_identity(text: str) -> tuple[str | None, str | None]:
    # Revit titleblock text follows its print timestamp and precedes the project number.
    match = re.search(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\s*\n(.{1,120}?)\n\d{2,}[-\w]*\n", text, re.S)
    if not match:
        return None, None
    title = " ".join(match[1].split())
    tail = text[match.end():].splitlines()[:8]
    numbers = [line.strip() for line in tail if re.fullmatch(r"[A-Z]{1,3}\d{3,}(?:[-.]\d+)?", line.strip())]
    return title, numbers[0] if len(numbers) == 1 else None


@dataclass(frozen=True, slots=True)
class DrawingDocument:
    file_name: str
    pages: tuple[DrawingPage, ...]
    metadata: Mapping[str, str]
    source_bytes: bytes

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def has_text_layer(self) -> bool:
        return any(page.text.strip() for page in self.pages)


class PyMuPDFParser:
    def parse(self, path: Path) -> DrawingDocument:
        try:
            source_bytes = path.read_bytes()
        except OSError as error:
            raise PDFParseError(f"Cannot read PDF '{path}': {error}") from error
        return self.parse_bytes(source_bytes, file_name=path.name)

    def parse_bytes(
        self,
        source_bytes: bytes,
        *,
        file_name: str,
    ) -> DrawingDocument:
        try:
            with pymupdf.open(stream=source_bytes, filetype="pdf") as document:
                pages = tuple(
                    DrawingPage(
                        page_number=index + 1,
                        text=page.get_text("text"),
                        sheet_title=sheet_identity(page.get_text("text"))[0],
                        drawing_number=sheet_identity(page.get_text("text"))[1],
                    )
                    for index, page in enumerate(document)
                )
                metadata = {
                    key: value
                    for key, value in (document.metadata or {}).items()
                    if isinstance(key, str)
                    and isinstance(value, str)
                    and value.strip()
                }
        except (RuntimeError, ValueError) as error:
            raise PDFParseError(
                f"Cannot parse PDF '{file_name}': {error}"
            ) from error

        return DrawingDocument(
            file_name=file_name,
            pages=pages,
            metadata=metadata,
            source_bytes=source_bytes,
        )

    def render_page(
        self,
        document: DrawingDocument,
        page_number: int,
        *,
        scale: float = 1.5,
    ) -> bytes:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError(
                f"Page number must be between 1 and {document.page_count}."
            )
        try:
            with pymupdf.open(
                stream=document.source_bytes,
                filetype="pdf",
            ) as source:
                page = source.load_page(page_number - 1)
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale),
                    alpha=False,
                )
                return pixmap.tobytes("png")
        except (RuntimeError, ValueError) as error:
            raise PDFParseError(
                f"Cannot render page {page_number} from "
                f"'{document.file_name}': {error}"
            ) from error


def search_drawing_text(
    document: DrawingDocument,
    query_term: str,
) -> tuple[DrawingPage, ...]:
    normalized_term = query_term.strip().casefold()
    if not normalized_term:
        return ()
    return tuple(
        page
        for page in document.pages
        if normalized_term in page.text.casefold()
    )
