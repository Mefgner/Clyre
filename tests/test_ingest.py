import pytest

from pipelines.ingest import TextChunk, UnsupportedFileType, chunk_text, extract_text


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []


def test_short_text_is_a_single_chunk():
    text = "a short document"
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0] == TextChunk(index=0, text=text, offset=0, length=len(text))


def test_offsets_reslice_to_chunk_text():
    text = " ".join(f"word{i}" for i in range(500))
    for c in chunk_text(text, chunk_size=120, overlap=30):
        assert text[c.offset : c.offset + c.length] == c.text
        assert c.length == len(c.text)


def test_chunks_cover_whole_text_without_gaps():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = chunk_text(text, chunk_size=120, overlap=30)
    assert chunks[0].offset == 0
    assert chunks[-1].offset + chunks[-1].length == len(text)
    # contiguous-with-overlap: each chunk starts no later than the previous end
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.offset <= prev.offset + prev.length


def test_indices_are_sequential():
    chunks = chunk_text(" ".join("x" * 1 for _ in range(2000)), chunk_size=100, overlap=20)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_consecutive_chunks_overlap():
    text = "x" * 1000  # no whitespace -> hard windows
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    for prev, nxt in zip(chunks, chunks[1:]):
        overlap_len = (prev.offset + prev.length) - nxt.offset
        assert overlap_len == 20


def test_multibyte_offsets_are_character_based():
    text = "Ñ" * 50 + " " + "ä" * 50 + " " + "я" * 50
    for c in chunk_text(text, chunk_size=40, overlap=10):
        assert text[c.offset : c.offset + c.length] == c.text


def test_invalid_params_raise():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=0)
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=10, overlap=10)
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=10, overlap=15)


def test_extract_text_decodes_text_like():
    assert extract_text("héllo".encode("utf-8"), filename="a.txt") == "héllo"
    assert extract_text(b"# title", content_type="text/markdown") == "# title"


def test_extract_text_rejects_unsupported():
    with pytest.raises(UnsupportedFileType):
        extract_text(b"%PDF-1.4", filename="a.pdf", content_type="application/pdf")
