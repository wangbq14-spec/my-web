from pathlib import Path

from app.rag.parsers.base import ParsedDocument, ParserError


def parse_text(path: Path) -> ParsedDocument:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ParserError("文档编码无法识别") from exc
    except OSError as exc:
        raise ParserError("文档无法读取") from exc
    return ParsedDocument(text=text, metadata={})
