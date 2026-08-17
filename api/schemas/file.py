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


__all__ = ["ChunkEmbedding", "ChunkResult"]
