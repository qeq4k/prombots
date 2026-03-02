#!/usr/bin/env python3
"""
Скрипт для заполнения базы данных информацией о фильмах:
актёры, режиссёры, жанры.
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from database import Database
from movies_data import MOVIES_DATA

def fill_database():
    """Заполняет базу данных фильмами с актёрами, режиссёрами и жанрами."""
    
    config = Config()
    db = Database(config.DATABASE_PATH)
    
    print(f"📊 Подключение к базе: {config.DATABASE_PATH}")
    
    added = 0
    skipped = 0
    errors = 0
    
    for movie_data in MOVIES_DATA:
        try:
            code = movie_data['code']
            title = movie_data['title']
            year = movie_data.get('year')
            genres = movie_data.get('genres', [])
            actors = movie_data.get('actors', [])
            directors = movie_data.get('directors', [])
            
            # Проверяем, есть ли уже фильм с таким кодом
            existing = db.get_movie_by_code(code)
            
            if existing:
                # Фильм существует - обновляем жанры, актёров, режиссёров
                print(f"⏭️ Пропущено (уже есть): {code} - {title}")
                skipped += 1
                
                # Но добавляем жанры, актёров и режиссёров если их нет
                movie_id = existing['id']
                
                # Добавляем жанры
                for genre in genres:
                    genre_id = db._get_or_create_genre(genre)
                    if genre_id:
                        db.cursor.execute(
                            'INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)',
                            (movie_id, genre_id)
                        )
                
                # Добавляем актёров
                for actor in actors:
                    actor_id = db._get_or_create_actor(actor)
                    if actor_id:
                        db.cursor.execute(
                            'INSERT OR IGNORE INTO movie_actors (movie_id, actor_id) VALUES (?, ?)',
                            (movie_id, actor_id)
                        )
                
                # Добавляем режиссёров
                for director in directors:
                    director_id = db._get_or_create_director(director)
                    if director_id:
                        db.cursor.execute(
                            'INSERT OR IGNORE INTO movie_directors (movie_id, director_id) VALUES (?, ?)',
                            (movie_id, director_id)
                        )
                
                db.conn.commit()
            else:
                # Фильма нет - создаём заглушку с полной информацией
                # Для работы бота нужен link, поэтому создаём временную ссылку
                temp_link = f"https://example.com/movie/{code}"
                
                success = db.add_movie(
                    code=code,
                    title=title,
                    link=temp_link,
                    year=year,
                    description="",
                    poster_url="",
                    banner_url="",
                    trailer_url="",
                    quality="1080p",
                    rating=0.0,
                    duration=None,
                    genres=genres,
                    actors=actors,
                    directors=directors
                )
                
                if success:
                    print(f"✅ Добавлено: {code} - {title}")
                    added += 1
                else:
                    print(f"❌ Ошибка добавления: {code} - {title}")
                    errors += 1
                    
        except Exception as e:
            print(f"❌ Ошибка обработки {movie_data.get('code', 'unknown')}: {e}")
            errors += 1
    
    db.close()
    
    print("\n" + "="*50)
    print(f"📊 Результаты заполнения базы:")
    print(f"   ✅ Добавлено: {added}")
    print(f"   ⏭️ Пропущено: {skipped}")
    print(f"   ❌ Ошибок: {errors}")
    print("="*50)
    
    if added > 0:
        print(f"\n✅ Успешно добавлено {added} фильмов с актёрами, режиссёрами и жанрами!")
        print("\n📌 Теперь работают:")
        print("   • Поиск по жанрам (🎭 Поиск по жанру)")
        print("   • Поиск по актёрам (🎬 Поиск по актёру)")
        print("   • Поиск по режиссёрам (🎥 Поиск по режиссёру)")
    else:
        print("\n⚠️ Ни одного фильма не добавлено. Возможно, все уже есть в базе.")


if __name__ == "__main__":
    fill_database()
