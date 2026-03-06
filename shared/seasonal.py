#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎄 Seasonal Templates — Сезонные шаблоны для постов

Использование:
    from shared import SeasonalTemplates
    
    templates = SeasonalTemplates()
    header = templates.get_header()  # "🎄 Новогодний дайджест"
    footer = templates.get_footer()  # "С праздником! 🎅"
"""
from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class SeasonalTemplates:
    """Сезонные шаблоны для постов и дайджестов"""
    
    # Праздники (месяц, день) → название
    HOLIDAYS = {
        # Январь
        (1, 1): "Новый год",
        (1, 7): "Рождество",
        (1, 14): "Старый Новый год",
        (1, 25): "День студентов",
        
        # Февраль
        (2, 14): "День святого Валентина",
        (2, 23): "День защитника Отечества",
        
        # Март
        (3, 8): "8 Марта",
        
        # Апрель
        (4, 1): "День смеха",
        (4, 12): "День космонавтики",
        
        # Май
        (5, 1): "День труда",
        (5, 9): "День Победы",
        
        # Июнь
        (6, 1): "День защиты детей",
        (6, 12): "День России",
        
        # Июль
        (7, 8): "День семьи",
        
        # Сентябрь
        (9, 1): "День знаний",
        
        # Октябрь
        (10, 5): "День учителя",
        (10, 31): "Хэллоуин",
        
        # Ноябрь
        (11, 4): "День народного единства",
        
        # Декабрь
        (12, 25): "Католическое Рождество",
        (12, 31): "Новый год (канун)",
    }
    
    # Шаблоны заголовков для дайджестов
    DIGEST_HEADERS = {
        "new_year": "🎄🎅 <b>НОВОГОДНИЙ ДАЙДЖЕСТ</b> 🎅🎄",
        "christmas": "⭐ <b>РОЖДЕСТВЕНСКИЙ ДАЙДЖЕСТ</b> ⭐",
        "feb23": "🛡️ <b>ДАЙДЖЕСТ К 23 ФЕВРАЛЯ</b> 🛡️",
        "mar8": "🌷 <b>ПРАЗДНИЧНЫЙ ДАЙДЖЕСТ К 8 МАРТА</b> 🌷",
        "may9": "🎖️ <b>ДАЙДЖЕСТ К ДНЮ ПОБЕДЫ</b> 🎖️",
        "halloween": "🎃 <b>ХЭЛЛОУИНСКИЙ ДАЙДЖЕСТ</b> 🎃",
        "default": "📊 <b>ДАЙДЖЕСТ ЗА {date}</b>",
    }
    
    # Шаблоны футеров
    FOOTERS = {
        "new_year": "\n\n🎄 С Новым Годом! Пусть следующий год будет ещё интереснее! 🥂",
        "christmas": "\n\n⭐ С Рождеством! Мира и добра! ✨",
        "feb23": "\n\n🛡️ С Днём защитника Отечества! 💪",
        "mar8": "\n\n🌷 С 8 Марта! Весеннего настроения! 🌸",
        "may9": "\n\n🎖️ С Днём Победы! Вечная память героям! 🕯️",
        "halloween": "\n\n🎃 С Хэллоуином! Не бойтесь читать новости! 👻",
        "default": "",
    }
    
    # Сезонные эмодзи по месяцам
    SEASONAL_EMOJIS = {
        1: "❄️🎄🎅",  # Январь
        2: "💘🛡️",     # Февраль
        3: "🌷🌸🌺",   # Март
        4: "🚀🌍",     # Апрель
        5: "🎖️🌹",     # Май
        6: "☀️🏖️",     # Июнь
        7: "🌞🏖️",     # Июль
        8: "🌾☀️",     # Август
        9: "📚🍂",     # Сентябрь
        10: "🍂🎃",    # Октябрь
        11: "🍂☔",     # Ноябрь
        12: "❄️🎄🎅",  # Декабрь
    }
    
    def __init__(self):
        self._cache = {}
    
    def get_today_holiday(self) -> Optional[str]:
        """Получение сегодняшнего праздника"""
        now = datetime.now(timezone.utc)
        key = (now.month, now.day)
        return self.HOLIDAYS.get(key)
    
    def is_holiday_today(self) -> bool:
        """Проверка: сегодня праздник?"""
        return self.get_today_holiday() is not None
    
    def is_holiday_period(self, days_before: int = 1, days_after: int = 0) -> bool:
        """
        Проверка: сейчас праздничный период?
        
        Args:
            days_before: Дней до праздника
            days_after: Дней после праздника
        """
        now = datetime.now(timezone.utc)
        
        for (month, day), name in self.HOLIDAYS.items():
            holiday_date = datetime(now.year, month, day, tzinfo=timezone.utc)
            period_start = holiday_date - timedelta(days=days_before)
            period_end = holiday_date + timedelta(days=days_after)
            
            if period_start <= now <= period_end:
                return True
        
        return False
    
    def get_header(self, date_str: str = "") -> str:
        """
        Получение заголовка для дайджеста
        
        Args:
            date_str: Дата (по умолчанию сегодня)
        
        Returns:
            Заголовок с учётом праздника
        """
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        
        holiday = self.get_today_holiday()
        
        if holiday:
            # Определяем тип праздника
            if "Новый год" in holiday or "Старый Новый год" in holiday:
                return self.DIGEST_HEADERS["new_year"]
            elif "Рождество" in holiday:
                return self.DIGEST_HEADERS["christmas"]
            elif "23 февраля" in holiday or "Защитника" in holiday:
                return self.DIGEST_HEADERS["feb23"]
            elif "8 Марта" in holiday:
                return self.DIGEST_HEADERS["mar8"]
            elif "Победы" in holiday:
                return self.DIGEST_HEADERS["may9"]
            elif "Хэллоуин" in holiday:
                return self.DIGEST_HEADERS["halloween"]
        
        # Обычный заголовок
        return self.DIGEST_HEADERS["default"].format(date=date_str)
    
    def get_footer(self) -> str:
        """Получение футера для дайджеста"""
        holiday = self.get_today_holiday()
        
        if holiday:
            if "Новый год" in holiday or "Старый Новый год" in holiday:
                return self.FOOTERS["new_year"]
            elif "Рождество" in holiday:
                return self.FOOTERS["christmas"]
            elif "23 февраля" in holiday or "Защитника" in holiday:
                return self.FOOTERS["feb23"]
            elif "8 Марта" in holiday:
                return self.FOOTERS["mar8"]
            elif "Победы" in holiday:
                return self.FOOTERS["may9"]
            elif "Хэллоуин" in holiday:
                return self.FOOTERS["halloween"]
        
        return self.FOOTERS["default"]
    
    def get_seasonal_emoji(self) -> str:
        """Получение сезонных эмодзи для текущего месяца"""
        month = datetime.now(timezone.utc).month
        return self.SEASONAL_EMOJIS.get(month, "📰")
    
    def decorate_post(self, text: str, add_footer: bool = True) -> str:
        """
        Украшение поста сезонными элементами
        
        Args:
            text: Текст поста
            add_footer: Добавить футер
        
        Returns:
            Украшенный текст
        """
        holiday = self.get_today_holiday()
        
        if holiday:
            # Добавляем праздничный эмодзи в начало
            emoji = self.get_seasonal_emoji()
            lines = text.split('\n')
            
            if lines:
                # Добавляем эмодзи к заголовку
                lines[0] = f"{emoji} {lines[0]}"
            
            # Добавляем футер
            if add_footer:
                footer = self.get_footer()
                if footer:
                    lines.append(footer)
            
            return '\n'.join(lines)
        
        return text
    
    def get_upcoming_holidays(self, days: int = 7) -> List[Dict]:
        """
        Получение предстоящих праздников
        
        Args:
            days: На сколько дней вперёд
        
        Returns:
            Список праздников
        """
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        upcoming = []
        
        for (month, day), name in self.HOLIDAYS.items():
            holiday_date = datetime(now.year, month, day, tzinfo=timezone.utc)
            
            # Если праздник уже был в этом году, берём следующий год
            if holiday_date < now:
                holiday_date = datetime(now.year + 1, month, day, tzinfo=timezone.utc)
            
            days_until = (holiday_date - now).days
            
            if 0 <= days_until <= days:
                upcoming.append({
                    "name": name,
                    "date": holiday_date.strftime("%d.%m.%Y"),
                    "days_until": days_until,
                })
        
        # Сортируем по дате
        upcoming.sort(key=lambda x: x["days_until"])
        
        return upcoming


# ========== Helper для быстрой интеграции ==========

def apply_seasonal_template(text: str, template_type: str = "digest") -> str:
    """
    Быстрое применение сезонного шаблона
    
    Args:
        text: Текст
        template_type: Тип шаблона ("digest", "post", "header")
    
    Returns:
        Текст с шаблоном
    """
    templates = SeasonalTemplates()
    
    if template_type == "digest":
        header = templates.get_header()
        footer = templates.get_footer()
        return f"{header}\n\n{text}{footer}"
    
    elif template_type == "post":
        return templates.decorate_post(text)
    
    elif template_type == "header":
        return templates.get_header()
    
    return text


# Import timedelta for the helper function
from datetime import timedelta


__all__ = ['SeasonalTemplates', 'apply_seasonal_template']
