from base import Base
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import relationship, mapped_column


class TelegramConnection(Base):
    __tablename__ = 'telegram_users'

    id = mapped_column(String(36), primary_key=True, autoincrement=True)
    telegram_id = mapped_column(Integer, unique=True, nullable=False, index=True)
    user_id = mapped_column(String, ForeignKey('users.id'), nullable=False)

    user = relationship("User", back_populates="telegram_connections")
