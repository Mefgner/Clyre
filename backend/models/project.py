from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import mapped_column, relationship

from . import Base


class Project(Base):
    __tablename__ = "project"

    title = mapped_column(String(45), nullable=False)
    user_id = mapped_column(String(36), ForeignKey("user.id"), nullable=False, index=True)

    user = relationship("User", back_populates="projects")
    threads = relationship("Thread", back_populates="project", cascade="all, delete-orphan")

    file_links = relationship(
        "FileHasProject", back_populates="project", cascade="all, delete-orphan"
    )


__all__ = ["Project"]
