# main.py

import sys  # 👈 ЭТОТ ИМПОРТ НУЖНО ДОБАВИТЬ!
import time
import threading
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from handlers.common import router as main_router
from database.storage import setup_database
from config import check_config
from database.stats import stats_manager


# Функция обновления heartbeat
def update_heartbeat():
    """Обновляет файл heartbeat для watchdog"""
    if getattr(sys, 'frozen', False):
        heartbeat_file = os.path.join(os.path.dirname(sys.executable), 'heartbeat.txt')
    else:
        heartbeat_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'heartbeat.txt')

    while True:
        try:
            with open(heartbeat_file, 'w') as f:
                f.write(str(time.time()))
            time.sleep(10)  # Каждые 10 секунд
        except:
            time.sleep(10)


check_config()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=os.getenv("BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())

# Регистрируем только один роутер
dp.include_router(main_router)


async def on_startup():
    await setup_database()
    logger.info("База данных готова")


async def main():
    stats_manager.add_restart()  # Регистрируем перезапуск
    # Запускаем heartbeat в отдельном потоке
    heartbeat_thread = threading.Thread(target=update_heartbeat, daemon=True)
    heartbeat_thread.start()

    dp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())