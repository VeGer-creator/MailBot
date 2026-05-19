# watchdog.py

import asyncio
import subprocess
import sys
import os
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BotWatchdog:
    def __init__(self, bot_file: str, check_interval: int = 30):
        self.bot_file = bot_file
        self.check_interval = check_interval
        self.last_heartbeat = None
        self.process = None
        self.restart_count = 0

        # Файл для хранения времени последнего heartbeat
        if getattr(sys, 'frozen', False):
            self.heartbeat_file = os.path.join(os.path.dirname(sys.executable), 'heartbeat.txt')
        else:
            self.heartbeat_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'heartbeat.txt')

    def update_heartbeat(self):
        """Обновляет время последнего heartbeat (вызывается из бота)"""
        with open(self.heartbeat_file, 'w') as f:
            f.write(str(time.time()))
        logger.info("Heartbeat обновлён")

    def check_heartbeat(self) -> bool:
        """Проверяет, жив ли бот"""
        if not os.path.exists(self.heartbeat_file):
            return False

        try:
            with open(self.heartbeat_file, 'r') as f:
                last_time = float(f.read().strip())

            # Если прошло больше 60 секунд без heartbeat — бот завис
            if time.time() - last_time > 60:
                logger.warning(f"Бот не отвечает! Последний heartbeat: {datetime.fromtimestamp(last_time)}")
                return False
            return True
        except:
            return False

    def start_bot(self):
        """Запускает бота как отдельный процесс"""
        logger.info("Запуск бота...")

        if getattr(sys, 'frozen', False):
            # Запуск .exe
            self.process = subprocess.Popen([self.bot_file])
        else:
            # Запуск .py
            self.process = subprocess.Popen([sys.executable, self.bot_file])

        # Ждём запуска
        time.sleep(5)
        self.restart_count += 1
        logger.info(f"Бот запущен (PID: {self.process.pid}), перезагрузок: {self.restart_count}")

    def stop_bot(self):
        """Останавливает бота"""
        if self.process and self.process.poll() is None:
            logger.info("Остановка бота...")
            self.process.terminate()
            time.sleep(3)
            if self.process.poll() is None:
                self.process.kill()

    def run(self):
        """Основной цикл watchdog"""
        logger.info(f"Watchdog запущен. Проверка каждые {self.check_interval} секунд")

        while True:
            if not self.check_heartbeat():
                logger.error("Обнаружен зависший бот! Перезапуск...")
                self.stop_bot()
                self.start_bot()
                time.sleep(10)  # Даём время на запуск

            time.sleep(self.check_interval)


def run_watchdog():
    """Запускает watchdog"""
    if getattr(sys, 'frozen', False):
        bot_path = os.path.join(os.path.dirname(sys.executable), 'MailBot.exe')
    else:
        bot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')

    watchdog = BotWatchdog(bot_path)
    watchdog.run()


if __name__ == "__main__":
    run_watchdog()