#!/usr/bin/env python3
"""
Скрипт для обновления рейтингов фильмов (коды 053-117)
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "/root/projectss/checkerrr/movies.db"

# Ratings for movies (code: rating)
RATINGS = {
    "053": 8.3,
    "054": 8.0,
    "055": 7.8,
    "056": 7.7,
    "057": 8.0,
    "058": 7.3,
    "059": 8.0,
    "060": 7.8,
    "061": 8.2,
    "062": 8.5,
    "063": 8.1,
    "064": 6.8,
    "065": 6.8,
    "066": 8.0,
    "067": 7.6,
    "068": 7.2,
    "069": 7.0,
    "070": 7.1,
    "071": 7.4,
    "072": 7.8,
    "073": 7.5,
    "074": 7.3,
    "075": 7.6,
    "076": 7.9,
    "077": 7.5,
    "078": 7.2,
    "079": 6.9,
    "080": 7.1,
    "081": 7.0,
    "082": 6.8,
    "083": 7.4,
    "084": 7.3,
    "085": 6.7,
    "086": 7.0,
    "087": 7.2,
    "088": 7.5,
    "089": 7.1,
    "090": 6.9,
    "091": 7.3,
    "092": 7.0,
    "093": 7.4,
    "094": 6.8,
    "095": 6.6,
    "096": 7.8,
    "097": 7.2,
    "098": 7.0,
    "099": 7.1,
    "100": 6.9,
    "101": 7.0,
    "102": 7.3,
    "103": 6.8,
    "104": 7.2,
    "105": 6.7,
    "106": 7.1,
    "107": 6.9,
    "108": 7.0,
    "109": 7.2,
    "110": 6.8,
    "111": 7.0,
    "112": 7.1,
    "113": 6.9,
    "114": 7.3,
    "115": 7.5,
    "116": 7.4,
    "117": 7.2,
}


def update_ratings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    updated_count = 0
    not_found_count = 0
    
    for code, rating in RATINGS.items():
        # Try exact code match first
        cursor.execute("SELECT id, title FROM movies WHERE code = ?", (code,))
        row = cursor.fetchone()
        
        # If not found, try without leading zero (e.g., "53" instead of "053")
        if not row:
            code_no_zero = code.lstrip('0')
            cursor.execute("SELECT id, title FROM movies WHERE code = ?", (code_no_zero,))
            row = cursor.fetchone()
        
        # Also check for "053a" variant
        if not row and code == "053":
            cursor.execute("SELECT id, title FROM movies WHERE code = '053a'")
            row = cursor.fetchone()
        
        if row:
            movie_id, title = row
            cursor.execute("UPDATE movies SET rating = ? WHERE id = ?", (rating, movie_id))
            updated_count += 1
            logger.info(f"✅ Обновлён рейтинг: {code} - {title} → {rating}")
        else:
            not_found_count += 1
            logger.warning(f"⚠️ Не найден фильм с кодом: {code}")
    
    conn.commit()
    conn.close()
    
    logger.info("=" * 50)
    logger.info(f"✅ Готово! Обновлено: {updated_count}, Не найдено: {not_found_count}")


if __name__ == "__main__":
    update_ratings()
