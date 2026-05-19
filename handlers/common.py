# common.py (исправленная версия)

import asyncio
import re
import smtplib
import logging
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from database.stats import stats_manager
from aiogram import Router, F
from aiogram.types import Message, ContentType, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, \
    InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.storage import save_user_email, get_user_emails, clear_user_emails
from config import get_smtp_config

# ==================== НАСТРОЙКИ ====================
router = Router()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SMTP настройки
SMTP_CONFIG = get_smtp_config()
SMTP_SERVER = SMTP_CONFIG["server"]
SMTP_PORT = SMTP_CONFIG["port"]
EMAIL_ADDRESS = SMTP_CONFIG["address"]
EMAIL_PASSWORD = SMTP_CONFIG["password"]

# Клавиатура
ready_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Готово")]],
    resize_keyboard=True,
)

# Папка для загрузок
UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# В начале файла, после импортов

# Хранилище для обработки медиагрупп
# Структура: {user_id: {"messages": [], "process_task": asyncio.Task, "last_update": float}}
user_pending_files = {}

# ==================== СОСТОЯНИЯ ====================
class EmailStates(StatesGroup):
    waiting_for_email = State()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None


def get_default_subject(files: list) -> str:
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


def extract_name_from_caption(caption: str) -> str:
    if not caption:
        return None
    match = re.search(r'([\w\-_]+\.(jpg|jpeg|png|gif|webp|bmp))', caption, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def get_photo_filename(message: Message) -> str:
    caption = message.caption
    extracted_name = extract_name_from_caption(caption)
    if extracted_name:
        return extracted_name
    if caption and caption.strip():
        clean_name = re.sub(r'[<>:"/\\|?*]', '_', caption.strip())
        clean_name = clean_name[:50]
        if clean_name:
            return f"{clean_name}.jpg"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"photo_{timestamp}.jpg"


def get_document_filename(message: Message) -> str:
    if message.document:
        return message.document.file_name
    return None


def get_unique_file_path(folder: str, filename: str) -> tuple:
    file_path = os.path.join(folder, filename)
    if os.path.exists(file_path):
        name_without_ext, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        new_filename = f"{name_without_ext}_{timestamp}{ext}"
        file_path = os.path.join(folder, new_filename)
        return file_path, new_filename
    return file_path, filename


# ==================== ОТПРАВКА EMAIL ====================
async def send_files_to_email(files: list, recipient_email: str, subject: str) -> bool:
    """Отправляет файлы на email. Возвращает True при успехе."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = recipient_email
        msg["Subject"] = subject if subject else get_default_subject(files)
        msg.attach(MIMEText(
            f"Тема: {subject}\n\nФайлы во вложении." if subject else f"{get_default_subject(files)} во вложении.",
            "plain"))

        for file_path, file_name in files:
            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=file_name)
            part["Content-Disposition"] = f'attachment; filename="{file_name}"'
            msg.attach(part)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(msg["From"], recipient_email, msg.as_string())

            # 👈 ДОБАВИТЬ СЧЁТЧИК ОТПРАВЛЕННЫХ ПИСЕМ (ПОСЛЕ УСПЕШНОЙ ОТПРАВКИ)
            stats_manager.add_email_sent()

        # Удаляем временные файлы
        for file_path, _ in files:
            try:
                os.remove(file_path)
            except:
                pass
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False

# ==================== ОБРАБОТКА МЕДИАГРУПП ====================


@router.message(Command("size"))
async def show_current_size(message: Message, state: FSMContext):
    """Показывает текущий общий размер файлов"""
    data = await state.get_data()
    files = data.get("files", [])

    if not files:
        await message.answer("📁 Нет загруженных файлов.")
        return

    total_size = sum(os.path.getsize(p) for p, _ in files)
    size_mb = total_size / (1024 * 1024)
    max_size = 10 * 1024 * 1024
    remaining_mb = (max_size - total_size) / (1024 * 1024) if total_size < max_size else 0

    status = "✅ В пределах лимита" if total_size <= max_size else "⚠️ ПРЕВЫШЕН ЛИМИТ!"

    await message.answer(
        f"📊 **Статус загруженных файлов**\n\n"
        f"📁 Количество файлов: {len(files)}\n"
        f"💾 Общий размер: {size_mb:.1f} МБ\n"
        f"📏 Лимит: 10 МБ\n"
        f"🔻 Осталось: {remaining_mb:.1f} МБ\n"
        f"📌 Статус: {status}\n\n"
        f"💡 Если лимит превышен, письмо может не доставиться."
    )

# ==================== ОБРАБОТЧИКИ ====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    stats_manager.add_user(user_id)  # 👈 ДОБАВИТЬ ЭТУ СТРОКУ

    await state.clear()
    await state.update_data(subject=None, files=[])
    await message.answer(
        "📤 Привет! Отправь мне фото или документы.\n"
        "📝 Если хочешь указать тему — напиши текст вместе с файлом или отдельно.\n"
        "Когда закончишь, нажми 'Готово'.",
        reply_markup=ready_keyboard,
    )

@router.message(Command("emails"))
async def show_saved_emails(message: Message):
    """Показывает последние 3 сохранённых email"""
    user_id = message.from_user.id
    emails = await get_user_emails(user_id)

    if emails:
        response = "📧 **Ваши сохранённые email адреса:**\n\n"
        for i, email in enumerate(emails, 1):
            response += f"{i}. {email}\n"
        response += f"\n💡 Всего сохранено: {len(emails)}/3"
        await message.answer(response)
    else:
        await message.answer(
            "📧 У вас пока нет сохранённых email адресов.\n"
            "Отправьте файлы и введите email — он сохранится автоматически.")


@router.message(Command("clearemails"))
async def clear_saved_emails(message: Message):
    """Очищает все сохранённые email пользователя"""
    user_id = message.from_user.id
    await clear_user_emails(user_id)
    await message.answer("🗑️ Все сохранённые email адреса удалены.")


@router.message(F.text == "Готово")
async def handle_ready(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])

    if not files:
        await message.answer("⚠️ Вы не добавили ни одного файла.")
        return

    user_id = message.from_user.id
    user_emails = await get_user_emails(user_id)

    logger.info(f"Найдено email для {user_id}: {user_emails}")

    if user_emails:
        keyboard_buttons = []
        for email in user_emails:
            keyboard_buttons.append([InlineKeyboardButton(text=email, callback_data=f"send:{email}")])
        keyboard_buttons.append([InlineKeyboardButton(text="➕ Новый адрес", callback_data="change_email")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer(
            f"📧 Найдено {len(files)} файлов.\n"
            f"Выберите email для отправки (доступно {len(user_emails)} адресов):",
            reply_markup=keyboard
        )
    else:
        await state.set_state(EmailStates.waiting_for_email)
        await message.answer(f"📧 Найдено {len(files)} файлов. Введите email для отправки:")


@router.callback_query(F.data.startswith("send:"))
async def send_with_saved_email(callback: CallbackQuery, state: FSMContext):
    email = callback.data.split(":")[1]
    await callback.message.answer(f"📧 Отправка на {email}...")
    await callback.answer()
    await state.set_state(None)

    data = await state.get_data()
    files = data.get("files", [])
    user_subject = data.get("subject")

    email_subject = user_subject if user_subject and user_subject.strip() else get_default_subject(files)

    success = await send_files_to_email(files, email, email_subject)

    if success:
        await callback.message.answer(
            f"✅ Файлы отправлены!\n"
            f"📝 Тема: {email_subject}\n"
            f"📧 Получатель: {email}"
        )
    else:
        await callback.message.answer("❌ Ошибка при отправке. Проверьте настройки почты.")

    await state.clear()


@router.callback_query(F.data == "change_email")
async def change_email(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EmailStates.waiting_for_email)
    await callback.message.answer(
        "📧 Введите новый email для отправки.\n"
        "💡 После отправки этот email будет сохранён в списке последних (до 3 адресов)."
    )
    await callback.answer()


@router.message(EmailStates.waiting_for_email)
async def process_email_input(message: Message, state: FSMContext):
    email = message.text.strip()
    user_id = message.from_user.id

    logger.info(f"=== ОБРАБОТКА EMAIL: {email} ===")

    if not is_valid_email(email):
        await message.answer("⚠️ Некорректный email. Пример: user@example.com\nПожалуйста, введите правильный email:")
        return

    await save_user_email(user_id, email)
    logger.info(f"Email {email} сохранён для {user_id}")

    await state.set_state(None)

    data = await state.get_data()
    files = data.get("files", [])
    user_subject = data.get("subject")

    if not files:
        await message.answer("❌ Файлы не найдены.")
        return

    email_subject = user_subject if user_subject and user_subject.strip() else get_default_subject(files)

    await message.answer(f"📧 Отправка на {email}...")
    success = await send_files_to_email(files, email, email_subject)

    updated_emails = await get_user_emails(user_id)

    if success:
        await message.answer(
            f"✅ Файлы отправлены!\n"
            f"📝 Тема: {email_subject}\n"
            f"📧 Получатель: {email}\n\n"
            f"💾 Сохранённые адреса ({len(updated_emails)}/3):\n"
            + "\n".join([f"• {e}" for e in updated_emails])
        )
    else:
        await message.answer("❌ Ошибка при отправке. Проверьте настройки почты.")

    await state.clear()


@router.message(Command("stats"))
async def show_stats(message: Message):
    """Показывает статистику бота (только для админа)"""
    ADMIN_ID = 1017147622  # Замените на ваш Telegram ID

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    # Получаем статистику
    total_users = len(stats_manager.data["total_users"])
    total_photos = stats_manager.data["total_photos"]
    total_docs = stats_manager.data["total_documents"]
    total_emails = stats_manager.data["total_emails_sent"]
    total_errors = stats_manager.data["total_errors"]
    total_restarts = stats_manager.data["total_restarts"]
    last_restart = stats_manager.data["last_restart"]

    # Периоды
    day_stats = stats_manager.get_period_stats("day")
    week_stats = stats_manager.get_period_stats("week")
    month_stats = stats_manager.get_period_stats("month")

    await message.answer(
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 **Пользователи**\n"
        f"• Всего: {total_users}\n\n"

        f"📁 **Отправлено файлов**\n"
        f"• Всего фото: {total_photos}\n"
        f"• Всего документов: {total_docs}\n"
        f"• Всего писем: {total_emails}\n\n"

        f"📅 **За сегодня**\n"
        f"• Фото: {day_stats['photos']}\n"
        f"• Документы: {day_stats['documents']}\n"
        f"• Письма: {day_stats['emails']}\n\n"

        f"📆 **За неделю**\n"
        f"• Фото: {week_stats['photos']}\n"
        f"• Документы: {week_stats['documents']}\n"
        f"• Письма: {week_stats['emails']}\n\n"

        f"📅 **За месяц**\n"
        f"• Фото: {month_stats['photos']}\n"
        f"• Документы: {month_stats['documents']}\n"
        f"• Письма: {month_stats['emails']}\n\n"

        f"⚠️ **Система**\n"
        f"• Ошибок: {total_errors}\n"
        f"• Перезагрузок: {total_restarts}\n"
        f"• Последний рестарт: {last_restart or 'не было'}\n\n"

        f"🕐 Бот работает в штатном режиме"
    )
    
# ==================== ОБРАБОТКА ФАЙЛОВ ====================
@router.message(F.text, ~F.text.in_({"Готово"}))
async def handle_text_only(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logger.info(f"Текущее состояние: {current_state}, текст: {message.text}")

    if current_state == EmailStates.waiting_for_email:
        logger.info("Пользователь в состоянии waiting_for_email — пропускаем как тему")
        return

    data = await state.get_data()
    files = data.get("files", [])

    if not files:
        await message.answer("📁 Сначала отправьте файлы (фото или документы).")
        return

    subject_text = message.text.strip()
    await state.update_data(subject=subject_text)
    logger.info(f"Тема установлена: {subject_text}")
    await message.answer(f"📝 Тема установлена:\n\"{subject_text}\"")


@router.message(F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def handle_files(message: Message, state: FSMContext):
    """Обрабатывает все файлы, объединяя медиагруппы от одного пользователя"""
    user_id = message.from_user.id

    # Инициализируем хранилище для пользователя
    if user_id not in user_pending_files:
        user_pending_files[user_id] = {
            "messages": [],
            "process_task": None,
            "last_update": 0
        }

    # Добавляем сообщение
    user_pending_files[user_id]["messages"].append(message)
    user_pending_files[user_id]["last_update"] = asyncio.get_event_loop().time()

    # Если уже есть задача на обработку, не создаём новую
    if user_pending_files[user_id]["process_task"] is None or user_pending_files[user_id]["process_task"].done():
        task = asyncio.create_task(process_user_files_delayed(user_id, state))
        user_pending_files[user_id]["process_task"] = task


async def process_user_files_delayed(user_id: int, state: FSMContext, delay: float = 1.0):
    """Отложенная обработка всех файлов пользователя (объединяет несколько медиагрупп)"""
    await asyncio.sleep(delay)

    if user_id not in user_pending_files:
        return

    user_data = user_pending_files.pop(user_id)
    messages = user_data["messages"]

    if not messages:
        return

    logger.info(f"Обработка {len(messages)} файлов от пользователя {user_id}")

    first_msg = messages[0]
    caption = first_msg.caption

    if caption and caption.strip():
        await state.update_data(subject=caption.strip())
        logger.info(f"Тема из первого сообщения: {caption.strip()}")

    data = await state.get_data()
    files = data.get("files", [])
    old_count = len(files)

    for msg in messages:
        try:
            if msg.photo:
                original_name = get_photo_filename(msg)
                file = await msg.bot.download(msg.photo[-1])
                stats_manager.add_photo()  # 👈 ДОБАВИТЬ СЧЁТЧИК ФОТО
            elif msg.document:
                original_name = get_document_filename(msg)
                file = await msg.bot.download(msg.document)
                stats_manager.add_document()  # 👈 ДОБАВИТЬ СЧЁТЧИК ДОКУМЕНТОВ
            else:
                continue

            file_path, final_name = get_unique_file_path(UPLOAD_FOLDER, original_name)

            with open(file_path, "wb") as f:
                f.write(file.read())

            files.append((file_path, final_name))
            logger.info(f"Файл добавлен: {final_name}")

        except Exception as e:
            logger.error(f"Ошибка при сохранении файла: {e}")

    await state.update_data(files=files)

    # Проверка размера и отправка результата
    total_size = sum(os.path.getsize(p) for p, _ in files)
    max_size = 10 * 1024 * 1024
    added_count = len(files) - old_count
    current_subject = (await state.get_data()).get("subject")

    size_mb = total_size / (1024 * 1024)

    if total_size > max_size:
        warning_msg = (
            f"⚠️ **ВНИМАНИЕ: Превышение лимита!**\n\n"
            f"✅ Добавлено {added_count} файлов.\n"
            f"📊 Общий размер всех файлов: {size_mb:.1f} МБ (лимит: 10 МБ)\n\n"
            f"❌ При отправке письмо может не доставиться!\n"
            f"💡 Рекомендуется удалить часть файлов или отправить их отдельно.\n\n"
            f"Текущая тема: \"{current_subject or 'не указана'}\"\n\n"
            f"Отправьте ещё файлы или нажмите 'Готово'."
        )
        await first_msg.answer(warning_msg)
    else:
        remaining_mb = (max_size - total_size) / (1024 * 1024)
        if current_subject:
            await first_msg.answer(
                f"✅ Добавлено {added_count} файлов.\n"
                f"📝 Тема: \"{current_subject}\"\n"
                f"📊 Общий размер: {size_mb:.1f} / 10 МБ\n"
                f"💾 Осталось: {remaining_mb:.1f} МБ\n\n"
                f"Отправьте ещё файлы или нажмите 'Готово'."
            )
        else:
            await first_msg.answer(
                f"✅ Добавлено {added_count} файлов.\n"
                f"📊 Общий размер: {size_mb:.1f} / 10 МБ\n"
                f"💾 Осталось: {remaining_mb:.1f} МБ\n\n"
                f"📝 Чтобы добавить тему, напишите текст.\n\n"
                f"Отправьте ещё файлы или нажмите 'Готово'."
            )

async def process_single_file(message: Message, state: FSMContext):
    """Обрабатывает одиночный файл с умной проверкой размера"""
    data = await state.get_data()
    files = data.get("files", [])

    caption = message.caption
    if caption and caption.strip():
        await state.update_data(subject=caption.strip())
        has_subject = True
    else:
        has_subject = False

    try:
        if message.photo:
            original_name = get_photo_filename(message)
            file = await message.bot.download(message.photo[-1])
            stats_manager.add_photo()  # 👈 ДОБАВИТЬ СЧЁТЧИК ФОТО
        elif message.document:
            original_name = get_document_filename(message)
            file = await message.bot.download(message.document)
            stats_manager.add_document()  # 👈 ДОБАВИТЬ СЧЁТЧИК ДОКУМЕНТОВ
        else:
            await message.answer("⚠️ Отправьте фото или документ.")
            return

        file_path, final_name = get_unique_file_path(UPLOAD_FOLDER, original_name)

        with open(file_path, "wb") as f:
            f.write(file.read())

        files.append((file_path, final_name))
        await state.update_data(files=files)

        # Умная проверка размера
        total_size = sum(os.path.getsize(p) for p, _ in files)
        max_size = 10 * 1024 * 1024

        if total_size > max_size:
            size_mb = total_size / (1024 * 1024)
            await message.answer(
                f"⚠️ **ВНИМАНИЕ: Превышение лимита!**\n\n"
                f"Общий размер файлов: {size_mb:.1f} МБ (лимит: 10 МБ)\n"
                f"Файл '{final_name}' добавлен, но при отправке письмо может не доставиться.\n\n"
                f"Рекомендуется удалить некоторые файлы или отправить их отдельно.\n\n"
                f"✅ Вы можете продолжить добавлять файлы или нажать 'Готово'."
            )
        else:
            remaining_mb = (max_size - total_size) / (1024 * 1024)
            if has_subject:
                await message.answer(
                    f"✅ Файл '{final_name}' добавлен.\n"
                    f"📝 Тема: \"{caption.strip()}\"\n"
                    f"📊 Общий размер: {total_size / (1024 * 1024):.1f} / 10 МБ\n"
                    f"💾 Осталось: {remaining_mb:.1f} МБ"
                )
            else:
                await message.answer(
                    f"✅ Файл '{final_name}' добавлен. Всего: {len(files)}.\n"
                    f"📊 Общий размер: {total_size / (1024 * 1024):.1f} / 10 МБ\n"
                    f"💾 Осталось: {remaining_mb:.1f} МБ\n\n"
                    f"📝 Чтобы добавить тему, напишите текст."
                )

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Ошибка при сохранении файла.")
