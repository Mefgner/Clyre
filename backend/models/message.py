from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship, mapped_column

from models.base import Base, IdMixin


class Message(Base, IdMixin):
    __tablename__ = "message"

    hash = mapped_column(String(64), nullable=False, index=True)
    inline_value = mapped_column(Text, nullable=True)
    role = mapped_column(String(30), nullable=False)

    user_id = mapped_column(String(36), ForeignKey("user.id"), nullable=False, index=True)
    thread_id = mapped_column(String(36), ForeignKey("thread.id"), nullable=False, index=True)

    order = mapped_column("order", Integer, nullable=False, quote=True)

    user = relationship("User", back_populates="messages")
    thread = relationship("Thread", back_populates="messages")
