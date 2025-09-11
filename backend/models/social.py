from models.base import Base, IdMixin
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import relationship, mapped_column


class TelegramConnection(Base, IdMixin):
    __tablename__ = 'telegram_connection'

    telegram_id = mapped_column(Integer, unique=True, nullable=False, index=True)
    user_id = mapped_column(String(36), ForeignKey("user.id"), nullable=False)

    user = relationship("User", back_populates="telegram_connections")
