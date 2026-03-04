"""
Сервис трендов и статистики
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from database import Database

logger = logging.getLogger(__name__)


class TrendsService:
    """Сервис для получения трендовой статистики"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_trending_movies(
        self, 
        period: str = "week",
        limit: int = 10
    ) -> List[Dict]:
        """
        Получить трендовые фильмы за период
        
        Args:
            period: 'day', 'week', 'month'
            limit: количество фильмов
        
        Returns:
            Список фильмов со статистикой просмотров
        """
        days_map = {
            'day': 1,
            'week': 7,
            'month': 30
        }
        
        days = days_map.get(period, 7)
        top_movies = self.db.get_top_movies(limit=limit, period_days=days)
        
        result = []
        for i, movie in enumerate(top_movies, 1):
            result.append({
                'rank': i,
                'movie_code': movie['code'],
                'movie_title': movie['title'],
                'views_count': movie['views'],
                'period': period,
                'year': movie.get('year'),
                'rating': movie.get('rating')
            })
        
        return result
    
    def get_now_watching(self, minutes: int = 5) -> int:
        """
        Получить количество пользователей, смотрящих сейчас
        
        Args:
            minutes: за сколько минут считать активность
        
        Returns:
            Количество активных пользователей
        """
        return self.db.get_active_users_count(minutes=minutes)
    
    def get_popular_genres(self, limit: int = 5) -> List[Dict]:
        """
        Получить популярные жанры
        
        Returns:
            Список жанров с количеством фильмов
        """
        genres = self.db.get_all_genres()
        genres_with_count = []
        
        for genre in genres:
            count = self.db.get_movies_by_genre_count(genre['name'])
            genres_with_count.append({
                'name': genre['name'],
                'movies_count': count
            })
        
        # Сортируем по количеству фильмов
        genres_with_count.sort(key=lambda x: x['movies_count'], reverse=True)
        return genres_with_count[:limit]
    
    def get_popular_actors(self, limit: int = 5) -> List[Dict]:
        """
        Получить популярных актёров
        
        Returns:
            Список актёров с количеством фильмов
        """
        actors = self.db.get_all_actors(limit=100)
        actors_with_count = []
        
        for actor in actors:
            actors_with_count.append({
                'name': actor['name'],
                'movies_count': actor.get('film_count', 0)
            })
        
        # Сортируем по количеству фильмов
        actors_with_count.sort(key=lambda x: x['movies_count'], reverse=True)
        return actors_with_count[:limit]
    
    def get_search_stats(self, period_days: int = 7) -> Dict:
        """
        Получить статистику поисковых запросов
        
        Returns:
            Dict со статистикой
        """
        empty_searches = self.db.get_empty_searches_stats(period_days=period_days)
        
        return {
            'empty_searches': empty_searches[:10],
            'period_days': period_days
        }
    
    def get_daily_stats(self, date: datetime = None) -> Dict:
        """
        Получить дневную статистику
        
        Returns:
            Dict со статистикой за день
        """
        if date is None:
            date = datetime.now()
        
        return {
            'date': date.strftime('%Y-%m-%d'),
            'new_users': self.db.get_new_users_count(date),
            'searches': self.db.get_searches_count(date),
            'views': self.db.get_views_count(date)
        }
