from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.rag.parsers.base import ParserError
from app.rag.parsers.factory import parse_document


def _pdf_with_text(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, object_data in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(object_data)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    output.extend(b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_parse_txt_and_markdown(tmp_path):
    txt_path = tmp_path / "notes.txt"
    markdown_path = tmp_path / "notes.md"
    txt_path.write_text("plain text", encoding="utf-8")
    markdown_path.write_text("# heading", encoding="utf-8")

    assert parse_document(txt_path, ".txt").text == "plain text"
    assert parse_document(markdown_path, ".MD").text == "# heading"


def test_parse_pdf_extracts_text(tmp_path):
    pdf_path = tmp_path / "text.pdf"
    pdf_path.write_bytes(_pdf_with_text("PDF content"))

    parsed = parse_document(pdf_path, ".pdf")

    assert parsed.text == "PDF content"
    assert parsed.metadata["page_count"] == 1


def test_parse_pdf_without_text_fails(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as stream:
        writer.write(stream)

    with pytest.raises(ParserError, match="PDF 无可用文本"):
        parse_document(pdf_path, ".pdf")


def test_parse_unsupported_suffix_fails(tmp_path):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"not a document")

    with pytest.raises(ParserError, match="不支持的文件类型"):
        parse_document(path, ".docx")
