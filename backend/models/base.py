from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, mapped_column

from utils import hashing


class Base(DeclarativeBase):
    __abstract__ = True

    id = mapped_column(
        String(36),
        primary_key=True,
        unique=True,
        nullable=False,
        index=True,
        default=hashing.generate_uuid,
    )


__all__ = ["Base"]
