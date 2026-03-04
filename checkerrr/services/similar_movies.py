"""
Сервис похожих фильмов
"""
import logging
from typing import List, Dict, Set

from database import Database

logger = logging.getLogger(__name__)


class SimilarMoviesService:
    """Сервис для поиска похожих фильмов"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_similar_movies(
        self, 
        movie_code: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Найти похожие фильмы на основе жанров, актёров и режиссёров
        
        Args:
            movie_code: код фильма
            limit: количество результатов
        
        Returns:
            Список похожих фильмов
        """
        # Получаем исходный фильм
        movie = self.db.get_movie_by_code(movie_code)
        if not movie:
            return []
        
        movie_id = movie.get('id')
        if not movie_id:
            return []
        
        # Получаем жанры, актёров, режиссёров
        movie_genres = set(self.db.get_movie_genres(movie_id))
        movie_actors = set(self.db.get_movie_actors(movie_id))
        movie_directors = set(self.db.get_movie_directors(movie_id))
        
        # Получаем все фильмы (кроме текущего)
        all_movies = self.db.get_all_movies(limit=500)
        
        candidates = []
        
        for m in all_movies:
            if m['code'] == movie_code:
                continue
            
            m_id = m.get('id')
            if not m_id:
                continue
            
            # Получаем жанры, актёров, режиссёров кандидата
            m_genres = set(self.db.get_movie_genres(m_id))
            m_actors = set(self.db.get_movie_actors(m_id))
            m_directors = set(self.db.get_movie_directors(m_id))
            
            # Считаем совпадения
            genres_match = len(movie_genres & m_genres)
            actors_match = len(movie_actors & m_actors)
            directors_match = len(movie_directors & m_directors)
            
            # Общий score
            score = (
                genres_match * 3 +  # Жанры важнее
                actors_match * 2 +
                directors_match * 2
            )
            
            if score > 0:
                candidates.append({
                    **m,
                    'similarity_score': score,
                    'genres_match': genres_match,
                    'actors_match': actors_match,
                    'directors_match': directors_match
                })
        
        # Сортируем по score
        candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Возвращаем top N
        return candidates[:limit]
    
    def get_similar_by_genre(
        self, 
        movie_code: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Найти фильмы того же жанра
        
        Returns:
            Список фильмов
        """
        movie = self.db.get_movie_by_code(movie_code)
        if not movie:
            return []
        
        movie_id = movie.get('id')
        if not movie_id:
            return []
        
        genres = self.db.get_movie_genres(movie_id)
        if not genres:
            return []
        
        # Ищем фильмы первого жанра
        similar = self.db.search_movies_by_genre_fuzzy(genres[0], limit=limit + 1)
        
        # Исключаем исходный фильм
        return [m for m in similar if m['code'] != movie_code][:limit]
    
    def get_similar_by_actor(
        self, 
        movie_code: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Найти фильмы с теми же актёрами
        
        Returns:
            Список фильмов
        """
        movie = self.db.get_movie_by_code(movie_code)
        if not movie:
            return []
        
        movie_id = movie.get('id')
        if not movie_id:
            return []
        
        actors = self.db.get_movie_actors(movie_id)
        if not actors:
            return []
        
        # Ищем фильмы с первым актёром
        similar = self.db.search_movies_by_actor_fuzzy(actors[0], limit=limit + 1)
        
        # Исключаем исходный фильм
        return [m for m in similar if m['code'] != movie_code][:limit]
    
    def get_similar_by_director(
        self, 
        movie_code: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Найти фильмы того же режиссёра
        
        Returns:
            Список фильмов
        """
        movie = self.db.get_movie_by_code(movie_code)
        if not movie:
            return []
        
        movie_id = movie.get('id')
        if not movie_id:
            return []
        
        directors = self.db.get_movie_directors(movie_id)
        if not directors:
            return []
        
        # Ищем фильмы того же режиссёра
        similar = self.db.search_movies_by_director_fuzzy(directors[0], limit=limit + 1)
        
        # Исключаем исходный фильм
        return [m for m in similar if m['code'] != movie_code][:limit]
