from pathlib import Path

from app.rag.parsers.base import ParsedDocument, ParserError
from app.rag.parsers.pdf import parse_pdf
from app.rag.parsers.text import parse_text


def parse_document(path: Path, suffix: str) -> ParsedDocument:
    normalised_suffix = suffix.lower()
    if normalised_suffix in {".txt", ".md"}:
        return parse_text(path)
    if normalised_suffix == ".pdf":
        return parse_pdf(path)
    raise ParserError("不支持的文件类型")
