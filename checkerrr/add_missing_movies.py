#!/usr/bin/env python3
"""
Скрипт для добавления недостающих фильмов (053 и 067)
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "/root/projectss/checkerrr/movies.db"

# Missing movies
MISSING_MOVIES = [
    # 053 - Бешеные псы (нужно использовать код "053a" т.к. "53" уже занят)
    ("053a", "Бешеные псы (Reservoir Dogs)", 1992, 
     ["Криминал", "Триллер", "Чёрная комедия"],
     ["Харви Кейтель (Kharvi Keytel)", "Тим Рот (Tim Rot)", "Майкл Мэдсен (Maykl Madsen)", "Стив Бушеми (Stiv Bushemi)"],
     ["Квентин Тарантино (Kventin Tarantino)"],
     "https://rutube.ru/video/пример-reservoir-dogs"),
    
    # 067 - Супермен 2025 (без ссылки, т.к. новинка)
    ("067", "Супермен (Superman) 2025", 2025,
     ["Супергероика", "Боевик"],
     ["Дэвид Коренсвет (Devid Korensvet)", "Рэйчел Броснахэн (Reychel Brosnakhen)"],
     ["Джеймс Ганн (Dzheyms Gann)"],
     ""),  # новинка 2025, пока может не быть
]


def get_or_create_genre(cursor, name: str) -> int:
    name = name.strip().lower()
    cursor.execute("SELECT id FROM genres WHERE LOWER(name) = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO genres (name) VALUES (?)", (name,))
    return cursor.lastrowid


def get_or_create_actor(cursor, name: str) -> int:
    name = name.strip()
    cursor.execute("SELECT id FROM actors WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO actors (name) VALUES (?)", (name,))
    return cursor.lastrowid


def get_or_create_director(cursor, name: str) -> int:
    name = name.strip()
    cursor.execute("SELECT id FROM directors WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO directors (name) VALUES (?)", (name,))
    return cursor.lastrowid


def add_missing_movies():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    added_count = 0
    
    for movie_data in MISSING_MOVIES:
        code, title, year, genres, actors, directors, link = movie_data
        
        # Check if already exists
        cursor.execute("SELECT id FROM movies WHERE code = ?", (code,))
        if cursor.fetchone():
            logger.warning(f"⚠️ Фильм уже существует: {code} - {title}")
            continue
        
        try:
            cursor.execute('''
                INSERT INTO movies (code, title, link, year, description, quality, views, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, title, link, year, None, "1080p", 0, 7.5))
            
            movie_id = cursor.lastrowid
            
            # Add genres
            for genre_name in genres:
                genre_id = get_or_create_genre(cursor, genre_name)
                cursor.execute('''
                    INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)
                ''', (movie_id, genre_id))
            
            # Add actors
            for actor_name in actors:
                actor_id = get_or_create_actor(cursor, actor_name)
                cursor.execute('''
                    INSERT OR IGNORE INTO movie_actors (movie_id, actor_id) VALUES (?, ?)
                ''', (movie_id, actor_id))
            
            # Add directors
            for director_name in directors:
                director_id = get_or_create_director(cursor, director_name)
                cursor.execute('''
                    INSERT OR IGNORE INTO movie_directors (movie_id, director_id) VALUES (?, ?)
                ''', (movie_id, director_id))
            
            added_count += 1
            logger.info(f"✅ Добавлен: {code} - {title}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления {code} - {title}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"✅ Готово! Добавлено фильмов: {added_count}")


if __name__ == "__main__":
    add_missing_movies()
