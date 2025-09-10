from sqlalchemy.testing.schema import mapped_column

from base import Base
from sqlalchemy import String
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

class TelegramConnection(Base):
    __tablename__ = 'telegram_users'

    id = mapped_column(String(36), primary_key=True, autoincrement=True)
    telegram_id = mapped_column(Integer, unique=True, nullable=False, index=True)
    user_id = mapped_column(String, ForeignKey('users.id'), nullable=False)

    user = relationship("User", back_populates="telegram_connections")