from sqlalchemy import Column, Integer, BigInteger, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime
import logging

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем базовый класс для моделей
Base = declarative_base()

class UserEmail(Base):
    __tablename__ = "user_emails"  # Исправлено название таблицы

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Логирование создания модели
logger.info("Модель UserEmail успешно определена.")
