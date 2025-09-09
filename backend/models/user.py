from models.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import mapped_column, relationship

class User(Base):
    __tablename__ = "user"

    id = mapped_column(Integer, primary_key=True, index=True)
    name = mapped_column(String(90), nullable=False)
    email = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash = mapped_column(String(255), nullable=False)

    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user")

    user_roles = relationship("RoleHasUser", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("Role", secondary="role_has_user", back_populates="users")
