# email_handler.py

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramRetryAfter as RetryAfter
import smtplib
import re
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from database.storage import save_user_email, get_user_email
from config import get_smtp_config

# Получаем настройки
SMTP_CONFIG = get_smtp_config()
SMTP_SERVER = SMTP_CONFIG["server"]
SMTP_PORT = SMTP_CONFIG["port"]
EMAIL_ADDRESS = SMTP_CONFIG["address"]
EMAIL_PASSWORD = SMTP_CONFIG["password"]

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()


class EmailStates(StatesGroup):
    waiting_for_email = State()


def get_default_subject(files: list) -> str:
    """Возвращает тему по умолчанию в зависимости от типа файлов"""
    if not files:
        return "Файлы"

    has_document = False
    has_photo = False

    for file_path, file_name in files:
        ext = os.path.splitext(file_name)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            has_photo = True
        else:
            has_document = True

    if has_document and not has_photo:
        return "Документы"
    elif has_photo and not has_document:
        return "Медиафайлы"
    else:
        return "Медиафайлы и документы"


def is_valid_email(email: str) -> bool:
    """Проверяет, является ли строка корректным email адресом"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None


@router.message(F.text == "Готово")
async def cmd_ready(message: Message, state: FSMContext):
    """Обработчик кнопки 'Готово'"""
    data = await state.get_data()
    files = data.get("files", [])

    logger.info(f"cmd_ready: найдено {len(files)} файлов")

    if not files:
        await message.answer("⚠️ Вы не добавили ни одного файла.")
        return

    user_id = message.from_user.id
    last_email = await get_user_email(user_id)

    logger.info(f"Пользователь {user_id}, последний email: {last_email}")

    if last_email:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=last_email, callback_data=f"send:{last_email}")],
                [InlineKeyboardButton(text="Сменить адрес", callback_data="change_email")]
            ]
        )
        await message.answer(
            f"📧 Найдено {len(files)} файлов. Выберите email или введите новый:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            f"📧 Найдено {len(files)} файлов. Введите email для отправки:"
        )
        await state.set_state(EmailStates.waiting_for_email)
        logger.info(f"Установлено состояние waiting_for_email для {user_id}")


@router.callback_query(F.data.startswith("send:"))
async def send_files_with_saved_email(callback: CallbackQuery, state: FSMContext):
    """Отправка на сохранённый email"""
    email = callback.data.split(":")[1]
    await callback.message.answer(f"📧 Выбран email: {email}")
    await callback.answer()  # Закрываем callback

    # ✅ Явно вызываем отправку
    await process_email(callback.message, state, email)


@router.callback_query(F.data == "change_email")
async def change_email(callback: CallbackQuery, state: FSMContext):
    """Смена email"""
    await callback.message.answer("📧 Введите новый email для отправки:")
    await state.set_state(EmailStates.waiting_for_email)
    await callback.answer()
    logger.info(f"Пользователь хочет сменить email")


@router.message(EmailStates.waiting_for_email)
async def process_email_input(message: Message, state: FSMContext):
    """Обработка введённого email"""
    email = message.text.strip()
    user_id = message.from_user.id

    logger.info(f"Получен email от {user_id}: {email}")

    if not is_valid_email(email):
        await message.answer(
            "⚠️ Некорректный email. Пример: user@example.com\n"
            "Пожалуйста, введите правильный email адрес."
        )
        return

    # Сохраняем email в БД
    await save_user_email(user_id, email)
    logger.info(f"Email {email} сохранён для {user_id}")

    # ✅ ВАЖНО: сбрасываем состояние перед отправкой
    await state.set_state(None)

    # Отправляем файлы
    await process_email(message, state, email)


async def process_email(message: Message, state: FSMContext, recipient_email: str):
    """Основная функция отправки файлов"""
    data = await state.get_data()
    files = data.get("files", [])
    user_subject = data.get("subject")

    logger.info(f"process_email: {len(files)} файлов, тема: {user_subject}, получатель: {recipient_email}")

    if not files:
        await message.answer("❌ Ошибка: файлы не найдены. Попробуйте загрузить файлы заново.")
        return

    # Определяем тему
    if user_subject and user_subject.strip():
        email_subject = user_subject.strip()
        logger.info(f"Используем тему пользователя: {email_subject}")
    else:
        email_subject = get_default_subject(files)
        logger.info(f"Используем тему по умолчанию: {email_subject}")

    # Текст письма
    if user_subject and user_subject.strip():
        email_body = f"Тема: {user_subject}\n\nФайлы во вложении."
    else:
        email_body = f"{email_subject} во вложении."

    try:
        # Создаём письмо
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = recipient_email
        msg["Subject"] = email_subject
        msg.attach(MIMEText(email_body, "plain"))

        # Прикрепляем файлы
        for file_path, file_name in files:
            logger.info(f"Прикрепляем файл: {file_name} ({file_path})")
            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=file_name)
            part["Content-Disposition"] = f'attachment; filename="{file_name}"'
            msg.attach(part)

        # Отправляем
        logger.info(f"Подключаюсь к SMTP {SMTP_SERVER}:{SMTP_PORT}")
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(msg["From"], recipient_email, msg.as_string())
            logger.info("Письмо отправлено успешно!")

        # Удаляем временные файлы
        for file_path, _ in files:
            try:
                os.remove(file_path)
                logger.info(f"Удалён файл: {file_path}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {file_path}: {e}")

        await message.answer(
            f"✅ Файлы успешно отправлены!\n"
            f"📝 Тема: \"{email_subject}\"\n"
            f"📧 Получатель: {recipient_email}"
        )

    except Exception as e:
        logger.error(f"Ошибка при отправке: {e}")
        await message.answer(f"❌ Ошибка при отправке: {e}")
    finally:
        # Очищаем состояние после отправки
        await state.clear()
        logger.info("Состояние очищено")