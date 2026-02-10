from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import mapped_column, relationship

from models import Base


class User(Base):
    __tablename__ = "user"

    local_connections = relationship(
        "LocalConnection", back_populates="user", cascade="all, delete-orphan"
    )
    # telegram_connections = relationship(
    #     "TelegramConnection", back_populates="user", cascade="all, delete-orphan"
    # )

    files = relationship("File", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")

    user_roles = relationship(
        "RoleHasUser", back_populates="user", cascade="all, delete-orphan"
    )
    roles = relationship("Role", secondary="role_has_user", back_populates="users")


class LocalConnection(Base):
    __tablename__ = "local_connection"

    user_id = mapped_column(String(36), ForeignKey("user.id"))
    name = mapped_column(String(75), nullable=False)
    email = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash = mapped_column(String(128), nullable=False)

    user = relationship("User", back_populates="local_connections")


# class TelegramConnection(Base):
#     __tablename__ = "telegram_connection"

#     user_id = mapped_column(String(50), ForeignKey("user.id"))
#     telegram_id = mapped_column(String(50), nullable=False, unique=True, index=True)
#     chat_id = mapped_column(String(50), nullable=False)

#     user = relationship("User", back_populates="telegram_connections")


__all__ = [
    "LocalConnection",
    # "TelegramConnection",
    "User",
]
