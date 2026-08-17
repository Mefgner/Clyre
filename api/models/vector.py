from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import mapped_column

from models import Base


class VectorIndexMeta(Base):
    # Singleton row: identity of the embedding space every stored vector shares.
    # Vectors from different embedders are mutually incomparable, so a config
    # change must trigger a full re-embed rather than mixing spaces silently.
    __tablename__ = "vector_index_meta"

    embedding_model = mapped_column(String(255), nullable=False)
    embedding_dim = mapped_column(Integer, nullable=False)
    normalized = mapped_column(Boolean, nullable=False)
    updated_at = mapped_column(DateTime, nullable=False, server_default=func.now())


__all__ = ["VectorIndexMeta"]
