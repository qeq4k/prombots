#!/usr/bin/env python3
"""
Скрипт для импорта актёров и режиссёров для фильмов из CSV.

Формат CSV:
code,title,year,description,link,poster_url,quality,views,rating,genre,main_actors_ru,main_actors_translit,director_ru,director_translit,kinopoisk_rating

Использование:
    python3 import_cast_crew.py cast_crew.csv
"""
import sys
import csv
import re
from database import Database

def parse_list(text):
    """Парсит строку со списком (разделители: | или ,)"""
    if not text or text.strip() == '—' or text.strip() == '"—"':
        return []
    
    text = text.strip().strip('"')
    
    # Если есть | - используем его как разделитель
    if '|' in text:
        separator = '|'
    else:
        separator = ','
    
    result = []
    for item in text.split(separator):
        item = item.strip()
        if item and item != '—':
            result.append(item)
    
    return result

def is_valid_name(name: str) -> bool:
    """Проверяет, является ли строка именем актёра/режиссёра (а не жанром или мусором)"""
    if not name or name.strip() == '—':
        return False
    
    name_lower = name.lower()
    
    # Слова-маркеры жанров и прочего мусора
    invalid_markers = [
        'sci-fi', 'genre', 'боевик', 'триллер', 'драма', 'комедия', 'ужасы',
        'фантастика', 'вестерн', 'мелодрама', 'детектив', 'криминал', 'биография',
        'исторический', 'документальный', 'анимация', 'мультфильм', 'предположительно',
        'научная фантастика', 'neo-нуар', 'нео-нуар', 'нуар', 'спай', 'шпионский',
        'супергероика', 'постапокалипсис', 'артхаус', 'мюзикл', 'романтика',
        'семья', 'семейный', 'эпик', 'приключения', 'фэнтези', 'военный', 'катастрофа',
        'спорт', 'спорт.', 'сатира', 'чёрная комедия', 'черная комедия', 'жанр',
        'предположительно', 'жанр-бендер', 'жанр бендер'
    ]
    
    # Если строка содержит маркер жанра — это не имя
    for marker in invalid_markers:
        if marker in name_lower:
            return False
    
    # Если строка состоит только из цифр и точек — это не имя
    if re.match(r'^[\d.\s]+$', name):
        return False
    
    # Если строка слишком короткая (1 символ) — это не имя
    if len(name.strip()) < 2:
        return False
    
    return True


def import_cast_crew(db: Database, csv_file: str):
    """Импортирует актёров и режиссёров для фильмов из CSV"""

    processed = 0
    updated_actors = 0
    updated_directors = 0
    skipped_invalid = 0

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            code = row.get('code', '').strip()
            if not code:
                continue

            movie = db.get_movie_by_code(code)
            if not movie:
                print(f"❌ Фильм с кодом '{code}' не найден")
                continue

            # Парсим актёров (используем русские имена)
            actors_str = row.get('main_actors_ru', '')
            actors = parse_list(actors_str)

            # Парсим режиссёров (используем русские имена)
            directors_str = row.get('director_ru', '')
            directors = parse_list(directors_str)

            if not actors and not directors:
                continue

            processed += 1

            # Удаляем старых актёров и режиссёров для этого фильма
            db.cursor.execute("DELETE FROM movie_actors WHERE movie_id = ?", (movie['id'],))
            db.cursor.execute("DELETE FROM movie_directors WHERE movie_id = ?", (movie['id'],))

            # Добавляем актёров
            for actor_name in actors:
                actor_name = actor_name.strip()
                if not is_valid_name(actor_name):
                    skipped_invalid += 1
                    continue
                # Очищаем имя от лишних кавычек и пробелов
                actor_name = ' '.join(actor_name.split())
                actor_id = db._get_or_create_actor(actor_name)
                if actor_id:
                    db.cursor.execute(
                        "INSERT OR IGNORE INTO movie_actors (movie_id, actor_id) VALUES (?, ?)",
                        (movie['id'], actor_id)
                    )
                    updated_actors += 1

            # Добавляем режиссёров
            for director_name in directors:
                director_name = director_name.strip()
                if not is_valid_name(director_name):
                    skipped_invalid += 1
                    continue
                # Очищаем имя от лишних кавычек и пробелов
                director_name = ' '.join(director_name.split())
                director_id = db._get_or_create_director(director_name)
                if director_id:
                    db.cursor.execute(
                        "INSERT OR IGNORE INTO movie_directors (movie_id, director_id) VALUES (?, ?)",
                        (movie['id'], director_id)
                    )
                    updated_directors += 1

            db.conn.commit()

            if processed % 10 == 0:
                print(f"✅ Обработано фильмов: {processed}")
    
    print(f"\n{'='*50}")
    print(f"✅ Импорт завершён!")
    print(f"📊 Обработано фильмов: {processed}")
    print(f"🎬 Добавлено актёров: {updated_actors}")
    print(f"🎥 Добавлено режиссёров: {updated_directors}")
    print(f"⚠️ Пропущено (жанры/мусор): {skipped_invalid}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование: python3 import_cast_crew.py <input.csv>")
        print("\nПример:")
        print("  python3 import_cast_crew.py cast_crew.csv")
        sys.exit(1)
    
    db = Database('movies.db')
    import_cast_crew(db, sys.argv[1])
