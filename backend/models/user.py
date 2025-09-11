from models.base import Base, IdMixin
from sqlalchemy import String
from sqlalchemy.orm import mapped_column, relationship

class User(Base, IdMixin):
    __tablename__ = "user"

    name = mapped_column(String(90), nullable=False)
    nickname = mapped_column(String(30), nullable=True)
    email = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash = mapped_column(String(100), nullable=False)

    telegram_connections = relationship("TelegramConnection", back_populates="user", cascade="all, delete-orphan")

    files = relationship("File", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")

    user_roles = relationship("RoleHasUser", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("Role", secondary="role_has_user", back_populates="users")
