import io
from unittest.mock import MagicMock, patch

import docx

from parsing.extract import extract_text_from_docx, extract_text_from_pdf


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_extract_text_from_docx_real_document():
    raw = _build_docx_bytes(["Jane Doe", "Senior Backend Engineer", "Built payment systems at scale"])
    text = extract_text_from_docx(raw)
    assert "Jane Doe" in text
    assert "Senior Backend Engineer" in text
    assert "Built payment systems at scale" in text


def test_extract_text_from_docx_skips_empty_paragraphs():
    raw = _build_docx_bytes(["Real line", "", "   ", "Another real line"])
    text = extract_text_from_docx(raw)
    lines = [line for line in text.split("\n") if line.strip()]
    assert lines == ["Real line", "Another real line"]


def test_extract_text_from_docx_empty_document_returns_empty_string():
    raw = _build_docx_bytes([])
    assert extract_text_from_docx(raw) == ""


# PDF cases mock pdfplumber.open at the boundary: building a byte-correct real PDF
# fixture by hand is fragile (xref tables, content streams) and not worth the
# flakiness for testing OUR join/skip logic, which is what these actually verify.
# A real sample-resume PDF fixture should be added once one exists in the repo.


def test_extract_text_from_pdf_joins_multiple_pages():
    page1 = MagicMock()
    page1.extract_text.return_value = "Page one text"
    page2 = MagicMock()
    page2.extract_text.return_value = "Page two text"

    mock_pdf = MagicMock()
    mock_pdf.pages = [page1, page2]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False

    with patch("parsing.extract.pdfplumber.open", return_value=mock_pdf):
        text = extract_text_from_pdf(b"fake-pdf-bytes")

    assert "Page one text" in text
    assert "Page two text" in text


def test_extract_text_from_pdf_skips_pages_with_no_extractable_text():
    page1 = MagicMock()
    page1.extract_text.return_value = "Has text"
    page2 = MagicMock()
    page2.extract_text.return_value = None  # scanned/image-only page

    mock_pdf = MagicMock()
    mock_pdf.pages = [page1, page2]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False

    with patch("parsing.extract.pdfplumber.open", return_value=mock_pdf):
        text = extract_text_from_pdf(b"fake-pdf-bytes")

    assert text.strip() == "Has text"
