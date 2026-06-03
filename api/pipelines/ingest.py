from dataclasses import dataclass

_TEXT_EXTENSIONS = (".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".log", ".py")


@dataclass(slots=True)
class TextChunk:
    index: int
    text: str
    # Character offset/length into the source text — never bytes, so multibyte
    # content reslices correctly: text[offset:offset + length].
    offset: int
    length: int


class UnsupportedFileType(ValueError):
    pass


def extract_text(
    data: bytes, *, content_type: str | None = None, filename: str | None = None
) -> str:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if ctype.startswith("text/") or name.endswith(_TEXT_EXTENSIONS):
        return data.decode("utf-8", errors="replace")
    raise UnsupportedFileType(content_type or filename or "unknown content type")


def chunk_text(text: str, *, chunk_size: int = 1500, overlap: int = 200) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    text_len = len(text)
    chunks: list[TextChunk] = []
    start = 0
    index = 0

    while start < text_len:
        end = min(start + chunk_size, text_len)
        # Prefer to cut on whitespace so a word is not split mid-token.
        if end < text_len:
            boundary = max(text.rfind(" ", start + 1, end), text.rfind("\n", start + 1, end))
            if boundary > start:
                end = boundary

        chunks.append(
            TextChunk(index=index, text=text[start:end], offset=start, length=end - start)
        )
        index += 1

        if end >= text_len:
            break
        start = max(end - overlap, start + 1)

    return chunks


__all__ = ["TextChunk", "UnsupportedFileType", "extract_text", "chunk_text"]
