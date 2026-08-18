from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import mapped_column, relationship

from models import Base
from utils import timing


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    __table_args__ = (
        Index("ix_refresh_token_user_revoked_expires", "user_id", "revoked_at", "expires_at"),
    )

    token_hash = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, default=timing.get_utc_now
    )
    expires_at = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


__all__ = ["RefreshToken"]
