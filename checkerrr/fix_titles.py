#!/usr/bin/env python3
"""
Скрипт для исправления названий фильмов (корректный перевод/транслит)
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "/root/projectss/checkerrr/movies.db"

# Исправленные названия (code: new_title)
FIXED_TITLES = {
    # Ошибочные дословные переводы → корректные
    "105": "Love Me Love Me (Лав ми лав ми)",  # не "Любовь меня, любовь меня"
    "106": "The Chronology of Water (Хронолоджи оф Уотер)",  # не "Хроника воды"
    "107": "All That's Left of You (Ол зэтс лефт оф ю)",  # не "Всё, что осталось от тебя"
    "108": "Is This Thing On? (Из зис синг он?)",  # не "Это вещь включена?"
    "109": "Twinless (Твинлес)",  # не "Двойняшка"
    "110": "My Father's Shadow (Май фазерс шэдоу)",  # не "Тень моего отца"
    "111": "Little Amélie (Литтл Амели)",  # не "Маленькая Амели или..."
    "113": "The Patient (Зе Пейшент)",  # не "Пациент"
    "114": "Spider-Noir (Спайдер-Нуар)",  # не "Паук-нуар"
    "115": "Disclosure Day (Дискложе Дей)",  # не "Раскрытие дня"
    "116": "The Mandalorian & Grogu (Зе Мандалориан энд Грогу)",  # не "Мандалорец и Грогу"
    "117": "Supergirl (Супергёрл)",  # не "Супергёрл" (оставить как есть)
    
    # Другие спорные переводы
    "060": "The Fall (Зе Фолл)",  # не "Королевство полной луны" (это другой фильм)
    "077": "F1 (Эф-Уан)",  # не "Автострада"
    "084": "Iron Lung (Айрон Ланг)",  # не "Железные лёгкие"
    "086": "GOAT (Гоут)",  # не "Козёл"
    "093": "Blades of the Guardians (Блэйдс оф зе Гардианз)",  # не "Клинки стражей"
    "094": "Last Ride (Ласт райд)",  # не "Последняя поездка"
    "095": "Solo Mio (Соло Мио)",  # оставить транслит
    "098": "Hoppers (Хопперс)",  # не "Прыгуны"
    "099": "Reminders of Him (Ремайндерс оф Хим)",  # не "Напоминания о нём"
    "100": "Undertone (Андертон)",  # не "Под тоном"
    "101": "They Will Kill You (Зэй уилл килл ю)",  # не "Они убьют тебя"
    "102": "The Rip (Зе Рип)",  # не "Разорви"
    "103": "Primate (Праймит)",  # не "Примат"
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
