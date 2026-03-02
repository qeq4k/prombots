#!/usr/bin/env python3
"""
Скрипт для заполнения базы данных тестовыми фильмами.
Запустите: python fill_db.py
"""

import sqlite3
import os

DB_PATH = "movies.db"

# Тестовые фильмы (код, название, ссылка, год)
TEST_MOVIES = [
    ("1", "Побег из Шоушенка", "https://example.com/shawshank", 1994),
    ("2", "Крёстный отец", "https://example.com/godfather", 1972),
    ("3", "Тёмный рыцарь", "https://example.com/darkknight", 2008),
    ("4", "Криминальное чтиво", "https://example.com/pulpfiction", 1994),
    ("5", "Властелин колец: Возвращение короля", "https://example.com/lotr3", 2003),
    ("6", "Форрест Гамп", "https://example.com/forrestgump", 1994),
    ("7", "Начало", "https://example.com/inception", 2010),
    ("8", "Матрица", "https://example.com/matrix", 1999),
    ("9", "Интерстеллар", "https://example.com/interstellar", 2014),
    ("10", "Паразиты", "https://example.com/parasite", 2019),
    ("11", "Джокер", "https://example.com/joker", 2019),
    ("12", "Мстители: Финал", "https://example.com/avengers4", 2019),
    ("13", "Ла-Ла Ленд", "https://example.com/lalaland", 2016),
    ("14", "Зелёная миля", "https://example.com/greenmile", 1999),
    ("15", "Гладиатор", "https://example.com/gladiator", 2000),
    ("001", "Побег из Шоушенка (дубль)", "https://example.com/shawshank2", 1994),
    ("100", "Титаник", "https://example.com/titanic", 1997),
    ("123", "Аватар", "https://example.com/avatar", 2009),
    ("777", "Казино Рояль", "https://example.com/casino", 2006),
    ("999", "Бойцовский клуб", "https://example.com/fightclub", 1999),
]

# Жанры для фильмов
MOVIE_GENRES = {
    "1": ["драма"],
    "2": ["драма", "криминал"],
    "3": ["боевик", "драма"],
    "4": ["криминал", "драма"],
    "5": ["фэнтези", "приключения"],
    "6": ["драма", "мелодрама"],
    "7": ["фантастика", "боевик"],
    "8": ["фантастика", "боевик"],
    "9": ["фантастика", "драма"],
    "10": ["драма", "триллер"],
    "11": ["драма", "триллер"],
    "12": ["фантастика", "боевик"],
    "13": ["мелодрама", "комедия"],
    "14": ["драма", "фэнтези"],
    "15": ["боевик", "драма"],
    "001": ["драма"],
    "100": ["драма", "мелодрама"],
    "123": ["фантастика", "боевик"],
    "777": ["боевик", "триллер"],
    "999": ["драма", "триллер"],
}

def create_connection():
    """Создание подключения к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables(conn):
    """Создание таблиц если не существуют"""
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
    
    # Таблица каналов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            link TEXT NOT NULL,
            chat_id TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ru',
            is_subscribed BOOLEAN DEFAULT 0,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_search_at TIMESTAMP,
            total_searches INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # История поисков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            query_type TEXT NOT NULL,
            results_count INTEGER DEFAULT 0,
            found_movie_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (found_movie_id) REFERENCES movies(id) ON DELETE SET NULL
        )
    ''')
    
    # Избранное
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, movie_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
        )
    ''')
    
    # Аналитика просмотров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS view_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER NOT NULL,
            user_id INTEGER,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
        )
    ''')
    
    # Лог пустых поисков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empty_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT NOT NULL,
            query_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
        )
    ''')
    
    # Миграции
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Индексы
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_code ON movies(code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
    
    conn.commit()
    print("✅ Таблицы созданы")

def get_or_create_genre(conn, name):
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

def add_movie(conn, code, title, link, year, genres=None):
    """Добавить фильм"""
    cursor = conn.cursor()
    
    # Проверяем существование
    cursor.execute("SELECT id FROM movies WHERE code = ?", (code,))
    if cursor.fetchone():
        print(f"⏭️ Пропущено: {title} (код {code} уже существует)")
        return False
    
    # Добавляем фильм
    cursor.execute('''
        INSERT INTO movies (code, title, link, year, quality, views, rating)
        VALUES (?, ?, ?, ?, '1080p', 0, 8.0)
    ''', (code, title, link, year))
    
    movie_id = cursor.lastrowid
    
    # Добавляем жанры
    if genres:
        for genre_name in genres:
            genre_id = get_or_create_genre(conn, genre_name)
            cursor.execute('''
                INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)
            ''', (movie_id, genre_id))
    
    conn.commit()
    print(f"✅ Добавлено: {title} ({code})")
    return True

def fill_test_data(conn):
    """Заполнение тестовыми данными"""
    for code, title, link, year in TEST_MOVIES:
        genres = MOVIE_GENRES.get(code, [])
        add_movie(conn, code, title, link, year, genres)
    
    print(f"\n📊 Добавлено {len(TEST_MOVIES)} фильмов")

def main():
    print("🚀 Заполнение базы данных тестовыми фильмами...\n")
    
    conn = create_connection()
    create_tables(conn)
    fill_test_data(conn)
    
    # Проверка
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM movies")
    count = cursor.fetchone()[0]
    print(f"\n✅ Всего фильмов в базе: {count}")
    
    cursor.execute("SELECT code, title, year FROM movies LIMIT 5")
    print("\n📋 Первые 5 фильмов:")
    for row in cursor.fetchall():
        print(f"   {row['code']}. {row['title']} ({row['year']})")
    
    conn.close()
    print("\n✅ Готово!")

if __name__ == "__main__":
    main()
