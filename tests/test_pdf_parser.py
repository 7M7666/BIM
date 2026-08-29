from pathlib import Path

import pymupdf
import pytest

from bim_evidence_qa.parsers import PDFParseError, PyMuPDFParser, search_drawing_text


def _write_text_pdf(path: Path) -> None:
    document = pymupdf.open()
    document.set_metadata({"title": "Development Drawing"})
    page_1 = document.new_page()
    page_1.insert_text((72, 72), "Floor Plan - Room 101")
    page_2 = document.new_page()
    page_2.insert_text((72, 72), "Door Schedule - Door D101")
    document.save(path)
    document.close()


def test_pdf_is_parsed_with_real_page_text_and_metadata(tmp_path):
    path = tmp_path / "drawing.pdf"
    _write_text_pdf(path)

    drawing = PyMuPDFParser().parse(path)

    assert drawing.file_name == "drawing.pdf"
    assert drawing.page_count == 2
    assert [page.page_number for page in drawing.pages] == [1, 2]
    assert "Room 101" in drawing.pages[0].text
    assert "Door D101" in drawing.pages[1].text
    assert drawing.metadata["title"] == "Development Drawing"
    assert drawing.has_text_layer is True
    assert all(page.sheet_title is None for page in drawing.pages)


def test_pdf_page_render_returns_png_preview(tmp_path):
    path = tmp_path / "drawing.pdf"
    _write_text_pdf(path)
    parser = PyMuPDFParser()
    drawing = parser.parse(path)

    preview = parser.render_page(drawing, 2)

    assert preview.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(preview) > 100


def test_drawing_search_returns_only_pages_with_extracted_text(tmp_path):
    path = tmp_path / "drawing.pdf"
    _write_text_pdf(path)
    drawing = PyMuPDFParser().parse(path)

    assert [
        page.page_number for page in search_drawing_text(drawing, "room 101")
    ] == [1]
    assert [
        page.page_number for page in search_drawing_text(drawing, "DOOR")
    ] == [2]
    assert search_drawing_text(drawing, "Room 999") == ()


def test_pdf_without_text_does_not_fabricate_text(tmp_path):
    path = tmp_path / "image-only.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    drawing = PyMuPDFParser().parse(path)

    assert drawing.page_count == 1
    assert drawing.pages[0].text == ""
    assert drawing.has_text_layer is False
    assert search_drawing_text(drawing, "Room 101") == ()


def test_invalid_pdf_reports_a_real_parse_error():
    with pytest.raises(PDFParseError, match="Cannot parse PDF 'broken.pdf'"):
        PyMuPDFParser().parse_bytes(b"not a pdf", file_name="broken.pdf")
