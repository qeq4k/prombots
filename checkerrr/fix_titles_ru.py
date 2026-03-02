#!/usr/bin/env python3
"""
Скрипт для исправления названий фильмов (русский перевод + английский оригинал)
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "/root/projectss/checkerrr/movies.db"

# Исправленные названия (code: new_title) - русский перевод + английский в скобках
FIXED_TITLES = {
    # Неправильные переводы → правильные
    "105": "Люби меня, люби (Love Me Love Me)",
    "106": "Хронология воды (The Chronology of Water)",
    "107": "Всё, что от тебя осталось (All That's Left of You)",
    "108": "Это thing работает? (Is This Thing On?)",
    "109": "Близнец (Twinless)",
    "110": "Тень моего отца (My Father's Shadow)",
    "111": "Маленькая Амели (Little Amélie)",
    "113": "Пациент (The Patient)",
    "114": "Человек-паук: Нуар (Spider-Noir)",
    "115": "День раскрытия (Disclosure Day)",
    "116": "Мандалорец и Грогу (The Mandalorian & Grogu)",
    "117": "Супергёрл (Supergirl)",
    
    # Другие исправления
    "060": "Падение (The Fall)",
    "077": "Формула-1 (F1)",
    "084": "Железное лёгкое (Iron Lung)",
    "086": "Козёл (GOAT)",
    "093": "Клинки стражей (Blades of the Guardians)",
    "094": "Последняя поездка (Last Ride)",
    "095": "Соло мио (Solo Mio)",
    "098": "Прыгуны (Hoppers)",
    "099": "Напоминания о нём (Reminders of Him)",
    "100": "Подтекст (Undertone)",
    "101": "Они убьют тебя (They Will Kill You)",
    "102": "Разрыв (The Rip)",
    "103": "Примат (Primate)",
}


def update_titles():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    updated_count = 0
    not_found_count = 0
    
    for code, new_title in FIXED_TITLES.items():
        cursor.execute("SELECT id, title FROM movies WHERE code = ?", (code,))
        row = cursor.fetchone()
        
        if row:
            movie_id, old_title = row
            cursor.execute("UPDATE movies SET title = ? WHERE id = ?", (new_title, movie_id))
            updated_count += 1
            logger.info(f"✅ Исправлено: {code}")
            logger.info(f"   Было: {old_title}")
            logger.info(f"   Стало: {new_title}")
        else:
            not_found_count += 1
            logger.warning(f"⚠️ Не найден фильм с кодом: {code}")
    
    conn.commit()
    conn.close()
    
    logger.info("=" * 50)
    logger.info(f"✅ Готово! Обновлено: {updated_count}, Не найдено: {not_found_count}")


if __name__ == "__main__":
    update_titles()
