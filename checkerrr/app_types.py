"""
Data classes для типизации данных
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class SubscriptionResult:
    """Результат проверки подписки"""
    is_subscribed: bool
    failed_channels: List[str]
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass
class SearchResult:
    """Результат поиска фильма"""
    movies: List[Dict[str, Any]]
    query: str
    search_type: str  # 'code', 'title', 'actor', 'director', 'genre'
    total_count: int
    page: int = 1
    total_pages: int = 1


@dataclass
class MovieInfo:
    """Информация о фильме"""
    id: int
    code: str
    title: str
    link: str
    year: Optional[int]
    description: Optional[str]
    poster_url: Optional[str]
    banner_url: Optional[str]
    trailer_url: Optional[str]
    quality: str
    views: int
    rating: Optional[float]
    duration: Optional[int]
    genres: List[str] = field(default_factory=list)
    actors: List[str] = field(default_factory=list)
    directors: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None


@dataclass
class UserInfo:
    """Информация о пользователе"""
    user_id: int
    total_searches: int = 0
    total_visits: int = 0
    favorites_count: int = 0
    last_search_at: Optional[datetime] = None
    first_visit_at: Optional[datetime] = None
    is_subscribed: bool = True
    language: str = "ru"
    notifications_enabled: bool = True


@dataclass
class AchievementInfo:
    """Информация о достижении"""
    achievement_type: str
    name_ru: str
    name_en: str
    description_ru: str
    description_en: str
    icon: str
    unlocked_at: Optional[datetime] = None
    is_unlocked: bool = False


@dataclass
class UserStats:
    """Статистика пользователя"""
    user_id: int
    total_searches: int
    total_visits: int
    favorites_count: int
    last_search_at: Optional[datetime]
    first_visit_at: Optional[datetime]
    achievements: List[AchievementInfo] = field(default_factory=list)


@dataclass
class SearchIntent:
    """Намерение поиска"""
    type: str  # 'code', 'title', 'actor', 'director', 'genre'
    query: str
    original_text: str


@dataclass
class ChannelInfo:
    """Информация о канале"""
    name: str
    link: str
    chat_id: str
    id: Optional[int] = None


@dataclass
class MovieEditData:
    """Данные для редактирования фильма"""
    code: str
    field: str
    value: Any


@dataclass
class NotificationInfo:
    """Информация об уведомлении"""
    user_id: int
    movie_code: str
    movie_title: str
    sent_at: Optional[datetime] = None
    is_read: bool = False


@dataclass
class ReactionInfo:
    """Реакция на фильм"""
    user_id: int
    movie_id: int
    movie_code: str
    reaction_type: str  # 'like', 'dislike'
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TrendInfo:
    """Трендовая информация"""
    movie_code: str
    movie_title: str
    views_count: int
    period: str  # 'day', 'week', 'month'
    rank: int


@dataclass
class HealthStatus:
    """Статус здоровья компонента"""
    component: str
    status: str  # 'ok', 'warning', 'error'
    message: str
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass
class CacheStats:
    """Статистика кэша"""
    hits: int = 0
    misses: int = 0
    size: int = 0
    ttl: int = 0
