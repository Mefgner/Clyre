import uuid

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    pass


class IdMixin:
    id = mapped_column(
        String(36), primary_key=True, unique=True,
        nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
