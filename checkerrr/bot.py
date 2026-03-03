import asyncio
import logging
import csv
import os
from datetime import datetime, timedelta
import re

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile

from config import Config
from database import Database
from keyboards import *
from texts import get_text
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
from cache import init_cache, SearchCache, SubscriptionCache, MovieCache, get_cache
from healthcheck import init_health_checker, get_health_checker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    config = Config()
    db = Database(config.DATABASE_PATH)
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    # Middleware для проверки подписки
    async def subscription_middleware(handler, event, data):
        """Middleware для проверки подписки пользователя"""
        # Получаем user_id из разных типов событий
        user_id = None
        if hasattr(event, 'from_user'):
            user_id = event.from_user.id
        elif hasattr(event, 'message') and hasattr(event.message, 'from_user'):
            user_id = event.message.from_user.id
        elif hasattr(event, 'callback_query') and hasattr(event.callback_query, 'from_user'):
            user_id = event.callback_query.from_user.id

        if user_id is None:
            return await handler(event, data)

        # Админы пропускают проверку
        if user_id in config.ADMIN_IDS:
            return await handler(event, data)

        # Проверяем подписку
        result = await check_subscription_cached(user_id, force_check=False)

        # Если не подписан и это не команда /start или /help
        if not result['is_subscribed']:
            # Разрешаем только определенные команды
            if hasattr(event, 'text'):
                text = event.text.strip() if event.text else ''
                if text in ['/start', '/help', '/language', '/lang', '/support']:
                    return await handler(event, data)

            # Разрешаем определенные callback query
            if hasattr(event, 'callback_query') and hasattr(event.callback_query, 'data'):
                cb_data = event.callback_query.data
                allowed_callbacks = ['check_subscription', 'cancel_to_main', 'back_to_menu', 'back_to_main']
                if any(cb_data.startswith(prefix) for prefix in allowed_callbacks):
                    return await handler(event, data)

            # Блокируем и показываем сообщение о необходимости подписки
            lang = db.get_user_language(user_id)
            all_channels = db.get_channels() or config.CHANNELS
            
            # Фильтруем только те каналы, на которые не подписан
            failed_channels = [ch for ch in all_channels if ch['name'] in result['failed_channels']]
            failed = "\n".join([f"• {ch['name']}" for ch in failed_channels])

            if hasattr(event, 'message') and hasattr(event.message, 'answer'):
                await event.message.answer(
                    get_text("subscription_check_failed", lang, failed_channels=failed),
                    reply_markup=get_channels_keyboard(failed_channels, lang),
                    disable_web_page_preview=True
                )
            elif hasattr(event, 'answer'):
                await event.answer(
                    get_text("subscription_check_failed", lang, failed_channels=failed),
                    show_alert=True
                )
            return

        return await handler(event, data)

    # Регистрируем middleware для сообщений и callback query
    dp.message.middleware(subscription_middleware)
    dp.callback_query.middleware(subscription_middleware)

    # Middleware для логирования посещений пользователей
    async def visits_middleware(handler, event, data):
        """Middleware для логирования посещений пользователей (исключая админов)"""
        user_id = None
        if hasattr(event, 'from_user'):
            user_id = event.from_user.id
        elif hasattr(event, 'message') and hasattr(event.message, 'from_user'):
            user_id = event.message.from_user.id
        elif hasattr(event, 'callback_query') and hasattr(event.callback_query, 'from_user'):
            user_id = event.callback_query.from_user.id

        if user_id is not None and user_id not in config.ADMIN_IDS:
            # Логируем посещение (асинхронно, чтобы не блокировать)
            try:
                db.log_user_visit(user_id)
            except Exception as e:
                logger.error(f"Ошибка логирования посещения для {user_id}: {e}")

        return await handler(event, data)

    # Регистрируем middleware для логирования посещений
    dp.message.middleware(visits_middleware)
    dp.callback_query.middleware(visits_middleware)

    def get_failed_channels_keyboard(failed_channels_names: list, lang: str):
        """Возвращает клавиатуру только с каналами, на которые не подписан пользователь"""
        all_channels = db.get_channels() or config.CHANNELS
        failed_channels = [ch for ch in all_channels if ch['name'] in failed_channels_names]
        return get_channels_keyboard(failed_channels, lang) if failed_channels else get_channels_keyboard(all_channels, lang)

    if config.USE_REDIS:
        cache = init_cache(host=config.REDIS_HOST, port=config.REDIS_PORT, password=config.REDIS_PASSWORD)
        asyncio.run(cache.connect())
    else:
        cache = init_cache()
        logger.info("✅ Используем in-memory кэш")

    if config.ENABLE_HEALTH_CHECK:
        health_checker = init_health_checker(config.DATABASE_PATH, config.BOT_TOKEN)
        logger.info("✅ Health checker инициализирован")

    logger.info("✅ Бот инициализирован успешно")
except Exception as e:
    logger.critical(f"❌ Ошибка инициализации: {e}", exc_info=True)
    raise

subscription_cache: dict = {}
cache_ttl = timedelta(seconds=config.CACHE_TTL)
last_check_time: dict = {}
check_cooldown = timedelta(seconds=5)


class SearchStates(StatesGroup):
    """Состояния для поиска по категориям"""
    waiting_for_genre = State()
    waiting_for_actor = State()
    waiting_for_director = State()


class AdminStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_link = State()
    waiting_for_csv = State()
    waiting_for_edit = State()
    waiting_for_edit_file = State()  # Для загрузки файлов
    waiting_for_broadcast = State()
    waiting_for_year = State()
    waiting_for_quality = State()
    waiting_for_rating = State()
    waiting_for_genres = State()
    waiting_for_description = State()


async def check_subscription_cached(user_id: int, force_check: bool = False) -> dict:
    cached = await SubscriptionCache.get(user_id)
    if cached and not force_check:
        return cached

    if not force_check:
        last_time = last_check_time.get(user_id)
        if last_time and (datetime.now() - last_time < check_cooldown):
            if cached:
                return cached

    channels_db = db.get_channels()
    channels = (
        [{"name": ch["name"], "link": ch["link"], "id": ch["chat_id"]} for ch in channels_db]
        if channels_db else config.CHANNELS
    )

    if not channels:
        return {'is_subscribed': True, 'failed_channels': []}

    is_subscribed = True
    failed_channels = []

    for channel in channels:
        raw_id = str(channel['id']).strip()
        if not raw_id:
            continue
        try:
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
            else:
                logger.debug(f"Пользователь {user_id} подписан на '{channel['name']}'")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка проверки '{channel['name']}' для {user_id}: {error_msg}")
            is_subscribed = False
            failed_channels.append(channel['name'])

    await SubscriptionCache.set(user_id, is_subscribed, failed_channels, config.SUBSCRIPTION_CACHE_TTL)
    subscription_cache[user_id] = {'is_subscribed': is_subscribed, 'failed_channels': failed_channels, 'checked_at': datetime.now()}
    last_check_time[user_id] = datetime.now()
    db.update_user_subscription(user_id, is_subscribed)

    return {'is_subscribed': is_subscribed, 'failed_channels': failed_channels}


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    result = await check_subscription_cached(user_id, force_check=True)

    if result['is_subscribed']:
        await message.answer(get_text("start_subscribed", lang), reply_markup=get_main_keyboard(lang, is_admin=is_admin), parse_mode="Markdown")
    else:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']]) if result['failed_channels'] else "Подпишитесь на все каналы"
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    await message.answer(get_text("command_help", lang), reply_markup=get_main_keyboard(lang, is_admin=is_admin), parse_mode="Markdown")


@dp.message(Command("language"))
async def cmd_language(message: types.Message):
    user_id = message.from_user.id
    current_lang = db.get_user_language(user_id)
    new_lang = "en" if current_lang == "ru" else "ru"
    is_admin = user_id in config.ADMIN_IDS
    db.set_user_language(user_id, new_lang)
    await message.answer(get_text("language_changed", new_lang), reply_markup=get_main_keyboard(new_lang, is_admin=is_admin))


@dp.message(Command("support"))
async def cmd_support(message: types.Message):
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    await message.answer(get_text("command_support", lang, support_link=config.SUPPORT_LINK),
                         reply_markup=get_main_keyboard(lang, is_admin=is_admin), parse_mode="Markdown", disable_web_page_preview=True)


@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    result = await check_subscription_cached(user_id, force_check=True)
    status = get_text("subscription_status_subscribed" if result['is_subscribed'] else "subscription_status_not_subscribed", lang)
    await message.answer(get_text("command_debug", lang, user_id=user_id, lang=lang, subscription_status=status),
                         reply_markup=get_main_keyboard(lang, is_admin=True), parse_mode="Markdown")


@dp.message(Command("channels"))
async def cmd_channels(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    channels_db = db.get_channels()
    text = get_text("admin_channels_title", lang)
    if channels_db:
        text += get_text("admin_channels_from_db", lang)
        for i, ch in enumerate(channels_db, 1):
            text += f"{i}. {ch['name']}\n   ID: `{ch['chat_id']}`\n   Link: {ch['link']}\n\n"
    else:
        text += get_text("admin_channels_from_config", lang)
        for i, ch in enumerate(config.CHANNELS, 1):
            text += f"{i}. {ch['name']}\n   ID: `{ch['id']}`\n   Link: {ch['link']}\n\n"
    text += get_text("admin_channels_warning", lang)
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    try:
        movies = db.get_all_movies(limit=10000)
        output = [['code', 'title', 'year', 'description', 'link', 'poster_url', 'quality', 'views', 'rating']]
        for movie in movies:
            output.append([movie['code'], movie['title'], movie['year'] or '', movie['description'] or '',
                           movie['link'], movie['poster_url'] or '', movie['quality'], movie['views'], movie.get('rating', '') or ''])
        with open('movies_export.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(output)
        with open('movies_export.csv', 'rb') as file:
            caption = get_text("admin_import_success", lang).format(added="OK", skipped="0").replace("OK", "").replace("\n⏭️ Пропущено: 0", "") + "✅"
            await message.answer_document(BufferedInputFile(file.read(), filename='movies_export.csv'), caption=get_text("admin_export_started", lang))
    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        await message.answer(get_text("admin_export_error", lang, error=str(e)))


@dp.message(Command("import"))
async def cmd_import_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    await message.answer(get_text("admin_import_start", lang))
    await state.set_state(AdminStates.waiting_for_csv)


@dp.message(AdminStates.waiting_for_csv, F.document)
async def cmd_import_file(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    if not message.document.filename.endswith('.csv'):
        await message.answer(get_text("admin_csv_invalid", lang))
        return
    try:
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, 'movies_import.csv')
        added, skipped = 0, 0
        with open('movies_import.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    year = int(row['year']) if row.get('year') and row['year'].strip() else None
                    rating = float(row['rating']) if row.get('rating') and row['rating'].strip() else None
                    if db.add_movie(code=row['code'].strip(), title=row['title'].strip(), link=row['link'].strip(),
                                    year=year, description=row.get('description', '').strip(),
                                    poster_url=row.get('poster_url', '').strip(),
                                    quality=row.get('quality', '1080p').strip(), rating=rating):
                        added += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error(f"Ошибка импорта строки {row.get('code', 'unknown')}: {e}")
                    continue
        await message.answer(get_text("admin_import_success", lang, added=added, skipped=skipped))
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка импорта: {e}")
        await message.answer(get_text("admin_export_error", lang, error=str(e)))
        await state.clear()


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    stats = db.get_general_stats()
    text = get_text("admin_stats_general", lang, total_movies=stats.get('total_movies', 0),
                    total_views=stats.get('total_views', 0), active_users=stats.get('active_users', 0),
                    searches_today=stats.get('searches_today', 0), searches_week=stats.get('searches_week', 0))
    await message.answer(text, reply_markup=get_stats_keyboard(lang))


@dp.message(Command("health"))
async def cmd_health(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    checker = get_health_checker()
    if checker:
        await checker.check_all()
        await message.answer(checker.get_status_text(), parse_mode="Markdown")
    else:
        await message.answer(get_text("admin_health_not_init", lang))


@dp.message(F.text.in_({"ℹ️ Помощь", "ℹ️ Instructions"}))
async def help_command(message: types.Message):
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    await message.answer(get_text("help", lang), reply_markup=get_main_keyboard(lang, is_admin=is_admin), parse_mode="Markdown")


@dp.message(F.text.in_({"🌐 Язык", "🌐 Language"}))
async def change_language(message: types.Message):
    user_id = message.from_user.id
    current_lang = db.get_user_language(user_id)
    new_lang = "en" if current_lang == "ru" else "ru"
    is_admin = user_id in config.ADMIN_IDS
    db.set_user_language(user_id, new_lang)
    await message.answer(get_text("language_changed", new_lang), reply_markup=get_main_keyboard(new_lang, is_admin=is_admin))


@dp.message(F.text.in_({"🛠 Поддержка", "🛠 Support"}))
async def support(message: types.Message):
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    await message.answer(get_text("command_support", lang, support_link=config.SUPPORT_LINK),
                         reply_markup=get_main_keyboard(lang, is_admin=is_admin), parse_mode="Markdown", disable_web_page_preview=True)


@dp.message(F.text.in_({"👑 Админ-панель", "👑 Admin Panel"}))
async def admin_panel(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    await message.answer(get_text("admin_panel_title", lang), reply_markup=get_admin_keyboard(lang))


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Команда /admin для открытия админ-панели"""
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    await message.answer(get_text("admin_panel_title", lang), reply_markup=get_admin_keyboard(lang))


@dp.message(F.text == "🔍 Найти фильм")
async def find_movie_button(message: types.Message):
    """Кнопка 'Найти фильм' - показывает подсказку"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    await message.answer(
        "🔍 **Поиск фильма**\n\n"
        "Введите:\n"
        "• Код фильма (например: `1`, `001`)\n"
        "• Название фильма\n"
        "• Имя актёра\n"
        "• Жанр (боевик, комедия...)",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(lang, is_admin=is_admin)
    )


@dp.message(F.text == "🎭 Поиск по жанру")
async def search_by_genre_button(message: types.Message, state: FSMContext):
    """Кнопка 'Поиск по жанру' - показывает список жанров"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    genres = db.get_all_genres()
    if not genres:
        await message.answer(
            get_text("genres_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        return

    text = get_text("genres_select", lang)
    for genre in genres[:20]:
        text += f"• {genre['name']}\n"

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_genres_keyboard(genres[:20], lang)
    )


@dp.message(F.text == "🎬 Поиск по актёру")
async def search_by_actor_button(message: types.Message, state: FSMContext):
    """Кнопка 'Поиск по актёру' - показывает список актёров (страница 1)"""
    await show_actors_page(message, page=1)


async def show_actors_page(message, page: int = 1):
    """Показывает страницу актёров"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    limit = 10
    offset = (page - 1) * limit
    actors = db.get_all_actors(limit=limit, offset=offset)
    total_count = db.get_actors_count()
    total_pages = (total_count + limit - 1) // limit

    if not actors:
        await message.answer(
            get_text("actors_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        return

    text = get_text("actors_select", lang, page=page, total_pages=total_pages)
    for i, actor in enumerate(actors, 1):
        text += f"{i}. {actor['name']} ({actor['film_count']} фил.)\n"

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_actors_keyboard(actors, lang, page=page, total_pages=total_pages)
    )


@dp.message(F.text == "🎥 Поиск по режиссёру")
async def search_by_director_button(message: types.Message, state: FSMContext):
    """Кнопка 'Поиск по режиссёру' - показывает список режиссёров (страница 1)"""
    await show_directors_page(message, page=1)


async def show_directors_page(message, page: int = 1):
    """Показывает страницу режиссёров"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    limit = 10
    offset = (page - 1) * limit
    directors = db.get_all_directors(limit=limit, offset=offset)
    total_count = db.get_directors_count()
    total_pages = (total_count + limit - 1) // limit

    if not directors:
        await message.answer(
            get_text("directors_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        return

    text = get_text("directors_select", lang, page=page, total_pages=total_pages)
    for i, director in enumerate(directors, 1):
        text += f"{i}. {director['name']} ({director['film_count']} фил.)\n"

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_directors_keyboard(directors, lang, page=page, total_pages=total_pages)
    )


@dp.message(F.text == "⭐ Избранное")
async def favorites_button(message: types.Message):
    """Кнопка 'Избранное' в главном меню"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    favorites = db.get_user_favorites(user_id)

    if not favorites:
        await message.answer(
            get_text("favorites_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=user_id in config.ADMIN_IDS)
        )
        return

    text = get_text("favorites_list", lang, count=len(favorites))
    for movie in favorites[:10]:
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"🎬 {movie['title']}{year_line} — `{movie['code']}`\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=get_favorites_keyboard(favorites, lang))


@dp.message(F.text == "🔥 Топ фильмов")
async def top_movies_button(message: types.Message):
    """Кнопка 'Топ фильмов' в главном меню"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    top = db.get_top_movies(limit=10)

    if not top:
        await message.answer(get_text("top_movies_empty", lang), reply_markup=get_main_keyboard(lang, is_admin=user_id in config.ADMIN_IDS))
        return

    text = get_text("admin_top_movies", lang)
    for i, movie in enumerate(top, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}` 👁 {movie['views']}\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=get_search_results_keyboard(top, lang))


@dp.message(F.text == "🎭 Жанры")
async def genres_button(message: types.Message):
    """Кнопка 'Жанры' - пока не используется"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    await message.answer(
        get_text("genres_unavailable", lang),
        reply_markup=get_main_keyboard(lang, is_admin=user_id in config.ADMIN_IDS)
    )


@dp.message(F.text == "📜 История")
async def history_button(message: types.Message):
    """Кнопка 'История' в главном меню"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        return

    history = db.get_user_search_history(user_id, limit=10)

    if not history:
        await message.answer(
            get_text("search_history_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=user_id in config.ADMIN_IDS)
        )
        return

    text = get_text("search_history", lang)
    for item in history:
        icon = "✅" if item['results_count'] > 0 else "❌"
        text += f"{icon} {item['query']} ({item['query_type']})\n"

    await message.answer(text)


@dp.callback_query(F.data == "admin_add_movie")
async def admin_add_movie(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text("Отправьте код фильма (только цифры, максимум 10 символов):\n\nПримеры: `1`, `001`, `MATRIX`",
                                     parse_mode="Markdown", reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel"))
    await state.set_state(AdminStates.waiting_for_code)


@dp.message(AdminStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    """Обработка кода - для добавления или удаления фильма"""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    code = message.text.strip()

    # Проверяем контекст - удаление это или добавление
    # Если в data есть 'delete_mode' - это режим удаления
    if data.get('delete_mode'):
        movie = db.get_movie_by_code(code)
        if not movie:
            await message.answer(f"❌ Фильм с кодом `{code}` не найден.", parse_mode="Markdown")
            return

        await message.answer(
            f"🗑 Удалить фильм?\n\n"
            f"🎬 {movie['title']} ({movie['code']})\n"
            f"📅 {movie.get('year', 'N/A')}\n"
            f"👁 {movie.get('views', 0)} просмотров",
            reply_markup=get_delete_confirm_keyboard(code, lang)
        )
        await state.clear()
        return

    # Режим добавления фильма
    code_clean = re.sub(r'[^\w]', '', code.upper())
    if not code_clean or len(code_clean) > 10:
        await message.answer(get_text("error_invalid_code", lang))
        return
    
    # ✅ ПРОВЕРКА НА ДУПЛИКАТЫ С УЧЁТОМ УНИВЕРСАЛЬНОГО ПОИСКА
    if db.check_code_duplicate(code_clean):
        await message.answer(
            f"❌ Код `{code_clean}` уже занят!\n\n"
            f"Коды `1`, `01`, `001` и т.д. считаются одинаковыми.\n"
            f"Используйте другой код.",
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(code=code_clean)
    await message.answer(f"✅ Код `{code_clean}` принят.\n\nТеперь отправьте название фильма:", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_title)


@dp.message(AdminStates.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    title = message.text.strip()
    if len(title) < 2:
        await message.answer(get_text("error_invalid_title", lang))
        return
    await state.update_data(title=title)
    data = await state.get_data()
    await message.answer(f"✅ Название: {title}\n\nТеперь отправьте ссылку на фильм (http/https):", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_link)


@dp.message(AdminStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(message.from_user.id)
    link = message.text.strip()
    if not link.startswith(('http://', 'https://')):
        await message.answer(get_text("error_invalid_link", lang), parse_mode="Markdown", reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel"))
        return
    
    await state.update_data(link=link)
    await message.answer(
        f"✅ Ссылка принята.\n\n"
        f"Теперь отправьте год выпуска (например: 2023) или про������устите:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state(AdminStates.waiting_for_year)


@dp.message(AdminStates.waiting_for_year)
async def process_year(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip()
    year = None

    if text.isdigit() and 1900 <= int(text) <= 2030:
        year = int(text)

    await state.update_data(year=year)
    await message.answer(
        f"✅ Год: {year if year else 'пропущен'}\n\n"
        f"Теперь отправьте качество (480p, 720p, 1080p, 4K) или пропустите:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state(AdminStates.waiting_for_quality)


@dp.message(AdminStates.waiting_for_quality)
async def process_quality(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)

    text = message.text.strip().lower()
    quality = "1080p"  # по умолчанию
    
    if text in ["480p", "720p", "1080p", "4k"]:
        quality = text.upper() if text == "4k" else text
    
    await state.update_data(quality=quality)
    await message.answer(
        f"✅ Качество: {quality}\n\n"
        f"Теперь отправьте рейтинг (0.0-10.0) или пропу��тите:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state(AdminStates.waiting_for_rating)


@dp.message(AdminStates.waiting_for_rating)
async def process_rating(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip()
    rating = 7.5  # по умолчанию

    try:
        rating_val = float(text.replace(',', '.'))
        if 0 <= rating_val <= 10:
            rating = rating_val
    except ValueError:
        pass

    await state.update_data(rating=rating)
    await message.answer(
        f"✅ Рейтинг: {rating}\n\n"
        f"Теперь отправьте жанры через запятую (например: боевик, фантастика) или пропустите:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state(AdminStates.waiting_for_genres)


@dp.message(AdminStates.waiting_for_genres)
async def process_genres(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    genres_text = message.text.strip()
    genres = []
    
    if genres_text and genres_text.lower() != "пропустить":
        genres = [g.strip() for g in genres_text.split(',')]
    
    await state.update_data(genres=genres)
    
    # Получаем все данные и добавляем фильм
    data = await state.get_data()
    
    try:
        success = db.add_movie(
            code=data['code'],
            title=data['title'],
            link=data['link'],
            year=data.get('year'),
            description='',
            poster_url='',
            quality=data.get('quality', '1080p'),
            rating=data.get('rating', 7.5),
            genres=data.get('genres', [])
        )

        if success:
            logger.info(f"Фильм добавлен: код={data['code']}, название={data['title']}")
            await message.answer(
                f"✅ ФИЛЬМ ДОБАВЛЕН!\n\n"
                f"Код: `{data['code']}`\n"
                f"Название: {data['title']}\n"
                f"Год: {data.get('year', 'N/A')}\n"
                f"Качество: {data.get('quality', '1080p')}\n"
                f"Рейтинг: {data.get('rating', 7.5)}\n"
                f"Жанры: {', '.join(data.get('genres', [])) if data.get('genres') else 'N/A'}\n"
                f"Ссылка: {data['link']}\n\n"
                f"💡 Пользователи могут найти его по коду `{data['code']}`",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(lang, is_admin=True)
            )
        else:
            await message.answer(
                f"❌ Не удалось добавить фильм.\n"
                f"Код `{data['code']}` уже используется.",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(lang, is_admin=True)
            )

    except Exception as e:
        logger.error(f"Ошибка добавления фильма: {e}", exc_info=True)
        await message.answer(
            f"❌ ОШИБКА:\n`{str(e)}`",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(lang, is_admin=True)
        )

    await state.clear()


@dp.message(AdminStates.waiting_for_edit)
async def process_edit(message: types.Message, state: FSMContext):
    """Обработка данных для редактирования фильма"""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    code = data.get('edit_code')
    field = data.get('edit_field')
    value = message.text.strip()

    if not code or not field:
        await message.answer(get_text("error_data_not_found", lang))
        await state.clear()
        return

    # Преобразуем значение
    if field == "year":
        if value.isdigit() and 1900 <= int(value) <= 2030:
            value = int(value)
        else:
            await message.answer(get_text("error_invalid_year", lang))
            return
    elif field == "rating":
        try:
            value = float(value.replace(',', '.'))
            if not (0 <= value <= 10):
                await message.answer(get_text("error_invalid_rating", lang))
                return
        except ValueError:
            await message.answer(get_text("error_invalid_rating_format", lang))
            return
    elif field == "quality":
        value = value.upper()
        if value not in ["480P", "720P", "1080P", "4K"]:
            await message.answer(get_text("error_invalid_quality", lang))
            return
    elif field in ["link", "poster_url", "banner_url", "trailer_url"]:
        if not value.startswith(('http://', 'https://')):
            await message.answer(get_text("error_invalid_link", lang))
            return

    # Обновляем фильм
    try:
        db.update_movie(code, **{field: value})
        movie = db.get_movie_by_code(code)
        
        await message.answer(
            f"✅ Фильм обновлён!\n\n"
            f"🎬 {movie['title']}\n"
            f"{field}: {value}",
            parse_mode="Markdown",
            reply_markup=get_movie_edit_keyboard(code, lang)
        )
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


@dp.message(AdminStates.waiting_for_edit_file, F.photo)
async def process_edit_photo(message: types.Message, state: FSMContext):
    """Обработка загруженно��о фото (постер/баннер)"""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    code = data.get('edit_code')
    field = data.get('edit_field')  # poster_url или banner_url

    if not code or not field:
        await message.answer(get_text("error_data_not_found", lang))
        await state.clear()
        return

    # Получаем фото (наибольшее качество)
    photo = message.photo[-1]

    # Создаём папку media если нет
    import os
    os.makedirs("media", exist_ok=True)
    
    # Скачиваем файл
    file = await bot.get_file(photo.file_id)
    file_name = f"{code}_{field}_{photo.file_unique_id}.jpg"
    file_path = os.path.join("media", file_name)
    abs_file_path = os.path.abspath(file_path)
    
    await bot.download_file(file.file_path, file_path)
    
    logger.info(f"Файл с��ачан: {file_path} → {abs_file_path}")

    # Сохраняем путь в БД
    try:
        db.update_movie(code, **{field: file_path})
        movie = db.get_movie_by_code(code)

        # Преобразуем имя поля в читаемое название
        field_names = {
            'poster_url': 'Постер',
            'banner_url': 'Баннер',
            'trailer_url': 'Трейлер'
        }
        field_name = field_names.get(field, field)

        # Пр������������веряем что файл существует
        if os.path.exists(abs_file_path):
            file_size = os.path.getsize(abs_file_path)
            await message.answer(
                f"✅ {field_name} обновлён!\n\n"
                f"🎬 {movie['title']}\n"
                f"📁 Файл: {file_path}\n"
                f"📊 Размер: {file_size} байт",
                reply_markup=get_movie_edit_keyboard(code, lang)
            )
        else:
            await message.answer(
                f"⚠️ {field_name} сохранён, но файл не найден!\n\n"
                f"🎬 {movie['title']}\n"
                f"📁 Путь: {file_path}",
                reply_markup=get_movie_edit_keyboard(code, lang)
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


@dp.message(AdminStates.waiting_for_edit_file, F.video)
async def process_edit_video(message: types.Message, state: FSMContext):
    """Обработка загруженного видео (трейлер)"""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    code = data.get('edit_code')
    field = data.get('edit_field')  # trailer_url

    if not code or not field:
        await message.answer(get_text("error_data_not_found", lang))
        await state.clear()
        return

    # Проверяем размер (макс 20MB)
    if message.video.file_size > 20 * 1024 * 1024:
        await message.answer(get_text("error_video_too_large", lang))
        return

    video = message.video
    
    # Создаём папку media если нет
    import os
    os.makedirs("media", exist_ok=True)
    
    # Скачиваем файл
    file = await bot.get_file(video.file_id)
    file_name = f"{code}_{field}_{video.file_unique_id}.mp4"
    file_path = os.path.join("media", file_name)
    abs_file_path = os.path.abspath(file_path)
    
    await bot.download_file(file.file_path, file_path)
    
    logger.info(f"Файл скачан: {file_path} → {abs_file_path}")
    
    # Сохраняем путь в БД
    try:
        db.update_movie(code, **{field: file_path})
        movie = db.get_movie_by_code(code)

        # Преобразуем имя поля в читаемое название
        field_names = {
            'poster_url': 'Постер',
            'banner_url': 'Баннер',
            'trailer_url': 'Трейлер'
        }
        field_name = field_names.get(field, field)

        # Проверяем что файл существует
        if os.path.exists(abs_file_path):
            file_size = os.path.getsize(abs_file_path)
            await message.answer(
                f"✅ {field_name} обновлён!\n\n"
                f"🎬 {movie['title']}\n"
                f"📁 Файл: {file_path}\n"
                f"📊 Размер: {file_size} байт",
                reply_markup=get_movie_edit_keyboard(code, lang)
            )
        else:
            await message.answer(
                f"⚠️ {field_name} сохранён, но файл не найден!\n\n"
                f"🎬 {movie['title']}\n"
                f"📁 Путь: {file_path}",
                reply_markup=get_movie_edit_keyboard(code, lang)
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


@dp.message(AdminStates.waiting_for_edit_file, F.document)
async def process_edit_document(message: types.Message, state: FSMContext):
    """Обработка загруженного файла (если отправили как документ)"""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    code = data.get('edit_code')
    field = data.get('edit_field')

    if not code or not field:
        await message.answer(get_text("error_data_not_found", lang))
        await state.clear()
        return

    doc = message.document
    
    # Проверяем тип файла
    if field in ["poster_url", "banner_url"]:
        if not doc.mime_type.startswith('image/'):
            await message.answer(get_text("error_invalid_image", lang))
            return
        file_ext = "jpg"
    elif field == "trailer_url":
        if not doc.mime_type.startswith('video/'):
            await message.answer(get_text("error_invalid_video", lang))
            return
        file_ext = "mp4"
    else:
        await message.answer(get_text("error_invalid_field", lang))
        await state.clear()
        return

    # Проверяем размер
    if doc.file_size > 20 * 1024 * 1024:
        await message.answer(get_text("error_file_too_large", lang))
        return

    # Скачиваем файл
    file = await bot.get_file(doc.file_id)
    file_path = f"media/{code}_{field}_{doc.file_unique_id}.{file_ext}"
    
    import os
    os.makedirs("media", exist_ok=True)
    
    await bot.download_file(file.file_path, file_path)
    
    # Сохраняем путь в БД
    try:
        db.update_movie(code, **{field: file_path})
        movie = db.get_movie_by_code(code)

        # Преобразуем имя поля в читаемое название
        field_names = {
            'poster_url': 'Постер',
            'banner_url': 'Баннер',
            'trailer_url': 'Трейлер'
        }
        field_name = field_names.get(field, field)

        await message.answer(
            f"✅ {field_name} обновлён!\n\n"
            f"🎬 {movie['title']}",
            reply_markup=get_movie_edit_keyboard(code, lang)
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


@dp.message(AdminStates.waiting_for_edit_file, F.text)
async def process_edit_cancel(message: types.Message, state: FSMContext):
    """Отмена загрузки файла"""
    if message.text.strip() == "🔕":
        await message.answer(get_text("error_cancelled", lang))
        await state.clear()


@dp.callback_query(F.data == "admin_list_movies")
async def admin_list_movies(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    await show_movies_page(callback.message, lang, page=1)


@dp.callback_query(F.data == "admin_delete_movie")
async def admin_delete_movie_start(callback: types.CallbackQuery):
    """Начало удаления фильма - показываем список"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)

    movies = db.get_all_movies(limit=100)
    if not movies:
        await callback.message.edit_text(get_text("admin_movies_empty", lang), reply_markup=get_admin_keyboard(lang))
        return

    text = get_text("admin_delete_title", lang)
    text += "Выберите фильм для удаления:\n\n"

    buttons = []
    for movie in movies[:20]:  # Показываем первые 20
        year_line = f" ({movie['year']})" if movie['year'] else ""
        button_text = f"🎬 {movie['title']}{year_line} — {movie['code']}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"delete_select_{movie['code']}"
        )])

    buttons.append([InlineKeyboardButton(text=get_text("admin_back_button", lang), callback_data="admin_back_to_panel")])

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data == "admin_edit_movie")
async def admin_edit_movie_start(callback: types.CallbackQuery):
    """Начало редактирования фильма - показываем список"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)

    movies = db.get_all_movies(limit=1000)  # Берём больше фильмов
    if not movies:
        await callback.message.edit_text(get_text("admin_movies_empty", lang), reply_markup=get_admin_keyboard(lang))
        return

    text = get_text("admin_edit_title", lang)
    text += "Выберите фильм для редактирования:\n\n"

    buttons = []
    for movie in movies[:50]:  # Показываем первые 50 фильмов
        year_line = f" ({movie['year']})" if movie['year'] else ""
        button_text = f"🎬 {movie['title']}{year_line} — {movie['code']}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"edit_select_{movie['code']}"
        )])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")])

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_select_"))
async def edit_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор фильма для редактирования"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    code = callback.data.replace("edit_select_", "").strip()
    movie = db.get_movie_by_code(code)

    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)

    # Сохраняем код в состоянии
    await state.update_data(edit_code=code)

    text = (
        f"✏️ **Редактирование фильма**\n\n"
        f"🎬 {movie['title']}\n"
        f"📅 Год: {movie.get('year', 'N/A')}\n"
        f"⭐ Код: `{movie['code']}`\n"
        f"📺 Качество: {movie.get('quality', 'N/A')}\n"
        f"⭐ Рейтинг: {movie.get('rating', 'N/A')}\n"
        f"🖼 Постер: {'✅' if movie.get('poster_url') else '❌'}\n"
        f"🎬 Баннер: {'✅' if movie.get('banner_url') else '❌'}\n"
        f"🎥 Трейлер: {'✅' if movie.get('trailer_url') else '❌'}\n\n"
        f"Выберите что хотите изменить:"
    )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_movie_edit_keyboard(movie['code'], lang)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_select_"))
async def delete_select(callback: types.CallbackQuery):
    """Выбор фильма для удаления"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    
    code = callback.data.replace("delete_select_", "").strip()
    movie = db.get_movie_by_code(code)
    
    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    text = (
        f"🗑 **Удаление фильма**\n\n"
        f"🎬 {movie['title']}\n"
        f"📅 Год: {movie.get('year', 'N/A')}\n"
        f"⭐ Код: `{movie['code']}`\n"
        f"👁 Просмотров: {movie.get('views', 0)}\n\n"
        f"Вы уверены что хотите удалить этот фильм?"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_delete_confirm_keyboard(movie['code'], lang)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_confirmed_"))
async def delete_confirmed(callback: types.CallbackQuery):
    """Подтверждение удаления фильма"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    lang = db.get_user_language(callback.from_user.id)
    code = callback.data.replace("delete_confirmed_", "").strip()

    logger.info(f"Удаление фильма: code={code}")

    movie = db.get_movie_by_code(code)
    if movie:
        result = db.delete_movie(code)
        logger.info(f"Результат удаления: {result}")
        if result:
            await callback.message.edit_text(
                f"✅ Фильм «{movie['title']}» (код: {code}) удалён",
                reply_markup=get_admin_keyboard(lang)
            )
        else:
            await callback.message.edit_text(
                f"❌ Не удалось удалить фильм «{movie['title']}»",
                reply_markup=get_admin_keyboard(lang)
            )
    else:
        await callback.message.edit_text("❌ Фильм не найден", reply_markup=get_admin_keyboard(lang))

    await callback.answer()


# ==================== ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ ====================

@dp.callback_query(F.data.startswith("edit_title_"))
async def edit_title_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования названия"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_title_", "").strip()
    await state.update_data(edit_code=code, edit_field="title")
    await callback.message.answer(get_text("edit_send_title", lang))
    await state.set_state(AdminStates.waiting_for_edit)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_link_"))
async def edit_link_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования ссылки"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_link_", "").strip()
    await state.update_data(edit_code=code, edit_field="link")
    await callback.message.answer(get_text("edit_send_link", lang))
    await state.set_state(AdminStates.waiting_for_edit)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_year_"))
async def edit_year_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования года"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_year_", "").strip()
    await state.update_data(edit_code=code, edit_field="year")
    await callback.message.answer(get_text("edit_send_year", lang))
    await state.set_state(AdminStates.waiting_for_edit)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_quality_"))
async def edit_quality_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования качества"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_quality_", "").strip()
    await state.update_data(edit_code=code, edit_field="quality")
    await callback.message.answer(get_text("edit_send_quality", lang))
    await state.set_state(AdminStates.waiting_for_edit)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_rating_"))
async def edit_rating_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования рейтинга"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_rating_", "").strip()
    await state.update_data(edit_code=code, edit_field="rating")
    await callback.message.answer(get_text("edit_send_rating", lang))
    await state.set_state(AdminStates.waiting_for_edit)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_poster_"))
async def edit_poster_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования постера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_poster_", "").strip()
    await state.update_data(edit_code=code, edit_field="poster_url")
    await callback.message.answer(
        "🖼 **Загрузка постера**\n\n"
        "Отправьте изображение как файл (не сжатое) или фото.\n\n"
        "Или отправьте 🔕 для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_edit_file)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_banner_"))
async def edit_banner_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_banner_", "").strip()
    await state.update_data(edit_code=code, edit_field="banner_url")
    await callback.message.answer(
        "🎬 **Загрузка баннера**\n\n"
        "Отправьте изображение как файл (не сжатое) или фото.\n\n"
        "Или отправьте 🔕 для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_edit_file)
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_trailer_"))
async def edit_trailer_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования трейлера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    code = callback.data.replace("edit_trailer_", "").strip()
    await state.update_data(edit_code=code, edit_field="trailer_url")
    await callback.message.answer(
        "🎥 **Загрузка трейлера**\n\n"
        "Отправьте видео файл (до 20MB).\n\n"
        "Или отправьте 🔕 для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_edit_file)
    await callback.answer()


async def show_movies_page(message: types.Message, lang: str, page: int = 1):
    PAGE_SIZE = config.MOVIES_PER_PAGE
    total_count = db.get_movies_count()
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))

    offset = (page - 1) * PAGE_SIZE
    movies = db.get_all_movies(limit=PAGE_SIZE, offset=offset)

    if not movies:
        await message.edit_text(get_text("admin_movies_empty_hint", lang), reply_markup=get_admin_keyboard(lang))
        return

    text = get_text("admin_movie_list", lang, page=page, total_pages=total_pages, total=total_count)
    start_idx = (page - 1) * PAGE_SIZE
    for i, movie in enumerate(movies, start=start_idx + 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        views = f" 👁 {movie['views']}" if movie['views'] else ""
        text += f"{i}. `{movie['code']}` - {movie['title']}{year_line}{views}\n"
    try:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_movies_keyboard(lang, page, total_pages))
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_movies_keyboard(lang, page, total_pages))


@dp.callback_query(F.data.startswith("admin_page_"))
async def admin_navigate_page(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    try:
        page = int(callback.data.replace("admin_page_", ""))
        await show_movies_page(callback.message, lang, page=page)
        await callback.answer()
    except ValueError:
        await callback.answer("❌ Некорректная страница", show_alert=True)


@dp.callback_query(F.data == "admin_back_to_panel")
async def admin_back_to_panel(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text("👑 Админ-панель", reply_markup=get_admin_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "admin_import_export")
async def admin_import_export(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        "📤 **Экспорт / Импорт**\n\n"
        "Выберите действие:",
        reply_markup=get_admin_import_export_keyboard(lang),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_import_start")
async def admin_import_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        "📥 **Импорт фильмов**\n\n"
        "Отправьте CSV файл с фильмами.\n\n"
        "Формат: code,title,year,description,link,poster_url,quality,views,rating",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state(AdminStates.waiting_for_csv)
    await callback.answer()


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Кнопка назад в пользовательское меню"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    
    await callback.message.edit_text(
        "🎬 Главное меню",
        reply_markup=get_main_keyboard(lang, is_admin=is_admin),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_export")
async def admin_export(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    await cmd_export(callback.message)
    await callback.answer("✅ Экспорт запущен", show_alert=False)


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_general_stats()
    text = get_text("admin_stats_general", lang, total_movies=stats.get('total_movies', 0),
                    total_views=stats.get('total_views', 0), active_users=stats.get('active_users', 0),
                    searches_today=stats.get('searches_today', 0), searches_week=stats.get('searches_week', 0))
    await callback.message.edit_text(text, reply_markup=get_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "stats_general")
async def stats_general(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_general_stats()
    text = get_text("admin_stats_general", lang, total_movies=stats.get('total_movies', 0),
                    total_views=stats.get('total_views', 0), active_users=stats.get('active_users', 0),
                    searches_today=stats.get('searches_today', 0), searches_week=stats.get('searches_week', 0))
    await callback.message.edit_text(text, reply_markup=get_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "stats_top_day")
async def stats_top_day(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    top = db.get_top_movies(limit=10, period_days=1)
    text = get_text("admin_stats_top", lang, period="за день")
    for i, movie in enumerate(top, 1):
        text += f"{i}. `{movie['code']}` - {movie['title']} ({movie['views']} просмотров)\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "stats_top_week")
async def stats_top_week(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    top = db.get_top_movies(limit=10, period_days=7)
    text = get_text("admin_stats_top", lang, period="за неделю")
    for i, movie in enumerate(top, 1):
        text += f"{i}. `{movie['code']}` - {movie['title']} ({movie['views']} просмотров)\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "stats_empty_searches")
async def stats_empty_searches(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    empty = db.get_empty_searches_stats(period_days=config.EMPTY_SEARCHES_LOG_DAYS)
    text = get_text("admin_empty_searches", lang, days=config.EMPTY_SEARCHES_LOG_DAYS)
    if empty:
        for item in empty[:15]:
            text += f"• `{item['query']}` ({item['query_type']}) — {item['count']} раз\n"
    else:
        text += "Пустых запросов не найдено"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_stats_keyboard(lang))
    await callback.answer()


# ==================== USER STATISTICS ====================

@dp.callback_query(F.data == "admin_user_stats")
async def admin_user_stats(callback: types.CallbackQuery):
    """Показывает общую статистику пользователей (за всё время)"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    
    stats = db.get_user_visits_stats(admin_ids=config.ADMIN_IDS)
    
    # Форматируем топ пользователей
    top_users_list = ""
    if stats.get('top_users'):
        for i, user in enumerate(stats['top_users'][:10], 1):
            top_users_list += f"{i}. ID {user['user_id']} — {user['visit_count']} посещений\n"
    else:
        top_users_list = "Нет данных"
    
    # Форматируем новых пользователей
    new_users_list = ""
    if stats.get('new_users'):
        for i, user in enumerate(stats['new_users'][:10], 1):
            new_users_list += f"{i}. ID {user['user_id']} — {user['first_visit']}\n"
    else:
        new_users_list = "Нет данных"
    
    text = get_text(
        "admin_user_stats_full", lang,
        total_visits=stats.get('total_visits', 0),
        unique_users=stats.get('unique_users', 0),
        visits_today=stats.get('visits_today', 0),
        visits_week=stats.get('visits_week', 0),
        visits_month=stats.get('visits_month', 0),
        top_users_list=top_users_list,
        new_users_list=new_users_list
    )
    
    await callback.message.edit_text(text, reply_markup=get_user_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "user_stats_day")
async def user_stats_day(callback: types.CallbackQuery):
    """Статистика пользователей за день"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    
    stats = db.get_user_visits_stats(admin_ids=config.ADMIN_IDS, period_days=1)
    
    top_users_list = ""
    if stats.get('top_users'):
        for i, user in enumerate(stats['top_users'][:10], 1):
            top_users_list += f"{i}. ID {user['user_id']} — {user['visit_count']} посещений\n"
    else:
        top_users_list = "Нет данных"
    
    text = get_text(
        "admin_user_stats", lang, period="день",
        total_visits=stats.get('total_visits', 0),
        unique_users=stats.get('unique_users', 0),
        visits_today=stats.get('visits_today', 0),
        visits_week=stats.get('visits_week', 0),
        visits_month=stats.get('visits_month', 0),
        top_users_list=top_users_list
    )
    
    await callback.message.edit_text(text, reply_markup=get_user_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "user_stats_week")
async def user_stats_week(callback: types.CallbackQuery):
    """Статистика пользователей за неделю"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    
    stats = db.get_user_visits_stats(admin_ids=config.ADMIN_IDS, period_days=7)
    
    top_users_list = ""
    if stats.get('top_users'):
        for i, user in enumerate(stats['top_users'][:10], 1):
            top_users_list += f"{i}. ID {user['user_id']} — {user['visit_count']} посещений\n"
    else:
        top_users_list = "Нет данных"
    
    text = get_text(
        "admin_user_stats", lang, period="неделю",
        total_visits=stats.get('total_visits', 0),
        unique_users=stats.get('unique_users', 0),
        visits_today=stats.get('visits_today', 0),
        visits_week=stats.get('visits_week', 0),
        visits_month=stats.get('visits_month', 0),
        top_users_list=top_users_list
    )
    
    await callback.message.edit_text(text, reply_markup=get_user_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "user_stats_month")
async def user_stats_month(callback: types.CallbackQuery):
    """Статистика пользователей за месяц"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    
    stats = db.get_user_visits_stats(admin_ids=config.ADMIN_IDS, period_days=30)
    
    top_users_list = ""
    if stats.get('top_users'):
        for i, user in enumerate(stats['top_users'][:10], 1):
            top_users_list += f"{i}. ID {user['user_id']} — {user['visit_count']} посещений\n"
    else:
        top_users_list = "Нет данных"
    
    text = get_text(
        "admin_user_stats", lang, period="месяц",
        total_visits=stats.get('total_visits', 0),
        unique_users=stats.get('unique_users', 0),
        visits_today=stats.get('visits_today', 0),
        visits_week=stats.get('visits_week', 0),
        visits_month=stats.get('visits_month', 0),
        top_users_list=top_users_list
    )
    
    await callback.message.edit_text(text, reply_markup=get_user_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "user_stats_all")
async def user_stats_all(callback: types.CallbackQuery):
    """Статистика пользователей за всё время"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    
    stats = db.get_user_visits_stats(admin_ids=config.ADMIN_IDS)
    
    top_users_list = ""
    if stats.get('top_users'):
        for i, user in enumerate(stats['top_users'][:10], 1):
            top_users_list += f"{i}. ID {user['user_id']} — {user['visit_count']} посещений\n"
    else:
        top_users_list = "Нет данных"
    
    new_users_list = ""
    if stats.get('new_users'):
        for i, user in enumerate(stats['new_users'][:10], 1):
            new_users_list += f"{i}. ID {user['user_id']} — {user['first_visit']}\n"
    else:
        new_users_list = "Нет данных"
    
    text = get_text(
        "admin_user_stats_full", lang,
        total_visits=stats.get('total_visits', 0),
        unique_users=stats.get('unique_users', 0),
        visits_today=stats.get('visits_today', 0),
        visits_week=stats.get('visits_week', 0),
        visits_month=stats.get('visits_month', 0),
        top_users_list=top_users_list,
        new_users_list=new_users_list
    )
    
    await callback.message.edit_text(text, reply_markup=get_user_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "user_stats_list")
async def user_stats_list(callback: types.CallbackQuery):
    """Список пользователей с детальной статистикой"""
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    lang = db.get_user_language(callback.from_user.id)
    
    users = db.get_all_users_stats(admin_ids=config.ADMIN_IDS, limit=50)
    
    users_list = ""
    if users:
        for user in users[:30]:
            sub_status = "✅" if user.get('is_subscribed') else "❌"
            last_search = user.get('last_search_at', 'Никогда') or 'Никогда'
            if last_search != 'Никогда':
                last_search = last_search[:16]  # Обрезаем до YYYY-MM-DD HH:MM
            created_at = user.get('created_at', 'Неизвестно') or 'Неизвестно'
            if created_at != 'Неизвестно':
                created_at = created_at[:16]
            
            users_list += (
                f"👤 ID `{user['user_id']}`\n"
                f"   🔍 Поисков: {user.get('total_searches', 0)}\n"
                f"   📊 Посещений: {user.get('total_visits', 0)}\n"
                f"   ⭐ В избранном: {user.get('favorites_count', 0)}\n"
                f"   {sub_status} Подписка | 📅 Рег: {created_at}\n\n"
            )
    else:
        users_list = "Нет данных"
    
    text = get_text("admin_user_list", lang, count=len(users), users_list=users_list)
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_user_stats_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    """Кнопка 'Меню' - возвращает в главное меню из любого места"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    
    # Очищаем все FSM состояния
    await state.clear()
    
    try:
        await callback.message.edit_text(
            get_text("command_start", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    except Exception:
        # Если сообщение нельзя редактировать - отправляем новое
        await callback.message.answer(
            get_text("command_start", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    await callback.answer()


@dp.callback_query(F.data == "cancel_to_main")
async def cancel_to_main(callback: types.CallbackQuery, state: FSMContext):
    """Кнопка 'Отмена' - отменяет операцию и возвращает в ��еню"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    
    await state.clear()
    
    try:
        await callback.message.edit_text(
            "❌ Операция отменена",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
    except Exception:
        await callback.message.answer(
            "❌ Операция отменена",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
    await callback.answer()


@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    wait_msg = await callback.message.answer(get_text("subscription_check_timer", lang, seconds=3))
    await asyncio.sleep(2)
    result = await check_subscription_cached(user_id, force_check=True)
    await wait_msg.delete()
    if result['is_subscribed']:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(get_text("subscription_check_passed", lang), reply_markup=get_main_keyboard(lang, is_admin=is_admin), parse_mode="Markdown")
    else:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
    await callback.answer()


@dp.message(F.text)
async def search_movie(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    original_text = message.text.strip()
    is_admin = user_id in config.ADMIN_IDS

    # Проверяем состояние - если в админке, пропускаем
    current_state = await state.get_state()
    logger.debug(f"State check: {current_state}")
    if current_state and 'AdminStates' in current_state:
        logger.debug(f"User {user_id} in AdminState, skipping search")
        return

    result = await check_subscription_cached(user_id)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                             reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang))
        return

    # Проверяем, не является ли текст кнопкой меню
    menu_buttons = [
        "👑 Админ-панель", "Admin Panel", "ℹ️ Инструкция", "ℹ️ Instructions",
        "🌐 Язык", "🌐 Language", "🛠 Поддержка", "🛠 Support",
        "🔍 Найти фильм", "⭐ Избранное", "🔥 Топ фильмов", "📜 История",
        "🎭 Поиск по жанру", "🎬 Поиск по актёру", "🎥 Поиск по режиссёру"
    ]
    if original_text in menu_buttons:
        return

    # Проверка на пустой запрос
    if len(original_text) < 1:
        await message.answer(get_text("search_empty_query", lang), reply_markup=get_main_keyboard(lang, is_admin=is_admin))
        return

    # Проверяем тип поиска
    intent = extract_search_intent(original_text)
    search_type = intent['type']
    query = intent['query']
    logger.info(f"Поиск: user={user_id}, type={search_type}, query={query}")
    
    # === ПОИСК ПО КОДУ РАБОТАЕТ ВСЕГДА ===
    if search_type == 'code':
        # Очищаем любое состояние
        await state.clear()
        
        cleaned_input = re.sub(r'[^\w]', '', query.upper())
        movie = db.get_movie_by_code(cleaned_input)

        if not movie and cleaned_input.isdigit():
            normalized = normalize_code_for_search(cleaned_input)
            movie = db.get_movie_by_code(normalized)

        if not movie and cleaned_input.isdigit():
            num = int(cleaned_input)
            for fmt in ["{:03d}", "{:04d}", "{:02d}", "{:05d}"]:
                padded = fmt.format(num)
                movie = db.get_movie_by_code(padded)
                if movie:
                    break

        if movie:
            await MovieCache.set_by_code(movie['code'], movie, config.MOVIE_CACHE_TTL)
            
            if config.ENABLE_SEARCH_HISTORY:
                db.log_user_search(user_id, query, 'code', 1, movie['id'])
            
            db.increment_views(movie['code'])
            db.log_view(movie.get('id'), user_id)
            movie = db.get_movie_by_code(movie['code'])
            genres = db.get_movie_genres(movie.get('id', 0))
            year_line = format_year_line(movie.get('year'))
            duration_line = format_duration_line(movie.get('duration'))
            rating_line = format_rating_line(movie.get('rating'))

            if genres:
                response = get_text("movie_found_with_genres", lang, title=movie['title'], year_line=year_line,
                                    duration_line=duration_line, rating_line=rating_line, genres=", ".join(genres),
                                    code=movie['code'], quality=movie['quality'], views=movie['views'], link=movie['link'])
            else:
                response = get_text("movie_found", lang, title=movie['title'], year_line=year_line,
                                    duration_line=duration_line, rating_line=rating_line,
                                    code=movie['code'], quality=movie['quality'], views=movie['views'], link=movie['link'])

            # Добавляем трейлер если есть
            if movie.get('trailer_url'):
                trailer_path = movie['trailer_url']
                import os
                if not trailer_path.startswith('/'):
                    trailer_path = os.path.abspath(trailer_path)

                if os.path.exists(trailer_path):
                    from aiogram.types import FSInputFile
                    try:
                        # Отправляем постер с трейлером как видео
                        if movie.get('poster_url'):
                            poster_path = movie['poster_url']
                            if not poster_path.startswith('/'):
                                poster_path = os.path.abspath(poster_path)

                            if os.path.exists(poster_path):
                                await message.answer_photo(
                                    photo=FSInputFile(poster_path),
                                    caption=response,
                                    reply_markup=get_movie_inline_keyboard(movie['code'], lang)
                                )
                                return
                            else:
                                # Постера нет, отправляем трейлер как видео
                                await message.answer_video(
                                    video=FSInputFile(trailer_path),
                                    caption=response,
                                    reply_markup=get_movie_inline_keyboard(movie['code'], lang)
                                )
                                return
                        else:
                            # Отправляем только трейлер как видео
                            await message.answer_video(
                                video=FSInputFile(trailer_path),
                                caption=response,
                                reply_markup=get_movie_inline_keyboard(movie['code'], lang)
                            )
                            return
                    except Exception as e:
                        logger.warning(f"Ошибка отправки трейлера: {e}")
                        response += f"\n\n🎥 Трейлер: {trailer_path}"
                else:
                    response += f"\n\n🎥 Трейлер: {trailer_path}"

            # Отправляем с постером если есть (и нет трейлера)
            if movie.get('poster_url'):
                poster_path = movie['poster_url']
                import os
                if not poster_path.startswith('/'):
                    poster_path = os.path.abspath(poster_path)

                if os.path.exists(poster_path):
                    from aiogram.types import FSInputFile
                    try:
                        await message.answer_photo(
                            photo=FSInputFile(poster_path),
                            caption=response,
                            reply_markup=get_movie_inline_keyboard(movie['code'], lang)
                        )
                        return
                    except Exception as e:
                        logger.warning(f"Ошибка отправки постера: {e}")

            # Если нет постера или ошибка - отправляем текстом
            await message.answer(
                response,
                reply_markup=get_movie_inline_keyboard(movie['code'], lang),
                disable_web_page_preview=True
            )
            return
        else:
            # Код не найден
            await message.answer(
                f"❌ Фильм с кодом `{original_text}` не найден\n\n"
                "Проверьте код и попробуйте снова.",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(lang, is_admin=is_admin)
            )
            return

    # === ЕСЛИ НЕ КОД - ПРОВЕРЯЕМ СОСТОЯНИЯ ПОИСКА ПО КАТЕГОРИЯМ ===
    current_state = await state.get_state()
    
    if current_state == "SearchStates:waiting_for_genre":
        # Поиск по жанру (текстом)
        genre_resolved = resolve_genre_alias(original_text)
        movies = db.search_movies_by_genre_fuzzy(genre_resolved, limit=20)
        await state.clear()
        
        if not movies:
            await message.answer(
                f"❌ Фильмы жанра \"{original_text}\" не найдены\n\n"
                "Попробуйте другой жанр или выберите из списка.",
                reply_markup=get_main_keyboard(lang, is_admin=is_admin)
            )
            return
        
        text = f"🎭 **Жанр: {genre_resolved}**\n\nНайдено фильмов: {len(movies)}\n\n"
        for i, movie in enumerate(movies[:10], 1):
            year_line = f" ({movie['year']})" if movie['year'] else ""
            text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"
        
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_search_results_keyboard(movies[:10], lang)
        )
        return
    
    elif current_state == "SearchStates:waiting_for_actor":
        # Поиск по актёру (текстом)
        actor_resolved = resolve_actor_alias(original_text)
        movies = db.search_movies_by_actor_fuzzy(actor_resolved, limit=20)
        await state.clear()
        
        if not movies:
            await message.answer(
                f"❌ Фильмы с актёром \"{original_text}\" не найдены\n\n"
                "Попробуйте другое имя или выберите из списка.",
                reply_markup=get_main_keyboard(lang, is_admin=is_admin)
            )
            return
        
        text = f"🎬 **Актёр: {actor_resolved}**\n\nНайдено фильмов: {len(movies)}\n\n"
        for i, movie in enumerate(movies[:10], 1):
            year_line = f" ({movie['year']})" if movie['year'] else ""
            text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"
        
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_search_results_keyboard(movies[:10], lang)
        )
        return
    
    elif current_state == "SearchStates:waiting_for_director":
        # Поиск по режиссёру (текстом)
        director_resolved = resolve_director_alias(original_text)
        movies = db.search_movies_by_director_fuzzy(director_resolved, limit=20)
        await state.clear()
        
        if not movies:
            await message.answer(
                f"❌ Фильмы режиссёра \"{original_text}\" не найдены\n\n"
                "Попробуйте другое имя или выберите из списка.",
                reply_markup=get_main_keyboard(lang, is_admin=is_admin)
            )
            return
        
        text = f"🎥 **Режиссёр: {director_resolved}**\n\nНайдено фильмов: {len(movies)}\n\n"
        for i, movie in enumerate(movies[:10], 1):
            year_line = f" ({movie['year']})" if movie['year'] else ""
            text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"
        
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_search_results_keyboard(movies[:10], lang)
        )
        return

    # Если ничего не найдено
    await message.answer(get_text("search_not_found", lang), parse_mode="Markdown", reply_markup=get_main_keyboard(lang, is_admin=is_admin))


# ==================== CALLBACKS ДЛЯ ПОИСКА ПО КАТЕГОРИЯМ ====================

@dp.callback_query(F.data.startswith("genre_page_"))
async def genre_page_change(callback: types.CallbackQuery):
    """Переключение страницы жанра"""
    # Извлекаем номер страницы из callback_data (формат: genre_page_жанр_2)
    parts = callback.data.replace("genre_page_", "", 1).rsplit("_", 1)
    page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
    await show_genre_movies(callback, page=page)


@dp.callback_query(F.data.startswith("genre_"))
async def select_genre(callback: types.CallbackQuery):
    """Выбор жанра из inline-клавиатуры (страница 1)"""
    await show_genre_movies(callback, page=1)


async def show_genre_movies(callback: types.CallbackQuery, page: int = 1):
    """Показывает фильмы выбранного жанра с пагинацией"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    # Извлекаем имя жанра из callback_data
    # Формат: genre_жанр или genre_page_жанр_2
    if callback.data.startswith("genre_page_"):
        # Формат: genre_page_жанр_2 - извлекаем жанр и страницу
        data = callback.data.replace("genre_page_", "", 1)
        parts = data.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            genre_name = parts[0]
        else:
            genre_name = data
    else:
        genre_name = callback.data.replace("genre_", "", 1)

    # Применяем alias для жанра
    genre_resolved = resolve_genre_alias(genre_name)

    # Получаем общее количество фильмов
    total_count = db.get_movies_by_genre_count(genre_resolved)
    limit = 10
    total_pages = (total_count + limit - 1) // limit

    if total_pages < 1:
        total_pages = 1
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * limit
    movies = db.get_movies_by_genre_paginated(genre_resolved, limit=limit, offset=offset)

    if not movies:
        await callback.answer("❌ Фильмы этого жанра не найдены", show_alert=True)
        return

    text = f"🎭 **Жанр: {genre_resolved}**\n\n"
    text += f"Найдено фильмов: {total_count} (страница {page}/{total_pages})\n\n"
    for i, movie in enumerate(movies, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"

    # Пытаемся редактировать сообщение, если не получается - отправляем новое
    try:
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_genre_movies_keyboard(genre_name, movies, lang, page=page, total_pages=total_pages)
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_genre_movies_keyboard(genre_name, movies, lang, page=page, total_pages=total_pages)
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("actor_"))
async def select_actor(callback: types.CallbackQuery):
    """Выбор актёра из inline-клавиатуры"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    actor_hash = callback.data.replace("actor_", "", 1)

    # Получаем всех актёров (без лимита) и ищем по хэшу
    all_actors = db.get_all_actors(limit=10000, offset=0)
    import hashlib
    actor_name = None
    for actor in all_actors:
        if hashlib.md5(actor['name'].encode('utf-8')).hexdigest()[:16] == actor_hash:
            actor_name = actor['name']
            break

    if not actor_name:
        await callback.answer("❌ Актёр не найден", show_alert=True)
        return

    # Применяем alias для актёра
    actor_resolved = resolve_actor_alias(actor_name)

    movies = db.search_movies_by_actor_fuzzy(actor_resolved, limit=20)

    if not movies:
        await callback.answer("❌ Фильмы с этим актёром не найдены", show_alert=True)
        return

    text = f"🎬 **Актёр: {actor_resolved}**\n\nНайдено фильмов: {len(movies)}\n\n"
    for i, movie in enumerate(movies[:10], 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"

    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_search_results_keyboard(movies[:10], lang)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("director_"))
async def select_director(callback: types.CallbackQuery):
    """Выбор режиссёра из inline-клавиатуры"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    director_hash = callback.data.replace("director_", "", 1)

    # Получаем всех режиссёров (без лимита) и ищем по хэшу
    all_directors = db.get_all_directors(limit=10000, offset=0)
    import hashlib
    director_name = None
    for director in all_directors:
        if hashlib.md5(director['name'].encode('utf-8')).hexdigest()[:16] == director_hash:
            director_name = director['name']
            break

    if not director_name:
        await callback.answer("❌ Режиссёр не найден", show_alert=True)
        return

    # Применяем alias для режиссёра
    director_resolved = resolve_director_alias(director_name)

    movies = db.search_movies_by_director_fuzzy(director_resolved, limit=20)

    if not movies:
        await callback.answer("❌ Фильмы этого режиссёра не найдены", show_alert=True)
        return

    text = f"🎥 **Режиссёр: {director_resolved}**\n\nНайдено фильмов: {len(movies)}\n\n"
    for i, movie in enumerate(movies[:10], 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"

    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_search_results_keyboard(movies[:10], lang)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("actors_page_"))
async def actors_page_callback(callback: types.CallbackQuery):
    """Пагинация актёров"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    page_data = callback.data.replace("actors_page_", "")
    
    if page_data == "info":
        await callback.answer()
        return
    
    try:
        page = int(page_data)
    except ValueError:
        await callback.answer()
        return

    # Проверяем подписку
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    limit = 10
    offset = (page - 1) * limit
    actors = db.get_all_actors(limit=limit, offset=offset)
    total_count = db.get_actors_count()
    total_pages = (total_count + limit - 1) // limit

    if not actors:
        await callback.answer("❌ Актёры не найдены", show_alert=True)
        return

    text = f"🎬 **Актёры** (страница {page}/{total_pages})\n\n"
    text += "Выберите актёра или введите имя текстом:\n\n"
    for i, actor in enumerate(actors, 1):
        text += f"{i}. {actor['name']} ({actor['film_count']} фил.)\n"

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_actors_keyboard(actors, lang, page=page, total_pages=total_pages)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("directors_page_"))
async def directors_page_callback(callback: types.CallbackQuery):
    """Пагинация режиссёров"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    page_data = callback.data.replace("directors_page_", "")
    
    if page_data == "info":
        await callback.answer()
        return
    
    try:
        page = int(page_data)
    except ValueError:
        await callback.answer()
        return

    # Проверяем подписку
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    limit = 10
    offset = (page - 1) * limit
    directors = db.get_all_directors(limit=limit, offset=offset)
    total_count = db.get_directors_count()
    total_pages = (total_count + limit - 1) // limit

    if not directors:
        await callback.answer("❌ Режиссёры не найдены", show_alert=True)
        return

    text = f"🎥 **Режиссёры** (страница {page}/{total_pages})\n\n"
    text += "Выберите режиссёра или введите имя текстом:\n\n"
    for i, director in enumerate(directors, 1):
        text += f"{i}. {director['name']} ({director['film_count']} фил.)\n"

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_directors_keyboard(directors, lang, page=page, total_pages=total_pages)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("fav_add_"))
async def fav_add(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    code = callback.data.replace("fav_add_", "")
    movie = db.get_movie_by_code(code)
    if movie:
        db.add_to_favorites(user_id, movie['id'])
        await callback.answer(get_text("favorites_added", "ru"), show_alert=True)
    else:
        await callback.answer("❌ Фильм не найден", show_alert=True)


@dp.callback_query(F.data.startswith("fav_remove_"))
async def fav_remove(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    code = callback.data.replace("fav_remove_", "")
    movie = db.get_movie_by_code(code)
    if movie:
        db.remove_from_favorites(user_id, movie['id'])
        await callback.answer("❌ Удалено из избранного", show_alert=True)
        
        # Обно��ляем список избранного
        lang = db.get_user_language(user_id)
        favorites = db.get_user_favorites(user_id)
        
        if not favorites:
            await callback.message.edit_text(
                get_text("favorites_empty", lang),
                reply_markup=get_main_keyboard(lang, is_admin=user_id in config.ADMIN_IDS)
            )
        else:
            text = get_text("favorites_list", lang, count=len(favorites))
            for m in favorites[:10]:
                year_line = f" ({m['year']})" if m['year'] else ""
                text += f"🎬 {m['title']}{year_line} — `{m['code']}`\n"
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=get_favorites_keyboard(favorites, lang)
            )
    else:
        await callback.answer("❌ Фильм не найден", show_alert=True)


@dp.callback_query(F.data == "my_favorites")
async def my_favorites(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    favorites = db.get_user_favorites(user_id)
    if not favorites:
        await callback.message.answer(get_text("favorites_empty", lang))
        await callback.answer()
        return
    text = get_text("favorites_list", lang, count=len(favorites))
    for movie in favorites[:10]:
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"🎬 {movie['title']}{year_line} — `{movie['code']}`\n"
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_favorites_keyboard(favorites, lang))
    await callback.answer()


@dp.callback_query(F.data == "top_movies")
async def top_movies(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    top = db.get_top_movies(limit=10)
    if not top:
        await callback.message.answer(get_text("top_movies_empty", lang))
        await callback.answer()
        return
    text = get_text("admin_stats_top", lang)
    for i, movie in enumerate(top, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}` 👁 {movie['views']}\n"
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_search_results_keyboard(top, lang))
    await callback.answer()


@dp.callback_query(F.data == "search_history")
async def search_history(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Проверка подписки
    result = await check_subscription_cached(user_id, force_check=True)
    if not result['is_subscribed']:
        failed = "\n".join([f"• {ch}" for ch in result['failed_channels']])
        await callback.message.answer(get_text("subscription_check_failed", lang, failed_channels=failed),
                                      reply_markup=get_failed_channels_keyboard(result['failed_channels'], lang), disable_web_page_preview=True)
        await callback.answer()
        return

    history = db.get_user_search_history(user_id, limit=10)
    if not history:
        await callback.message.answer(get_text("search_history_empty", lang))
        await callback.answer()
        return
    text = get_text("search_history", lang)
    for item in history:
        icon = "✅" if item['results_count'] > 0 else "❌"
        text += f"{icon} {item['query']} ({item['query_type']})\n"
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "my_stats")
async def my_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    stats = db.get_user_stats(user_id)
    favorites = db.get_user_favorites(user_id)
    last_search = stats.get('last_search_at', 'Никогда')
    if last_search and isinstance(last_search, str):
        last_search = last_search[:19]
    text = get_text("user_stats", lang, total_searches=stats.get('total_searches', 0),
                    favorites_count=len(favorites), last_search=last_search if last_search else "Никогда")
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data.startswith("movie_"))
async def movie_from_search(callback: types.CallbackQuery):
    code = callback.data.replace("movie_", "")
    movie = db.get_movie_by_code(code)
    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    db.increment_views(movie['code'])
    db.log_view(movie.get('id'), user_id)
    genres = db.get_movie_genres(movie.get('id', 0))
    year_line = format_year_line(movie.get('year'))
    duration_line = format_duration_line(movie.get('duration'))
    rating_line = format_rating_line(movie.get('rating'))
    
    # Формируем текст
    if genres:
        response = get_text("movie_found_with_genres", lang, title=movie['title'], year_line=year_line,
                            duration_line=duration_line, rating_line=rating_line, genres=", ".join(genres),
                            code=movie['code'], quality=movie['quality'], views=movie['views'], link=movie['link'])
    else:
        response = get_text("movie_found", lang, title=movie['title'], year_line=year_line,
                            duration_line=duration_line, rating_line=rating_line, code=movie['code'],
                            quality=movie['quality'], views=movie['views'], link=movie['link'])
    
    # Добавляем трейлер если есть
    if movie.get('trailer_url'):
        response += f"\n\n🎥 Трейлер: {movie['trailer_url']}"
    
    # Отправляем с постером если есть
    if movie.get('poster_url'):
        poster_path = movie['poster_url']
        
        # Преобразуем относительный путь в абсолютный
        import os
        if not poster_path.startswith('/'):
            poster_path = os.path.abspath(poster_path)
        
        # Проверяем что файл существует
        if os.path.exists(poster_path):
            from aiogram.types import FSInputFile
            try:
                logger.info(f"Отправка постера: {poster_path}")
                await callback.message.answer_photo(
                    photo=FSInputFile(poster_path),
                    caption=response,
                    reply_markup=get_movie_inline_keyboard(movie['code'], lang)
                )
                await callback.answer()
                return
            except Exception as e:
                logger.error(f"Ошибка о��правки постера: {e}", exc_info=True)
        else:
            logger.warning(f"Постер не найден: {poster_path}")
    
    # Если нет постера или ошибка - отправляем текстом
    await callback.message.answer(
        response,
        reply_markup=get_movie_inline_keyboard(movie['code'], lang),
        disable_web_page_preview=True
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("search_page_"))
async def search_page_callback(callback: types.CallbackQuery):
    """Пагинация результатов поис��а"""
    page_data = callback.data.replace("search_page_", "")
    
    if page_data == "info":
        await callback.answer()
        return
    
    try:
        page = int(page_data)
    except ValueError:
        await callback.answer("❌ Некорректная страница", show_alert=True)
        return
    
    # Пока просто по��азываем номер страницы
    await callback.answer(f"Страница {page}", show_alert=False)


async def main():
    logger.info("🚀 Запуск бота...")
    if not db.get_channels():
        for ch in config.CHANNELS:
            if ch.get('id') and ch.get('link'):
                db.add_channel(ch['name'], ch['link'], ch['id'])
        logger.info("✅ Каналы инициализированы из config")
    if config.ENABLE_HEALTH_CHECK:
        checker = get_health_checker()
        if checker:
            await checker.check_all()
            logger.info(f"✅ Health check: {checker._health_status.get('status', 'unknown')}")
    try:
        await dp.start_polling(bot)
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