from io import BytesIO

from pypdf import PdfReader


def extract_pdf_bytes(data: bytes, max_pages: int = 12) -> str:
    reader = PdfReader(BytesIO(data))
    parts = []
    for i, page in enumerate(reader.pages[:max_pages]):
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def extract_pdf_path(path: str, max_pages: int = 20) -> str:
    reader = PdfReader(path)
    parts = []
    for i, page in enumerate(reader.pages[:max_pages]):
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()
