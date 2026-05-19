# database/storage.py

import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete
from database.models import UserEmail, Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_base_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = get_base_path()
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, 'database.db')}"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"База данных: {os.path.join(BASE_DIR, 'database.db')}")


async def save_user_email(user_id: int, email: str):
    async with async_session() as session:
        user_email = UserEmail(user_id=user_id, email=email)
        session.add(user_email)
        await session.commit()

        result = await session.execute(
            select(UserEmail)
            .where(UserEmail.user_id == user_id)
            .order_by(UserEmail.created_at.desc())
        )
        all_emails = result.scalars().all()

        if len(all_emails) > 3:
            for email_record in all_emails[3:]:
                await session.delete(email_record)
            await session.commit()

        logger.info(f"Email {email} сохранён для {user_id}")


async def get_user_emails(user_id: int) -> list[str]:
    async with async_session() as session:
        result = await session.execute(
            select(UserEmail.email)
            .where(UserEmail.user_id == user_id)
            .order_by(UserEmail.created_at.desc())
            .limit(3)
        )
        return result.scalars().all()


async def get_last_user_email(user_id: int) -> str:
    emails = await get_user_emails(user_id)
    return emails[0] if emails else None


async def get_user_email(user_id: int) -> str:
    """Алиас для обратной совместимости"""
    return await get_last_user_email(user_id)


async def clear_user_emails(user_id: int):
    async with async_session() as session:
        await session.execute(delete(UserEmail).where(UserEmail.user_id == user_id))
        await session.commit()
        logger.info(f"Email для {user_id} удалены")

# database/storage.py (добавьте в конец файла)

async def get_unique_users_count() -> int:
    """Возвращает количество уникальных пользователей"""
    async with async_session() as session:
        result = await session.execute(
            select(UserEmail.user_id).distinct()
        )
        users = result.scalars().all()
        return len(users)


async def get_emails_count() -> int:
    """Возвращает общее количество сохранённых email"""
    async with async_session() as session:
        result = await session.execute(select(UserEmail))
        return len(result.scalars().all())