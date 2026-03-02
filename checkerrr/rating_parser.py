#!/usr/bin/env python3
"""
Модуль для парсинга рейтингов фильмов с Кинопоиска и IMDb.
"""
import logging
import re
from typing import Optional, Dict
import asyncio

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("⚠️ aiohttp не установлен. Парсинг рейтингов недоступен.")


# Заголовки для запросов (чтобы не блокировали)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}


def extract_year_from_title(title: str) -> Optional[int]:
    """Извлекает год из названия фильма"""
    match = re.search(r'\(?\d{4}\)?', title)
    if match:
        year_str = match.group().replace('(', '').replace(')', '')
        return int(year_str)
    return None


def clean_title(title: str) -> str:
    """Очищает название для поиска"""
    # Убираем год в скобках
    title = re.sub(r'\(\d{4}\)', '', title)
    # Убираем лишние пробелы
    title = ' '.join(title.split())
    return title.strip()


async def parse_kinopoisk_rating(session: aiohttp.ClientSession, title: str, year: Optional[int] = None) -> Optional[float]:
    """
    Парсинг рейтинга с Кинопоиска.
    Возвращает рейтинг от 0.0 до 10.0 или None если не найдено.
    """
    try:
        # Очищаем название для поиска
        search_title = clean_title(title)
        
        # Используем API для поиска (через поиск на сайте)
        # Примечание: это упрощённая версия, для продакшена лучше использовать официальное API
        search_url = f"https://www.kinopoisk.ru/search/?kp_query={search_title.replace(' ', '+')}"
        
        async with session.get(search_url, headers=HEADERS, timeout=10) as response:
            if response.status != 200:
                logger.warning(f"Kinopoisk вернул статус {response.status}")
                return None
            
            html = await response.text()
            
            # Ищем рейтинг в HTML (упрощённый парсинг)
            # Кинопоиск использует разные классы, поэтому ищем по паттернам
            rating_patterns = [
                r'ratingBall\s*>\s*([\d.]+)',
                r'rating\s*:\s*([\d.]+)',
                r'data-rating\s*=\s*"([\d.]+)"',
            ]
            
            for pattern in rating_patterns:
                match = re.search(pattern, html)
                if match:
                    rating = float(match.group(1))
                    if 0 <= rating <= 10:
                        logger.info(f"Kinopoisk: {title} → {rating}")
                        return rating
            
            logger.debug(f"Kinopoisk: рейтинг не найден для {title}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка парсинга Kinopoisk для {title}: {e}")
        return None


async def parse_imdb_rating(session: aiohttp.ClientSession, title: str, year: Optional[int] = None) -> Optional[float]:
    """
    Парсинг рейтинга с IMDb.
    Возвращает рейтинг от 0.0 до 10.0 или None если не найдено.
    """
    try:
        search_title = clean_title(title)
        
        # Поиск через IMDb search
        search_url = f"https://www.imdb.com/find/?q={search_title.replace(' ', '+')}"
        
        async with session.get(search_url, headers=HEADERS, timeout=10) as response:
            if response.status != 200:
                return None
            
            html = await response.text()
            
            # Ищем ссылку на первый результат
            title_match = re.search(r'/title/tt\d+/', html)
            if not title_match:
                return None
            
            # Переходим на страницу фильма
            movie_url = f"https://www.imdb.com{title_match.group()}"
            
            async with session.get(movie_url, headers=HEADERS, timeout=10) as movie_response:
                if movie_response.status != 200:
                    return None
                
                movie_html = await movie_response.text()
                
                # Ищем рейтинг
                rating_match = re.search(r'ratingValue"\s*>\s*([\d.]+)', movie_html)
                if rating_match:
                    rating = float(rating_match.group(1))
                    if 0 <= rating <= 10:
                        logger.info(f"IMDb: {title} → {rating}")
                        return rating
            
            return None
            
    except Exception as e:
        logger.error(f"Ошибка парсинга IMDb для {title}: {e}")
        return None


async def parse_rating(title: str, year: Optional[int] = None, priority: str = 'kinopoisk') -> Optional[float]:
    """
    Получение рейтинга из доступных источников.
    
    Args:
        title: Название фильма
        year: Год выпуска (опционально)
        priority: Приоритетный источник ('kinopoisk' или 'imdb')
    
    Returns:
        Рейтинг от 0.0 до 10.0 или None
    """
    if not AIOHTTP_AVAILABLE:
        logger.warning("aiohttp недоступен, используем рейтинг по умолчанию")
        return None
    
    async with aiohttp.ClientSession() as session:
        # Пробуем приоритетный источник
        if priority == 'kinopoisk':
            rating = await parse_kinopoisk_rating(session, title, year)
            if rating:
                return rating
            rating = await parse_imdb_rating(session, title, year)
        else:
            rating = await parse_imdb_rating(session, title, year)
            if rating:
                return rating
            rating = await parse_kinopoisk_rating(session, title, year)
        
        return rating


async def parse_multiple_ratings(movies: list) -> Dict[str, float]:
    """
    Парсинг рейтингов для нескольких фильмов.
    
    Args:
        movies: Список словарей {'title': str, 'year': int}
    
    Returns:
        Словарь {code: rating}
    """
    results = {}
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for movie in movies:
            title = movie.get('title', '')
            year = movie.get('year')
            code = movie.get('code', '')
            
            # Создаём задачу с таймаутом
            task = asyncio.wait_for(
                parse_kinopoisk_rating(session, title, year),
                timeout=15
            )
            tasks.append((code, task))
        
        # Выполняем с ограничением параллелизма
        import asyncio.semaphore
        semaphore = asyncio.Semaphore(5)  # Максимум 5 одновременных запросов
        
        async def limited_parse(code, task):
            async with semaphore:
                try:
                    rating = await task
                    if rating:
                        results[code] = rating
                except asyncio.TimeoutError:
                    logger.warning(f"Таймаут парсинга для {code}")
                except Exception as e:
                    logger.error(f"Ошибка парсинга {code}: {e}")
        
        await asyncio.gather(*[limited_parse(code, task) for code, task in tasks])
    
    return results


def get_rating_stars(rating: float) -> str:
    """Конвертирует рейтинг в звёзды"""
    full_stars = int(rating / 2)  # 10 баллов = 5 звёзд
    half_star = 1 if (rating % 2) >= 1 else 0
    return "⭐" * full_stars + ("½" if half_star else "")


# Синхронная обёртка для простого использования
def get_rating_sync(title: str, year: Optional[int] = None, timeout: int = 20) -> Optional[float]:
    """
    Синхронная версия получения рейтинга.
    
    Args:
        title: Название фильма
        year: Год выпуска
        timeout: Таймаут в секундах
    
    Returns:
        Рейтинг или None
    """
    if not AIOHTTP_AVAILABLE:
        return None
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        rating = loop.run_until_complete(parse_rating(title, year))
        return rating
    except Exception as e:
        logger.error(f"Ошибка получения рейтинга: {e}")
        return None


if __name__ == "__main__":
    # Тестирование
    test_movies = [
        {"title": "Матрица", "year": 1999, "code": "001"},
        {"title": "Титаник", "year": 1997, "code": "002"},
        {"title": "Начало", "year": 2010, "code": "004"},
    ]
    
    print("🔍 Тест парсинга рейтингов...")
    
    for movie in test_movies:
        rating = get_rating_sync(movie['title'], movie['year'])
        if rating:
            stars = get_rating_stars(rating)
            print(f"  {movie['title']} ({movie['year']}) → {rating}/10 {stars}")
        else:
            print(f"  {movie['title']} → не найдено")
