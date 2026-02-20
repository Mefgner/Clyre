from sqlalchemy import Date, TIMESTAMP, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import mapped_column, relationship

from models import Base


class Thread(Base):
    __tablename__ = "thread"

    title = mapped_column(String(90), nullable=True)
    user_id = mapped_column(String(36), ForeignKey("user.id"), nullable=False, index=True)
    stared = mapped_column(SmallInteger, nullable=True, default=0)
    in_project = mapped_column(SmallInteger, nullable=True, default=0)
    project_id = mapped_column(String(36), ForeignKey("project.id"), nullable=True, index=True)
    creation_date = mapped_column(Date, nullable=False, server_default=func.current_date())
    update_time = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    user = relationship("User", back_populates="threads")
    project = relationship("Project", back_populates="threads")

    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")
    file_links = relationship(
        "FileHasThread", back_populates="thread", cascade="all, delete-orphan"
    )


__all__ = ["Thread"]
