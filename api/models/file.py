from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import mapped_column, relationship

from models import Base


class FileMetadata(Base):
    __tablename__ = "file_metadata"

    user_id = mapped_column(String(36), ForeignKey("user.id"), nullable=False, index=True)
    name = mapped_column(String(255), nullable=False)
    content_type = mapped_column(String(255), nullable=False)
    # Short text preview (first chars of decoded content) for UI hover; NULL for
    # binary or non-decodable files.
    head_value = mapped_column(String(128), nullable=True)
    creation_date = mapped_column(Date, nullable=True)
    # NULL until the file is linked into a project's index — only then is it embedded.
    project_id = mapped_column(String(36), nullable=True, index=True)
    index_status = mapped_column(String(16), nullable=False, default="not_indexed", index=True)
    index_error = mapped_column(Text, nullable=True)
    indexed_at = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="files")
    thread_links = relationship(
        "FileHasThread", back_populates="file", cascade="all, delete-orphan"
    )
    project_links = relationship(
        "FileHasProject", back_populates="file", cascade="all, delete-orphan"
    )
    chunks = relationship("ChunkVector", back_populates="file", cascade="all, delete-orphan")


class FileHasThread(Base):
    __tablename__ = "file_has_thread"

    file_id = mapped_column(
        String(36), ForeignKey("file_metadata.id", ondelete="CASCADE"), primary_key=True
    )
    thread_id = mapped_column(
        String(36), ForeignKey("thread.id", ondelete="CASCADE"), primary_key=True
    )

    file = relationship("FileMetadata", back_populates="thread_links")
    thread = relationship("Thread", back_populates="file_links")


class FileHasProject(Base):
    __tablename__ = "file_has_project"

    file_id = mapped_column(
        String(36), ForeignKey("file_metadata.id", ondelete="CASCADE"), primary_key=True
    )
    project_id = mapped_column(
        String(36), ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )

    file = relationship("FileMetadata", back_populates="project_links")
    project = relationship("Project", back_populates="file_links")


class ChunkVector(Base):
    __tablename__ = "chunk_vector"

    # Metadata only. The embedding itself is owned by VectorRepository (pgvector
    # column / sqlite-vec virtual table) keyed by this row's id, so the relational
    # schema builds identically on SQLite and Postgres.
    file_id = mapped_column(
        String(36),
        ForeignKey("file_metadata.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = mapped_column(Integer, nullable=False)
    token_count = mapped_column(Integer, nullable=False)
    file_content_offset = mapped_column(Integer, nullable=False)
    file_content_length = mapped_column(Integer, nullable=False)

    file = relationship("FileMetadata", back_populates="chunks")


__all__ = [
    "FileMetadata",
    "FileHasThread",
    "FileHasProject",
    "ChunkVector",
]
