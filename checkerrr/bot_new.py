"""
Checkerrr Bot - основной файл
Рефакторинг 2026
"""
import asyncio
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from config import Config
from database import Database
from cache import init_cache, SubscriptionCache, get_cache
from healthcheck import init_health_checker, get_health_checker

# Middleware
from middlewares.subscription import SubscriptionMiddleware, VisitsLoggingMiddleware

# Handlers
from handlers import (
    user_commands_router,
    new_features_router,
    reactions_router,
    menu_buttons_router,
    callbacks_router,
    search_admin_router,
    search_only_router,
)

# Services
from services import (
    NotificationService,
    AchievementService,
    ReactionService,
    TrendsService,
    SimilarMoviesService,
)

# Utils
from texts import get_text
from keyboards import get_main_keyboard, get_channels_keyboard
from utils import (
    validate_movie_code,
    format_year_line,
    format_duration_line,
    format_rating_line,
    normalize_code_for_search,
    extract_search_intent,
    resolve_actor_alias,
    resolve_director_alias,
    resolve_genre_alias,
)

# Constants
from constants import (
    MOVIES_PER_PAGE,
    CACHE_TTL,
    SEARCH_CACHE_TTL,
    SUBSCRIPTION_CACHE_TTL,
    MOVIE_CACHE_TTL,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==================== GLOBAL OBJECTS ====================

try:
    config = Config()
    db = Database(config.DATABASE_PATH)
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    
    # Services
    notification_service = None
    achievement_service = None
    reaction_service = None
    trends_service = None
    similar_movies_service = None
    
    logger.info("✅ Бот инициализирован успешно")
except Exception as e:
    logger.critical(f"❌ Ошибка инициализации: {e}", exc_info=True)
    raise


# ==================== HELPER FUNCTIONS ====================

async def check_subscription_cached(
    user_id: int, 
    force_check: bool = False,
    db: Database = None,
    config: Config = None,
    bot: Bot = None
) -> dict:
    """
    Проверка подписки пользователя с кэшированием
    
    Returns:
        dict: {'is_subscribed': bool, 'failed_channels': list}
    """
    from app_types import SubscriptionResult
    
    cached = await SubscriptionCache.get(user_id)
    if cached and not force_check:
        return {
            'is_subscribed': cached.get('is_subscribed', True),
            'failed_channels': cached.get('failed_channels', [])
        }
    
    # Проверка cooldown
    last_check_time = getattr(check_subscription_cached, '_last_check_time', {})
    check_cooldown = 5  # seconds
    
    if not force_check:
        last_time = last_check_time.get(user_id)
        if last_time and (datetime.now() - last_time).total_seconds() < check_cooldown:
            if cached:
                return {
                    'is_subscribed': cached.get('is_subscribed', True),
                    'failed_channels': cached.get('failed_channels', [])
                }
    
    # Получаем каналы
    channels_db = db.get_channels()
    channels = [
        {"name": ch["name"], "link": ch["link"], "id": ch["chat_id"]}
        for ch in (channels_db or config.CHANNELS)
    ]
    
    if not channels:
        result = {'is_subscribed': True, 'failed_channels': []}
        await _save_subscription_result(user_id, result)
        return result
    
    is_subscribed = True
    failed_channels = []
    
    for channel in channels:
        raw_id = str(channel['id']).strip()
        if not raw_id:
            continue
        
        try:
            # Парсинг chat_id
            if raw_id.lstrip('-').isdigit():
                chat_id = int(raw_id)
            elif raw_id.startswith('@'):
                chat_id = raw_id
            else:
                chat_id = '@' + raw_id.lstrip('@')
            
            chat_member = await bot.get_chat_member(chat_id, user_id)
            status = chat_member.status
            
            if status not in ["member", "administrator", "creator"]:
                is_subscribed = False
                failed_channels.append(channel['name'])
                
        except Exception as e:
            logger.error(f"Ошибка проверки '{channel['name']}' для {user_id}: {e}")
            is_subscribed = False
            failed_channels.append(channel['name'])
    
    result = {'is_subscribed': is_subscribed, 'failed_channels': failed_channels}
    await _save_subscription_result(user_id, result)
    return result


async def _save_subscription_result(user_id: int, result: dict) -> None:
    """Сохранение результата проверки подписки"""
    await SubscriptionCache.set(
        user_id, 
        result['is_subscribed'], 
        result['failed_channels'], 
        SUBSCRIPTION_CACHE_TTL
    )
    
    # Сохраняем время последней проверки
    if not hasattr(check_subscription_cached, '_last_check_time'):
        check_subscription_cached._last_check_time = {}
    check_subscription_cached._last_check_time[user_id] = datetime.now()
    
    db.update_user_subscription(user_id, result['is_subscribed'])


def get_failed_channels_keyboard(failed_channels_names: list, lang: str):
    """Возвращает клавиатуру только с каналами, на которые не подписан пользователь"""
    from keyboards import get_channels_keyboard
    
    all_channels = db.get_channels() or config.CHANNELS
    failed_channels = [ch for ch in all_channels if ch['name'] in failed_channels_names]
    return get_channels_keyboard(failed_channels, lang) if failed_channels else get_channels_keyboard(all_channels, lang)


# ==================== MIDDLEWARE REGISTRATION ====================

async def register_middlewares():
    """Регистрация middleware"""
    # Middleware для логирования посещений
    visits_middleware = VisitsLoggingMiddleware(
        db=db,
        admin_ids=config.ADMIN_IDS
    )
    
    # Регистрируем middleware
    dp.message.middleware(visits_middleware)
    dp.callback_query.middleware(visits_middleware)
    
    logger.info("✅ Middleware зарегистрированы")


# ==================== ROUTER REGISTRATION ====================

async def register_routers():
    """Регистрация роутеров"""
    # Включаем роутеры в диспетчер
    dp.include_router(user_commands_router)
    dp.include_router(new_features_router)
    dp.include_router(reactions_router)
    dp.include_router(menu_buttons_router)
    dp.include_router(callbacks_router)
    dp.include_router(search_admin_router)
    dp.include_router(search_only_router)
    
    logger.info("✅ Роутеры зарегистрированы")


# ==================== SERVICES INITIALIZATION ====================

async def init_services():
    """Инициализация сервисов"""
    global notification_service, achievement_service, reaction_service, trends_service, similar_movies_service
    
    notification_service = NotificationService(bot, db)
    achievement_service = AchievementService(db)
    reaction_service = ReactionService(db)
    trends_service = TrendsService(db)
    similar_movies_service = SimilarMoviesService(db)
    
    logger.info("✅ Сервисы инициализированы")


# ==================== MAIN ====================

async def main():
    """Основная функция запуска"""
    logger.info("🚀 Запуск бота...")
    
    # Инициализация каналов
    if not db.get_channels():
        for ch in config.CHANNELS:
            if ch.get('id') and ch.get('link'):
                db.add_channel(ch['name'], ch['link'], ch['id'])
        logger.info("✅ Каналы инициализированы из config")
    
    # Инициализация сервисов
    await init_services()
    
    # Регистрация middleware
    await register_middlewares()
    
    # Регистрация роутеров
    await register_routers()
    
    # Инициализация кэша
    cache = init_cache()
    logger.info("✅ Кэш инициализирован")
    
    # Health check
    if config.ENABLE_HEALTH_CHECK:
        checker = get_health_checker()
        if checker:
            await checker.check_all()
            logger.info(f"✅ Health check: {checker.get_status_text()}")
    
    # Запуск polling с передачей зависимостей
    try:
        await dp.start_polling(bot, db=db, config=config)
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
    finally:
        await bot.session.close()
        await get_cache().close()
        db.close()
        logger.info("✅ Бот остановлен корректно")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
