from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import mapped_column, relationship

from . import Base


class Role(Base):
    __tablename__ = "role"

    name = mapped_column(String(45), nullable=False, index=True)
    privilege_level = mapped_column(Integer, nullable=False)

    users = relationship(
        "User", secondary="role_has_user", back_populates="roles", overlaps="user_roles"
    )
    user_roles = relationship(
        "RoleHasUser",
        back_populates="role",
        cascade="all, delete-orphan",
        overlaps="user",
    )


class RoleHasUser(Base):
    __tablename__ = "role_has_user"

    role_id = mapped_column(String(36), ForeignKey("role.id"), primary_key=True)
    user_id = mapped_column(String(36), ForeignKey("user.id"), primary_key=True)

    role = relationship("Role", back_populates="user_roles")
    user = relationship("User", back_populates="user_roles")


__all__ = ["Role", "RoleHasUser"]
