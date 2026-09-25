import io

import docx
import pdfplumber


def extract_text_from_pdf(file_bytes: bytes) -> str:
    lines = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()  # None on scanned/image-only pages
            if page_text:
                lines.append(page_text)
    return "\n".join(lines)


def extract_text_from_docx(file_bytes: bytes) -> str:
    document = docx.Document(io.BytesIO(file_bytes))
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n".join(lines)
