# database/stats.py

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


# Путь к файлу статистики
def get_stats_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'stats.json')
    else:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stats.json')


class StatsManager:
    def __init__(self):
        self.stats_file = get_stats_path()
        self.data = self._load()

    def _load(self) -> Dict:
        """Загружает статистику из файла"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return self._default_stats()

    def _default_stats(self) -> Dict:
        """Структура статистики по умолчанию"""
        return {
            "total_users": set(),
            "total_photos": 0,
            "total_documents": 0,
            "total_emails_sent": 0,
            "total_errors": 0,
            "total_restarts": 0,
            "last_restart": None,
            "daily_stats": {},
            "weekly_stats": {},
            "monthly_stats": {}
        }

    def _save(self):
        """Сохраняет статистику в файл"""
        # Преобразуем set в list для JSON
        save_data = self.data.copy()
        if "total_users" in save_data:
            save_data["total_users"] = list(save_data["total_users"])

        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        # Восстанавливаем set
        if "total_users" in save_data:
            self.data["total_users"] = set(save_data["total_users"])

    def _get_date_key(self, date: datetime) -> str:
        """Возвращает ключ для статистики по дате"""
        return date.strftime("%Y-%m-%d")

    def _update_period_stats(self, stat_type: str, date_key: str):
        """Обновляет статистику за период"""
        if stat_type == "photos":
            # Обновляем дневную статистику
            if date_key not in self.data["daily_stats"]:
                self.data["daily_stats"][date_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["daily_stats"][date_key]["photos"] += 1

            # Обновляем недельную статистику
            week_key = f"week_{datetime.now().strftime('%Y_W%W')}"
            if week_key not in self.data["weekly_stats"]:
                self.data["weekly_stats"][week_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["weekly_stats"][week_key]["photos"] += 1

            # Обновляем месячную статистику
            month_key = datetime.now().strftime("%Y-%m")
            if month_key not in self.data["monthly_stats"]:
                self.data["monthly_stats"][month_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["monthly_stats"][month_key]["photos"] += 1

        elif stat_type == "documents":
            if date_key not in self.data["daily_stats"]:
                self.data["daily_stats"][date_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["daily_stats"][date_key]["documents"] += 1

            week_key = f"week_{datetime.now().strftime('%Y_W%W')}"
            if week_key not in self.data["weekly_stats"]:
                self.data["weekly_stats"][week_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["weekly_stats"][week_key]["documents"] += 1

            month_key = datetime.now().strftime("%Y-%m")
            if month_key not in self.data["monthly_stats"]:
                self.data["monthly_stats"][month_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["monthly_stats"][month_key]["documents"] += 1

        elif stat_type == "email":
            if date_key not in self.data["daily_stats"]:
                self.data["daily_stats"][date_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["daily_stats"][date_key]["emails"] += 1

            week_key = f"week_{datetime.now().strftime('%Y_W%W')}"
            if week_key not in self.data["weekly_stats"]:
                self.data["weekly_stats"][week_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["weekly_stats"][week_key]["emails"] += 1

            month_key = datetime.now().strftime("%Y-%m")
            if month_key not in self.data["monthly_stats"]:
                self.data["monthly_stats"][month_key] = {"photos": 0, "documents": 0, "emails": 0}
            self.data["monthly_stats"][month_key]["emails"] += 1

        self._save()

    def add_user(self, user_id: int):
        """Добавляет нового пользователя"""
        if user_id not in self.data["total_users"]:
            self.data["total_users"].add(user_id)
            self._save()

    def add_photo(self):
        """Увеличивает счётчик фото"""
        self.data["total_photos"] += 1
        date_key = self._get_date_key(datetime.now())
        self._update_period_stats("photos", date_key)

    def add_document(self):
        """Увеличивает счётчик документов"""
        self.data["total_documents"] += 1
        date_key = self._get_date_key(datetime.now())
        self._update_period_stats("documents", date_key)

    def add_email_sent(self):
        """Увеличивает счётчик отправленных писем"""
        self.data["total_emails_sent"] += 1
        date_key = self._get_date_key(datetime.now())
        self._update_period_stats("email", date_key)

    def add_error(self):
        """Увеличивает счётчик ошибок"""
        self.data["total_errors"] += 1
        self._save()

    def add_restart(self):
        """Увеличивает счётчик перезагрузок"""
        self.data["total_restarts"] += 1
        self.data["last_restart"] = datetime.now().isoformat()
        self._save()

    def get_period_stats(self, period: str) -> Dict:
        """Возвращает статистику за период (day/week/month)"""
        today = datetime.now().date()

        if period == "day":
            date_key = today.strftime("%Y-%m-%d")
            stats = self.data["daily_stats"].get(date_key, {"photos": 0, "documents": 0, "emails": 0})
            return stats

        elif period == "week":
            # Суммируем за последние 7 дней
            total = {"photos": 0, "documents": 0, "emails": 0}
            for i in range(7):
                date_key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                day_stats = self.data["daily_stats"].get(date_key, {"photos": 0, "documents": 0, "emails": 0})
                total["photos"] += day_stats["photos"]
                total["documents"] += day_stats["documents"]
                total["emails"] += day_stats["emails"]
            return total

        elif period == "month":
            # Суммируем за последние 30 дней
            total = {"photos": 0, "documents": 0, "emails": 0}
            for i in range(30):
                date_key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                day_stats = self.data["daily_stats"].get(date_key, {"photos": 0, "documents": 0, "emails": 0})
                total["photos"] += day_stats["photos"]
                total["documents"] += day_stats["documents"]
                total["emails"] += day_stats["emails"]
            return total

        return {"photos": 0, "documents": 0, "emails": 0}


# Глобальный экземпляр
stats_manager = StatsManager()