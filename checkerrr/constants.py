"""
Константы проекта Checkerrr Bot
"""
from enum import Enum


# ==================== PAGINATION ====================
MOVIES_PER_PAGE = 10
ACTORS_PER_PAGE = 10
DIRECTORS_PER_PAGE = 10
SEARCH_RESULTS_PER_PAGE = 5
MAX_PAGES_IN_KEYBOARD = 5


# ==================== CACHE TTL (seconds) ====================
CACHE_TTL = 60
SEARCH_CACHE_TTL = 600  # 10 минут
SUBSCRIPTION_CACHE_TTL = 60
MOVIE_CACHE_TTL = 3600  # 1 час


# ==================== FILE SIZE LIMITS ====================
MAX_VIDEO_SIZE_MB = 20
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024
MAX_PHOTO_SIZE_MB = 10
MAX_PHOTO_SIZE_BYTES = MAX_PHOTO_SIZE_MB * 1024 * 1024


# ==================== CODE VALIDATION ====================
MAX_CODE_LENGTH = 10
MIN_CODE_LENGTH = 1


# ==================== YEAR RANGE ====================
MIN_YEAR = 1900
MAX_YEAR = 2030


# ==================== RATING RANGE ====================
MIN_RATING = 0.0
MAX_RATING = 10.0
DEFAULT_RATING = 7.5


# ==================== QUALITY OPTIONS ====================
QUALITY_OPTIONS = ["480p", "720p", "1080p", "4K"]
DEFAULT_QUALITY = "1080p"


# ==================== SEARCH LIMITS ====================
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 100
TOP_MOVIES_LIMIT = 10
HISTORY_LIMIT = 10


# ==================== SUBSCRIPTION CHECK ====================
SUBSCRIPTION_CHECK_COOLDOWN = 5  # seconds
SUBSCRIPTION_CHECK_TIMER = 3  # seconds to wait before check


# ==================== ADMIN ====================
EXPORT_LIMIT = 10000
IMPORT_BATCH_SIZE = 100


# ==================== STATISTICS ====================
EMPTY_SEARCHES_LOG_DAYS = 30
USER_STATS_LIMIT = 50
TOP_USERS_LIMIT = 10


# ==================== FEATURES ====================
ENABLE_SIMILAR_MOVIES = True
SIMILAR_MOVIES_COUNT = 5
ENABLE_ACHIEVEMENTS = True
ENABLE_NOTIFICATIONS = True
ENABLE_REMINDERS = True
ENABLE_REACTIONS = True
ENABLE_TRENDS = True


# ==================== ACHIEVEMENTS ====================
class AchievementType(str, Enum):
    FIRST_SEARCH = "first_search"
    SEARCH_10 = "search_10"
    SEARCH_50 = "search_50"
    SEARCH_100 = "search_100"
    FAVORITE_1 = "favorite_1"
    FAVORITE_10 = "favorite_10"
    FAVORITE_50 = "favorite_50"
    DAYS_7 = "days_7"
    DAYS_30 = "days_30"
    DAYS_365 = "days_365"


ACHIEVEMENTS = {
    AchievementType.FIRST_SEARCH: {
        "name_ru": "Первый поиск",
        "name_en": "First Search",
        "description_ru": "Выполнить первый поиск фильма",
        "description_en": "Perform first movie search",
        "icon": "🔍"
    },
    AchievementType.SEARCH_10: {
        "name_ru": "Любопытный",
        "name_en": "Curious",
        "description_ru": "Выполнить 10 поисков",
        "description_en": "Perform 10 searches",
        "icon": "👀"
    },
    AchievementType.SEARCH_50: {
        "name_ru": "Киноман",
        "name_en": "Movie Buff",
        "description_ru": "Выполнить 50 поисков",
        "description_en": "Perform 50 searches",
        "icon": "🎬"
    },
    AchievementType.SEARCH_100: {
        "name_ru": "Гуру кино",
        "name_en": "Cinema Guru",
        "description_ru": "Выполнить 100 поисков",
        "description_en": "Perform 100 searches",
        "icon": "🏆"
    },
    AchievementType.FAVORITE_1: {
        "name_ru": "Коллекционер",
        "name_en": "Collector",
        "description_ru": "Добавить первый фильм в избранное",
        "description_en": "Add first movie to favorites",
        "icon": "⭐"
    },
    AchievementType.FAVORITE_10: {
        "name_ru": "Ценитель",
        "name_en": "Connoisseur",
        "description_ru": "Добавить 10 фильмов в избранное",
        "description_en": "Add 10 movies to favorites",
        "icon": "🌟"
    },
    AchievementType.FAVORITE_50: {
        "name_ru": "Легенда",
        "name_en": "Legend",
        "description_ru": "Добавить 50 фильмов в избранное",
        "description_en": "Add 50 movies to favorites",
        "icon": "💫"
    },
    AchievementType.DAYS_7: {
        "name_ru": "Недельный",
        "name_en": "Weekly",
        "description_ru": "Пользоваться ботом 7 дней",
        "description_en": "Use bot for 7 days",
        "icon": "📅"
    },
    AchievementType.DAYS_30: {
        "name_ru": "Месячный",
        "name_en": "Monthly",
        "description_ru": "Пользоваться ботом 30 дней",
        "description_en": "Use bot for 30 days",
        "icon": "🗓️"
    },
    AchievementType.DAYS_365: {
        "name_ru": "Годовой",
        "name_en": "Yearly",
        "description_ru": "Пользоваться ботом 365 дней",
        "description_en": "Use bot for 365 days",
        "icon": "🎉"
    },
}


# ==================== MENU BUTTONS ====================
MENU_BUTTONS_RU = [
    "👑 Админ-панель",
    "🔍 Найти фильм",
    "🎭 Поиск по жанру",
    "🎬 Поиск по актёру",
    "🎥 Поиск по режиссёру",
    "⭐ Избранное",
    "🔥 Топ фильмов",
    "📜 История",
    "ℹ️ Помощь",
    "🌐 Язык",
    "🛠 Поддержка",
    "🎲 Случайный фильм",
    "🔔 Уведомления",
    "🏆 Достижения",
    "📈 Тренды",
]

MENU_BUTTONS_EN = [
    "👑 Admin Panel",
    "🔍 Find Movie",
    "🎭 Search by Genre",
    "🎬 Search by Actor",
    "🎥 Search by Director",
    "⭐ Favorites",
    "🔥 Top Movies",
    "📜 History",
    "ℹ️ Instructions",
    "🌐 Language",
    "🛠 Support",
    "🎲 Random Movie",
    "🔔 Notifications",
    "🏆 Achievements",
    "📈 Trends",
]


# ==================== LOGGING ====================
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "bot.log"
LOG_LEVEL = "INFO"
