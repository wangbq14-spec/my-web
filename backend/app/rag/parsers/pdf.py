from pathlib import Path

from pypdf import PdfReader

from app.rag.parsers.base import ParsedDocument, ParserError


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise ParserError("PDF 解析失败") from exc
    if not text:
        raise ParserError("PDF 无可用文本")
    return ParsedDocument(text=text, metadata={"page_count": len(reader.pages)})
