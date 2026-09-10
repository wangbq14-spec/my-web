import re

from app.core.config import settings


def chunk_text(
    text: str,
    chunk_size: int = settings.RAG_CHUNK_SIZE,
    chunk_overlap: int = settings.RAG_CHUNK_OVERLAP,
) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    chunks: list[str] = []
    for paragraph in re.split(r"\r?\n+", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= chunk_size:
            chunks.append(paragraph)
            continue

        start = 0
        step = chunk_size - chunk_overlap
        while start < len(paragraph):
            chunk = paragraph[start : start + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
            if start + chunk_size >= len(paragraph):
                break
            start += step
    return chunks
