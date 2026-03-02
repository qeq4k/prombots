import re
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher

# Импортируем aliases из movies_data
try:
    from movies_data import ACTOR_ALIASES, DIRECTOR_ALIASES, GENRE_ALIASES
except ImportError:
    ACTOR_ALIASES = {}
    DIRECTOR_ALIASES = {}
    GENRE_ALIASES = {}


def validate_movie_code(code: str) -> Optional[str]:
    """
    Валидация кода фильма — ТОЛЬКО цифры (1-10 цифр).
    """
    code = code.strip()
    cleaned = re.sub(r'\D', '', code)

    if not cleaned or len(cleaned) < 1:
        return None

    if len(cleaned) > 10:
        cleaned = cleaned[:10]

    return cleaned


def format_year_line(year: Optional[int]) -> str:
    """Форматирование года для вывода."""
    if year and year > 1900:
        return f"📅 Год: {year}\n"
    return ""


def format_duration_line(duration: Optional[int]) -> str:
    """Форматирование длительности фильма."""
    if duration and duration > 0:
        hours = duration // 60
        minutes = duration % 60
        if hours > 0:
            return f"⏱ Длительность: {hours} ч {minutes} мин\n"
        return f"⏱ Длительность: {minutes} мин\n"
    return ""


def format_rating_line(rating: Optional[float]) -> str:
    """Форматирование рейтинга фильма."""
    if rating and rating > 0:
        stars = "⭐" * round(rating)
        return f"⭐ Рейтинг: {rating}/10 {stars}\n"
    return ""


def fuzzy_match_score(s1: str, s2: str) -> float:
    """
    Вычисляет коэффициент схожести строк (0.0 - 1.0).
    Использует SequenceMatcher для fuzzy matching.
    """
    s1_lower = s1.lower().strip()
    s2_lower = s2.lower().strip()
    
    # Прямое совпадение
    if s1_lower == s2_lower:
        return 1.0
    
    # Частичное совпадение
    return SequenceMatcher(None, s1_lower, s2_lower).ratio()


def search_movies_by_title(query: str, db) -> List[Dict]:
    """
    Поиск фильмов по названию с fuzzy matching.
    """
    if not query or len(query) < 2:
        return []

    query_clean = query.lower().strip()

    # Сначала пробуем SQL поиск
    try:
        if hasattr(db, 'search_movies_by_title_sql'):
            sql_results = db.search_movies_by_title_sql(query_clean, limit=20)
            if sql_results:
                # Сортируем по релевантности
                scored = []
                for movie in sql_results:
                    score = fuzzy_match_score(query_clean, movie['title'])
                    # Бонус за начало с запроса
                    if movie['title'].lower().startswith(query_clean):
                        score += 0.2
                    scored.append((movie, score))
                
                scored.sort(key=lambda x: x[1], reverse=True)
                return [movie for movie, score in scored[:10]]
    except Exception as e:
        pass

    # Fallback: загрузка всех и fuzzy поиск
    all_movies = db.get_all_movies(limit=500)
    results = []

    for movie in all_movies:
        score = fuzzy_match_score(query_clean, movie['title'])
        
        # Бонус за начало с запроса
        if movie['title'].lower().startswith(query_clean):
            score += 0.3
        
        # Бонус за содержание слов
        title_words = movie['title'].lower().split()
        query_words = query_clean.split()
        for qw in query_words:
            if any(qw in tw for tw in title_words):
                score += 0.1

        if score > 0.3:  # Порог релевантности
            results.append((movie, score))

    # Сортируем по релевантности
    results.sort(key=lambda x: x[1], reverse=True)
    return [movie for movie, score in results[:10]]


def normalize_code_for_search(code: str) -> str:
    """
    Нормализует код для поиска в БД — удаляет ведущие нули.
    """
    cleaned = re.sub(r'\D', '', code.strip())
    if not cleaned:
        return ""
    return str(int(cleaned)) if cleaned.isdigit() else cleaned


def extract_search_intent(text: str) -> Dict[str, Any]:
    """
    Извлекает намерение поиска из текста пользователя.
    Определяет только код фильма (цифры).

    Returns:
        {
            'type': 'code' | 'unknown',
            'query': str,
            'confidence': float
        }
    """
    text = text.strip()

    # Проверка на код (только цифры)
    if text.isdigit():
        return {'type': 'code', 'query': text, 'confidence': 1.0}

    # Проверка на код с буквами (например, MATRIX1)
    code_match = re.match(r'^[A-Za-z0-9]{1,10}$', text)
    if code_match and any(c.isdigit() for c in text):
        return {'type': 'code', 'query': text.upper(), 'confidence': 0.8}

    # Всё остальное — неизвестное
    return {'type': 'unknown', 'query': text, 'confidence': 0.0}


def format_movie_card(movie: Dict, lang: str = "ru") -> str:
    """
    Форматирует информацию о фильме в красивую карточку.
    """
    year_line = format_year_line(movie.get('year'))
    duration_line = format_duration_line(movie.get('duration'))
    rating_line = format_rating_line(movie.get('rating'))
    
    quality = movie.get('quality', '1080p')
    views = movie.get('views', 0)
    
    if lang == "ru":
        return (
            f"🎬 *{movie['title']}*\n"
            f"{year_line}"
            f"{duration_line}"
            f"{rating_line}"
            f"⭐ Код: `{movie['code']}`\n"
            f"📺 Качество: {quality}\n"
            f"👁️ Просмотров: {views}\n\n"
            f"⬇️ Ссылка для просмотра:\n{movie['link']}"
        )
    else:
        return (
            f"🎬 *{movie['title']}*\n"
            f"{year_line}"
            f"{duration_line}"
            f"{rating_line}"
            f"⭐ Code: `{movie['code']}`\n"
            f"📺 Quality: {quality}\n"
            f"👁️ Views: {views}\n\n"
            f"⬇️ Watch link:\n{movie['link']}"
        )


def calculate_similarity_for_recommendation(movie1: Dict, movie2: Dict) -> float:
    """
    Вычисляет схожесть двух фильмов для рекомендаций.
    Учитывает жанры, год, рейтинг.
    """
    score = 0.0

    # Схожесть по году (в пределах 5 лет)
    if movie1.get('year') and movie2.get('year'):
        year_diff = abs(movie1['year'] - movie2['year'])
        if year_diff <= 5:
            score += 0.3
        elif year_diff <= 10:
            score += 0.1

    # Схожесть по рейтингу (в пределах 2 пунктов)
    if movie1.get('rating') and movie2.get('rating'):
        rating_diff = abs(movie1['rating'] - movie2['rating'])
        if rating_diff <= 2:
            score += 0.2

    # Схожесть по качеству
    if movie1.get('quality') == movie2.get('quality'):
        score += 0.1

    return score


def resolve_actor_alias(query: str) -> str:
    """
    Преобразует alias актёра в каноническое имя.
    """
    query_lower = query.lower().strip()
    return ACTOR_ALIASES.get(query_lower, query)


def resolve_director_alias(query: str) -> str:
    """
    Преобразует alias режиссёра в каноническое имя.
    """
    query_lower = query.lower().strip()
    return DIRECTOR_ALIASES.get(query_lower, query)


def resolve_genre_alias(query: str) -> str:
    """
    Преобразует alias жанра в каноническое имя (в нижнем регистре для БД).
    """
    query_lower = query.lower().strip()
    result = GENRE_ALIASES.get(query_lower, query_lower)
    return result.lower()


def extract_search_intent(text: str) -> Dict[str, Any]:
    """
    Извлекает намерение поиска из текста пользователя.
    Определяет тип поиска: код, название, актёр, режиссёр, жанр.

    Returns:
        {
            'type': 'code' | 'title' | 'actor' | 'director' | 'genre' | 'unknown',
            'query': str,
            'confidence': float
        }
    """
    text = text.strip()

    # Проверка на код (только цифры)
    if text.isdigit():
        return {'type': 'code', 'query': text, 'confidence': 1.0}

    # Проверка на код с буквами (например, MATRIX1)
    code_match = re.match(r'^[A-Za-z0-9]{1,10}$', text)
    if code_match and any(c.isdigit() for c in text):
        return {'type': 'code', 'query': text.upper(), 'confidence': 0.8}

    # Всё остальное — неизвестное (будет обрабатываться в bot.py)
    return {'type': 'unknown', 'query': text, 'confidence': 0.0}
