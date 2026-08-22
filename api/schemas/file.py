from dataclasses import dataclass


@dataclass(slots=True)
class ChunkEmbedding:
    chunk_id: str
    project_id: str
    file_id: str
    embedding: list[float]


@dataclass(slots=True)
class ChunkResult:
    chunk_id: str
    file_id: str
    chunk_index: int
    file_content_offset: int
    file_content_length: int
    # Cosine distance: lower is closer. Results are ordered ascending.
    distance: float


@dataclass(slots=True)
class FileMeta:
    id: str
    name: str
    content_type: str
    head_value: str | None
    index_status: str


@dataclass(slots=True)
class ChunkText:
    chunk_id: str
    file_id: str
    chunk_index: int
    text: str


__all__ = ["ChunkEmbedding", "ChunkResult", "ChunkText", "FileMeta"]
