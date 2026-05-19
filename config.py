# config.py

import os
import sys
from dotenv import load_dotenv


def get_base_path() -> str:
    """Возвращает путь к папке, где находится исполняемый файл"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_path()
env_path = os.path.join(BASE_DIR, '.env')
load_dotenv(env_path)


def get_bot_token() -> str:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN не найден в .env")
    return token


def get_smtp_config() -> dict:
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    email_address = os.getenv("EMAIL_ADDRESS")
    email_password = os.getenv("EMAIL_PASSWORD")

    if not all([smtp_server, smtp_port, email_address, email_password]):
        raise ValueError("Не все SMTP переменные найдены в .env")

    return {
        "server": smtp_server,
        "port": int(smtp_port),
        "address": email_address,
        "password": email_password
    }


def check_config():
    required_vars = ["BOT_TOKEN", "SMTP_SERVER", "SMTP_PORT", "EMAIL_ADDRESS", "EMAIL_PASSWORD"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"❌ Отсутствуют: {', '.join(missing)}")
    print("✅ Все переменные окружения загружены!")


if __name__ == "__main__":
    check_config()