from app.rag.chunking import chunk_text


def test_short_paragraphs_are_kept_in_order_and_whitespace_is_filtered():
    assert chunk_text("  first  \n\n \nsecond\nthird  ", chunk_size=10, chunk_overlap=2) == [
        "first",
        "second",
        "third",
    ]


def test_long_paragraph_has_requested_size_and_overlap():
    chunks = chunk_text("abcdefghij", chunk_size=6, chunk_overlap=2)

    assert chunks == ["abcdef", "efghij"]
    assert chunks[0][-2:] == chunks[1][:2]


def test_long_paragraph_produces_stable_order_with_last_short_chunk():
    chunks = chunk_text("abcdefghijklmnop", chunk_size=6, chunk_overlap=2)

    assert chunks == ["abcdef", "efghij", "ijklmn", "mnop"]


def test_invalid_chunk_configuration_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=4, chunk_overlap=4)
