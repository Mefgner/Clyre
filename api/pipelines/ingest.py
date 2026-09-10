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


class UndecodableFileText(ValueError):
    """Bytes claim a text type but are not strict UTF-8 or contain NUL."""

    def __init__(self, detail: str = "file is not valid UTF-8 text"):
        super().__init__(detail)


def normalize_content_type(content_type: str | None) -> str:
    """Lowercase MIME without parameters (\"text/plain; charset=utf-8\" -> \"text/plain\")."""
    return (content_type or "").split(";")[0].strip().lower()


def is_supported_text_type(content_type: str | None, filename: str | None) -> bool:
    ctype = normalize_content_type(content_type)
    if ctype.startswith("text/"):
        return True
    return (filename or "").lower().endswith(_TEXT_EXTENSIONS)


def extract_text(
    data: bytes, *, content_type: str | None = None, filename: str | None = None
) -> str:
    if not is_supported_text_type(content_type, filename):
        raise UnsupportedFileType(content_type or filename or "unknown content type")
    try:
        # utf-8-sig accepts and strips a BOM while rejecting invalid sequences.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UndecodableFileText("file is not valid UTF-8 text") from exc
    if "\x00" in text:
        raise UndecodableFileText("file contains NUL bytes and is not plain text")
    return text


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


__all__ = [
    "TextChunk",
    "UndecodableFileText",
    "UnsupportedFileType",
    "chunk_text",
    "extract_text",
    "is_supported_text_type",
    "normalize_content_type",
]
