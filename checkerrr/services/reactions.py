"""
Сервис реакций (лайки/дизлайки)
"""
import logging
from typing import Dict, List

from database import Database

logger = logging.getLogger(__name__)


class ReactionService:
    """Сервис для управления реакциями на фильмы"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def add_reaction(
        self, 
        user_id: int, 
        movie_id: int, 
        movie_code: str,
        reaction_type: str  # 'like' или 'dislike'
    ) -> bool:
        """
        Добавить реакцию на фильм
        
        Returns:
            True если реакция добавлена успешно
        """
        try:
            # Проверяем, есть ли уже реакция
            existing = self.db.get_user_reaction(user_id, movie_id)
            
            if existing:
                # Если такая же реакция - удаляем (toggle)
                if existing['reaction_type'] == reaction_type:
                    self.db.remove_reaction(user_id, movie_id)
                    logger.info(f"Пользователь {user_id} удалил реакцию на фильм {movie_code}")
                    return False
                else:
                    # Изменяем реакцию
                    self.db.update_reaction(user_id, movie_id, reaction_type)
                    logger.info(f"Пользователь {user_id} изменил реакцию на фильм {movie_code}")
            else:
                # Добавляем новую реакцию
                self.db.add_reaction(user_id, movie_id, movie_code, reaction_type)
                logger.info(f"Пользователь {user_id} добавил реакцию '{reaction_type}' на фильм {movie_code}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления реакции: {e}")
            return False
    
    def get_movie_reactions(self, movie_id: int) -> Dict[str, int]:
        """
        Получить статистику реакций для фильма
        
        Returns:
            Dict с количеством likes и dislikes
        """
        reactions = self.db.get_movie_reactions(movie_id)
        
        likes = sum(1 for r in reactions if r['reaction_type'] == 'like')
        dislikes = sum(1 for r in reactions if r['reaction_type'] == 'dislike')
        
        return {
            'likes': likes,
            'dislikes': dislikes,
            'total': likes + dislikes,
            'rating': likes - dislikes
        }
    
    def get_user_reaction(self, user_id: int, movie_id: int) -> str | None:
        """
        Получить реакцию пользователя на фильм
        
        Returns:
            'like', 'dislike' или None
        """
        reaction = self.db.get_user_reaction(user_id, movie_id)
        return reaction['reaction_type'] if reaction else None
    
    def get_top_rated_movies(self, limit: int = 10) -> List[dict]:
        """
        Получить фильмы с лучшим рейтингом реакций
        
        Returns:
            Список фильмов с реакциями
        """
        movies = self.db.get_all_movies(limit=100)
        movies_with_ratings = []
        
        for movie in movies:
            stats = self.get_movie_reactions(movie['id'])
            if stats['total'] > 0:
                movies_with_ratings.append({
                    **movie,
                    'reaction_stats': stats
                })
        
        # Сортируем по рейтингу (likes - dislikes)
        movies_with_ratings.sort(
            key=lambda x: x['reaction_stats']['rating'], 
            reverse=True
        )
        
        return movies_with_ratings[:limit]
