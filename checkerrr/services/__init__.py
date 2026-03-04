"""
Сервисы для бота
"""
from .notifications import NotificationService
from .achievements import AchievementService
from .reactions import ReactionService
from .trends import TrendsService
from .similar_movies import SimilarMoviesService

__all__ = [
    "NotificationService",
    "AchievementService",
    "ReactionService",
    "TrendsService",
    "SimilarMoviesService",
]
