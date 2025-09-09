from models.base import Base
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import mapped_column, relationship


class Role(Base):
    __tablename__ = "role"

    id = mapped_column(Integer, primary_key=True, index=True)
    name = mapped_column(String(45), nullable=False, index=True)

    users = relationship("User", secondary="role_has_user", back_populates="roles")
    user_roles = relationship("RoleHasUser", back_populates="role", cascade="all, delete-orphan")


class RoleHasUser(Base):
    __tablename__ = "role_has_user"

    role_id = mapped_column(Integer, ForeignKey("role.id"), primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("user.id"), primary_key=True)

    role = relationship("Role", back_populates="user_roles")
    user = relationship("User", back_populates="user_roles")
