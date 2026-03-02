#!/usr/bin/env python3
"""
Скрипт для импорта фильмов из CSV в базу данных с жанрами, актёрами и рейтингами.
Запуск: python3 import_csv.py [--parse-ratings]
"""

import csv
import sqlite3
import re
import sys
import time
from typing import List, Dict, Optional

DB_PATH = "movies.db"
CSV_FILE = "movies_import.csv"

try:
    from predefined_ratings import get_predefined_rating, get_rating_stars
    RATINGS_AVAILABLE = True
except ImportError:
    RATINGS_AVAILABLE = False
    print("⚠️ predefined_ratings не доступен. Рейтинги будут 0.0.")
    
try:
    from rating_parser import get_rating_sync as parse_rating_sync
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False

# Жанры по фильмам (автоматическое определение по ключевым словам)
GENRE_KEYWORDS = {
    "боевик": ["мстители", "терминатор", "матрица", "джон", "экшен", "битва", "война", "пантера", "паук"],
    "драма": ["история", "жизнь", "любовь", "семья", "судьба", "дружба", "правда", "грехов", "молчание", "ягнят", "остров", "пианист", "зелёная", "миля", "форрест", "гамп", "шиндлера", "американская"],
    "фантастика": ["космос", "планета", "будущее", "робот", "инопланет", "реальность", "сон", "начало", "интерстеллар", "матрица", "аватар", "дюна", "джокер"],
    "фэнтези": ["магия", "волшеб", "хоббит", "гарри", "поттер", "властелин", "колец", "средизем", "ваканда"],
    "криминал": ["гангстер", "мафия", "преступ", "криминал", "крёстный", "отец", "чтиво", "джентльмен", "американская"],
    "триллер": ["убийца", "смерть", "расследование", "детектив", "молчание", "ягнят", "остров", "прокля", "семь", "престиж", "джокер"],
    "комедия": ["смеш", "комедия", "приключ", "1+1"],
    "приключения": ["путешеств", "приключ", "хоббит", "поттер", "паук"],
    "биография": ["реальн", "история", "жизнь", "выживание"],
    "военный": ["война", "битва", "солдат", "армия"],
    "вестерн": ["вестерн", "ковбой", "стрелок", "хороший", "плохой", "злой", "джанго"],
}

# Актёры по фильмам (по ключевым словам в названии)
ACTOR_MOVIES = {
    "Матрица": ["Киану Ривз", "Лоуренс Фишберн", "Кэрри-Энн Мосс", "Хьюго Уивинг"],
    "Дюна": ["Тимоти Шаламе", "Ребекка Фергюсон", "Оскар Айзек", "Зендея"],
    "Титаник": ["Леонардо Ди Каприо", "Кейт Уинслет"],
    "Начало": ["Леонардо Ди Каприо", "Том Харди", "Киллиан Мёрфи", "Марион Котийяр"],
    "Интерстеллар": ["Мэттью МакКонахи", "Энн Хэтэуэй", "Джессика Честейн"],
    "Джокер": ["Хоакин Феникс", "Роберт Де Ниро"],
    "Аватар": ["Сэм Уортингтон", "Зои Салдана"],
    "Мстители": ["Роберт Дауни мл.", "Крис Эванс", "Скарлетт Йоханссон", "Крис Хемсворт"],
    "Паразиты": ["Сон Кан Хо", "Ли Сон Гюн"],
    "Крёстный отец": ["Марлон Брандо", "Аль Пачино", "Джеймс Каан"],
    "Бойцовский клуб": ["Брэд Питт", "Эдвард Нортон", "Хелена Бонем Картер"],
    "Побег из Шоушенка": ["Тим Роббинс", "Морган Фримен"],
    "12 разгневанных мужчин": ["Генри Фонда", "Ли Дж. Кобб"],
    "Список Шиндлера": ["Лиам Нисон", "Бен Кингсли"],
    "Властелин колец": ["Элайджа Вуд", "Иэн МакКеллен", "Вигго Мортенсен"],
    "Хоббит": ["Мартин Фримен", "Иэн МакКеллен", "Ричард Армитидж"],
    "Гарри Поттер": ["Дэниел Рэдклифф", "Руперт Гринт", "Эмма Уотсон"],
    "Гладиатор": ["Рассел Кроу", "Хоакин Феникс"],
    "Семь": ["Брэд Питт", "Морган Фримен"],
    "Престиж": ["Хью Джекман", "Кристиан Бейл"],
    "Леон": ["Жан Рено", "Натали Портман", "Гари Олдман"],
    "Терминатор": ["Арнольд Шварценеггер", "Линда Хэмилтон"],
    "Криминальное чтиво": ["Джон Траволта", "Сэмюэл Л. Джексон", "Ума Турман"],
    "Молчание ягнят": ["Джоди Фостер", "Энтони Хопкинс"],
    "Американская история Икс": ["Эдвард Нортон"],
    "Остров проклятых": ["Леонардо Ди Каприо", "Марк Руффало"],
    "Форрест Гамп": ["Том Хэнкс"],
    "Зелёная миля": ["Том Хэнкс", "Майкл Кларк Дункан"],
    "Пианист": ["Эдриен Броуди"],
    "Хороший, плохой, злой": ["Клинт Иствуд"],
    "1+1": ["Франсуа Клюзе", "Омар Си"],
    "Джанго освобожденный": ["Джейми Фокс", "Кристоф Вальц", "Леонардо Ди Каприо"],
    "Без компромиссов": ["Пэдди Консидайн", "Эйдан Гиллен"],
    "Человек-паук": ["Том Холланд", "Сэмюэл Л. Джексон"],
    "Чёрная пантера": ["Чедвик Боузман", "Майкл Б. Джордан"],
    "Джентльмены": ["Мэттью МакКонахи", "Чарли Ханнэм"],
}


def create_connection() -> sqlite3.Connection:
    """Создание подключения к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Таблица фильмов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            year INTEGER,
            description TEXT,
            poster_url TEXT,
            quality TEXT DEFAULT '1080p',
            views INTEGER DEFAULT 0,
            rating REAL DEFAULT 0.0,
            duration INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица жанров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Связь фильмов и жанров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movie_genres (
            movie_id INTEGER NOT NULL,
            genre_id INTEGER NOT NULL,
            PRIMARY KEY (movie_id, genre_id),
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
            FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
        )
    ''')
    
    # Таблица актёров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    ''')
    
    # Связь фильмов и актёров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movie_actors (
            movie_id INTEGER NOT NULL,
            actor_id INTEGER NOT NULL,
            PRIMARY KEY (movie_id, actor_id),
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
            FOREIGN KEY (actor_id) REFERENCES actors(id) ON DELETE CASCADE
        )
    ''')
    
    # Индексы
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_code ON movies(code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)')
    
    conn.commit()
    return conn


def get_or_create_genre(conn: sqlite3.Connection, name: str) -> Optional[int]:
    """Получить или создать жанр"""
    cursor = conn.cursor()
    name = name.strip().lower()
    cursor.execute("SELECT id FROM genres WHERE LOWER(name) = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO genres (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def get_or_create_actor(conn: sqlite3.Connection, name: str) -> Optional[int]:
    """Получить или создать актёра"""
    cursor = conn.cursor()
    name = name.strip()
    cursor.execute("SELECT id FROM actors WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO actors (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def detect_genres(title: str, description: str = "") -> List[str]:
    """Автоматическое определение жанров по названию и описанию"""
    detected = []
    text = (title + " " + description).lower()
    
    for genre, keywords in GENRE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                if genre not in detected:
                    detected.append(genre)
                break
    
    if not detected:
        detected = ["драма"]
    
    return detected


def get_actors_for_movie(title: str) -> List[str]:
    """Получить актёров для фильма"""
    for movie_title, actors in ACTOR_MOVIES.items():
        if movie_title.lower() in title.lower():
            return actors
    return []


def import_movies(conn: sqlite3.Connection, csv_file: str, parse_ratings: bool = False):
    """Импорт фильмов из CSV"""
    cursor = conn.cursor()
    added = 0
    skipped = 0
    updated = 0
    
    # Считываем все строки
    movies_to_import = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            movies_to_import.append(row)
    
    total = len(movies_to_import)
    
    # Используем предустановленные рейтинги (быстро и надёжно)
    ratings_cache = {}
    if RATINGS_AVAILABLE:
        print(f"\n📊 Загрузка рейтингов для {total} фильмов...")
        for i, row in enumerate(movies_to_import, 1):
            title = row['title'].strip()
            code = row['code'].strip()
            
            rating = get_predefined_rating(title)
            if rating > 0:
                ratings_cache[code] = rating
                stars = get_rating_stars(rating)
                print(f"  [{i}/{total}] {title} → ⭐{rating}/10 {stars}")
            else:
                ratings_cache[code] = 0.0
                print(f"  [{i}/{total}] {title} → рейтинг не найден")
    
    # Импортируем фильмы
    for i, row in enumerate(movies_to_import, 1):
        try:
            code = row['code'].strip()
            title = row['title'].strip()
            link = row['link'].strip()
            year = int(row['year']) if row.get('year') and row['year'].strip() else None
            description = row.get('description', '').strip()
            poster_url = row.get('poster_url', '').strip()
            quality = row.get('quality', '1080p').strip()
            views = int(row.get('views', 0))
            
            # Рейтинг из кэша
            rating = ratings_cache.get(code, 0.0)
            
            # Проверяем существование
            cursor.execute("SELECT id FROM movies WHERE code = ?", (code,))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute('''
                    UPDATE movies SET 
                        title = ?, link = ?, year = ?, description = ?,
                        poster_url = ?, quality = ?, views = ?, rating = ?
                    WHERE code = ?
                ''', (title, link, year, description, poster_url, quality, views, rating, code))
                movie_id = existing['id']
                updated += 1
            else:
                cursor.execute('''
                    INSERT INTO movies (code, title, link, year, description, poster_url, quality, views, rating)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (code, title, link, year, description, poster_url, quality, views, rating))
                movie_id = cursor.lastrowid
                added += 1
            
            # Жанры
            genres = detect_genres(title, description)
            for genre_name in genres:
                genre_id = get_or_create_genre(conn, genre_name)
                if genre_id:
                    cursor.execute('''
                        INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)
                    ''', (movie_id, genre_id))
            
            # Актёры
            actors = get_actors_for_movie(title)
            for actor_name in actors:
                actor_id = get_or_create_actor(conn, actor_name)
                if actor_id:
                    cursor.execute('''
                        INSERT OR IGNORE INTO movie_actors (movie_id, actor_id) VALUES (?, ?)
                    ''', (movie_id, actor_id))
            
            conn.commit()
            
        except Exception as e:
            print(f"❌ Ошибка импорта строки {row.get('code', 'unknown')}: {e}")
            skipped += 1
            continue
    
    return added, updated, skipped


def main():
    print("🚀 Импорт фильмов из CSV в базу данных...\n")
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            pass
    except FileNotFoundError:
        print(f"❌ Файл {CSV_FILE} не найден!")
        print("Положите файл movies_import.csv в папку с ботом")
        return
    
    conn = create_connection()
    
    try:
        added, updated, skipped = import_movies(conn, CSV_FILE)
        
        print(f"\n✅ Импорт завершён!")
        print(f"📊 Добавлено: {added}")
        print(f"🔄 Обновлено: {updated}")
        print(f"⏭️ Пропущено: {skipped}")
        
        # Статистика
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        total_movies = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM genres")
        total_genres = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM actors")
        total_actors = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(rating) FROM movies WHERE rating > 0")
        avg_rating = cursor.fetchone()[0]
        
        print(f"\n📈 Всего в базе:")
        print(f"   Фильмов: {total_movies}")
        print(f"   Жанров: {total_genres}")
        print(f"   Актёров: {total_actors}")
        if avg_rating:
            print(f"   Средний рейтинг: {avg_rating:.1f}")
        
        # Примеры
        print(f"\n📋 Примеры фильмов с рейтингами:")
        cursor.execute('''
            SELECT m.code, m.title, m.rating, GROUP_CONCAT(g.name, ', ') as genres
            FROM movies m
            LEFT JOIN movie_genres mg ON m.id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.id
            GROUP BY m.id
            ORDER BY m.rating DESC
            LIMIT 5
        ''')
        for row in cursor.fetchall():
            rating_str = f"{row['rating']}/10" if row['rating'] and row['rating'] > 0 else "нет"
            stars = get_rating_stars(row['rating']) if row['rating'] > 0 else ""
            print(f"   {row['code']}. {row['title']} — ⭐{rating_str} {stars} — {row['genres'] or 'без жанров'}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
    
    print("\n✅ Готово!")


if __name__ == "__main__":
    main()
