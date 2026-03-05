"""
Обработчики callback query для кнопок
"""
import logging
import os
import base64
from aiogram import F, Router, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import Config as AppConfig
from database import Database
from keyboards import (
    get_main_keyboard,
    get_admin_keyboard,
    get_admin_movies_keyboard,
    get_admin_import_export_keyboard,
    get_stats_keyboard,
    get_user_stats_keyboard,
    get_favorites_keyboard,
    get_search_results_keyboard,
    get_movie_inline_keyboard,
    get_movie_edit_keyboard,
    get_delete_confirm_keyboard,
    get_cancel_keyboard,
    get_channels_keyboard,
    get_genres_keyboard,
    get_actors_keyboard,
    get_directors_keyboard,
    get_genre_movies_keyboard,
)
from texts import get_text
from utils import format_year_line, format_duration_line, format_rating_line

logger = logging.getLogger(__name__)

router = Router()


async def check_sub(user_id: int, db: Database, bot) -> dict:
    """Проверка подписки"""
    from bot_new import check_subscription_cached
    from config import Config
    return await check_subscription_cached(user_id, force_check=True, db=db, config=Config, bot=bot)


# ==================== ИЗБРАННОЕ ====================

@router.callback_query(F.data.startswith("fav_add_"))
async def fav_add(callback: CallbackQuery, db: Database):
    """Добавить в избранное"""
    user_id = callback.from_user.id
    code = callback.data.replace("fav_add_", "")
    movie = db.get_movie_by_code(code)
    if movie:
        db.add_to_favorites(user_id, movie['id'])
        
        # Проверяем достижения
        from services import AchievementService
        from constants import AchievementType
        achievement_service = AchievementService(db)
        await achievement_service.check_and_unlock(user_id, AchievementType.FAVORITE_1)
        await achievement_service.check_and_unlock(user_id, AchievementType.FAVORITE_10)
        await achievement_service.check_and_unlock(user_id, AchievementType.FAVORITE_50)
        
        await callback.answer(get_text("favorites_added", "ru"), show_alert=True)
    else:
        await callback.answer("❌ Фильм не найден", show_alert=True)


@router.callback_query(F.data.startswith("fav_remove_"))
async def fav_remove(callback: CallbackQuery, db: Database):
    """Удалить из избранного"""
    user_id = callback.from_user.id
    code = callback.data.replace("fav_remove_", "")
    movie = db.get_movie_by_code(code)
    if movie:
        db.remove_from_favorites(user_id, movie['id'])
        await callback.answer("❌ Удалено из избранного", show_alert=True)
        
        lang = db.get_user_language(user_id)
        favorites = db.get_user_favorites(user_id)
        
        if not favorites:
            await callback.message.edit_text(
                get_text("favorites_empty", lang),
                reply_markup=get_main_keyboard(lang, is_admin=user_id in AppConfig.ADMIN_IDS)
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


@router.callback_query(F.data == "my_favorites")
async def my_favorites(callback: CallbackQuery, db: Database):
    """Моё избранное"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    favorites = db.get_user_favorites(user_id)
    if not favorites:
        await callback.message.answer(get_text("favorites_empty", lang))
        await callback.answer()
        return
    
    text = get_text("favorites_list", lang, count=len(favorites))
    for movie in favorites[:10]:
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"🎬 {movie['title']}{year_line} — `{movie['code']}`\n"
    
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_favorites_keyboard(favorites, lang)
    )
    await callback.answer()


# ==================== ТОП ФИЛЬМОВ ====================

@router.callback_query(F.data == "top_movies")
async def top_movies(callback: CallbackQuery, db: Database):
    """Топ фильмов"""
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
    
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_search_results_keyboard(top, lang)
    )
    await callback.answer()


# ==================== ИСТОРИЯ ====================

@router.callback_query(F.data == "search_history")
async def search_history(callback: CallbackQuery, db: Database):
    """История поиска"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    history = db.get_user_search_history(user_id, limit=10)
    if not history:
        await callback.message.answer(get_text("search_history_empty", lang))
        await callback.answer()
        return

    text = get_text("search_history", lang)
    for item in history:
        icon = "✅" if item['results_count'] > 0 else "❌"
        query = item['query']
        query_type = item['query_type']
        
        # Если искали по коду - пробуем получить название фильма
        if query_type == 'code' and item.get('found_movie_id'):
            movie = db.get_movie_by_id(item['found_movie_id'])
            if movie:
                text += f"{icon} {movie['title']} (код: {query})\n"
            else:
                text += f"{icon} {query} ({query_type})\n"
        else:
            text += f"{icon} {query} ({query_type})\n"

    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data == "view_history")
async def view_history(callback: CallbackQuery, db: Database):
    """История просмотров фильмов (с кодами)"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    history = db.get_user_view_history(user_id, limit=10)
    if not history:
        await callback.message.answer(get_text("view_history_empty", lang))
        await callback.answer()
        return

    text = get_text("view_history", lang)
    keyboard_buttons = []
    
    for item in history:
        year_line = f" ({item['year']})" if item['year'] else ""
        text += f"🎬 {item['title']}{year_line} — `{item['code']}`\n"
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"🎬 {item['title']}",
            callback_data=f"movie_{item['code']}"
        )])
    
    keyboard_buttons.append([InlineKeyboardButton(
        text="🔙 В меню",
        callback_data="back_to_main"
    )])

    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await callback.answer()


# ==================== СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ====================

@router.callback_query(F.data == "my_stats")
async def my_stats(callback: CallbackQuery, db: Database):
    """Моя статистика"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    stats = db.get_user_stats(user_id)
    favorites = db.get_user_favorites(user_id)
    last_search = stats.get('last_search_at', 'Никогда')
    if last_search and isinstance(last_search, str):
        last_search = last_search[:19]
    
    text = get_text("user_stats", lang,
                    total_searches=stats.get('total_searches', 0),
                    favorites_count=len(favorites),
                    last_search=last_search if last_search else "Никогда")
    
    await callback.message.answer(text)
    await callback.answer()


# ==================== ФИЛЬМ ИЗ ПОИСКА ====================

@router.callback_query(F.data.startswith("movie_"))
async def movie_from_search(callback: CallbackQuery, db: Database):
    """Фильм из результатов поиска"""
    code = callback.data.replace("movie_", "")
    
    # Используем кэшированный метод получения фильма
    movie = await db.get_movie_by_code_cached(code)

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
    
    if genres:
        response = get_text("movie_found_with_genres", lang,
                           title=movie['title'], year_line=year_line,
                           duration_line=duration_line, rating_line=rating_line,
                           genres=", ".join(genres), code=movie['code'],
                           quality=movie['quality'], views=movie['views'], link=movie['link'])
    else:
        response = get_text("movie_found", lang,
                           title=movie['title'], year_line=year_line,
                           duration_line=duration_line, rating_line=rating_line,
                           code=movie['code'], quality=movie['quality'],
                           views=movie['views'], link=movie['link'])
    
    # Отправляем с постером если есть
    if movie.get('poster_url'):
        poster_path = movie['poster_url']
        if not poster_path.startswith('/'):
            poster_path = os.path.abspath(poster_path)

        if os.path.exists(poster_path):
            from aiogram.types import FSInputFile
            try:
                await callback.message.answer_photo(
                    photo=FSInputFile(poster_path),
                    caption=response,
                    reply_markup=get_movie_inline_keyboard(movie['code'], lang)
                )
                await callback.answer()
            except Exception as e:
                logger.warning(f"Ошибка отправки постера: {e}")
                await callback.message.answer(
                    response,
                    reply_markup=get_movie_inline_keyboard(movie['code'], lang),
                    disable_web_page_preview=True
                )
                await callback.answer()
    else:
        await callback.message.answer(
            response,
            reply_markup=get_movie_inline_keyboard(movie['code'], lang),
            disable_web_page_preview=True
        )
        await callback.answer()

    # Отправляем трейлер если есть (отдельным сообщением)
    if movie.get('trailer_url'):
        trailer_path = movie['trailer_url']
        if not trailer_path.startswith('/'):
            trailer_path = os.path.abspath(trailer_path)

        if os.path.exists(trailer_path):
            try:
                await callback.message.answer_video(
                    video=FSInputFile(trailer_path),
                    caption=f"🎥 **Трейлер к фильму \"{movie['title']}\"**",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Ошибка отправки трейлера: {e}")


# ==================== ЖАНРЫ ====================

@router.callback_query(F.data.startswith("genre_id_"))
async def select_genre(callback: CallbackQuery, db: Database):
    """Выбор жанра по ID"""
    genre_id = callback.data.replace("genre_id_", "")
    
    # Получаем название жанра по ID
    genres = db.get_all_genres()
    genre_name = None
    for genre in genres:
        if str(genre['id']) == genre_id:
            genre_name = genre['name']
            break
    
    if not genre_name:
        await callback.answer("❌ Жанр не найден", show_alert=True)
        return
    
    await show_genre_movies(callback, db, genre_name, page=1)


async def show_genre_movies(callback: CallbackQuery, db: Database, genre_name: str, page: int = 1):
    """Показывает фильмы жанра с пагинацией"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    from utils import resolve_genre_alias
    genre_resolved = resolve_genre_alias(genre_name)

    # Получаем общее количество фильмов через fuzzy поиск
    movies = db.search_movies_by_genre_fuzzy(genre_resolved, limit=1000)
    total_count = len(movies)
    
    PAGE_SIZE = 10
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))

    offset = (page - 1) * PAGE_SIZE
    page_movies = movies[offset:offset + PAGE_SIZE]

    if not page_movies:
        await callback.answer("❌ Фильмы этого жанра не найдены", show_alert=True)
        return

    text = f"🎭 **Жанр: {genre_resolved}**\n\n"
    text += f"Найдено фильмов: {total_count} (страница {page}/{total_pages})\n\n"
    for i, movie in enumerate(page_movies, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}`\n"

    # Кнопки пагинации
    keyboard_buttons = []
    
    # Кнопки фильмов
    for movie in page_movies:
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"🎬 {movie['title']}",
            callback_data=f"movie_{movie['code']}"
        )])
    
    # Кнопки навигации - используем ID жанра
    # Сначала получаем ID жанра
    genres = db.get_all_genres()
    genre_id = None
    for genre in genres:
        if genre['name'] == genre_name:
            genre_id = genre['id']
            break
    
    if genre_id:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"genre_page_{genre_id}_{page-1}"
            ))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"genre_page_{genre_id}_{page+1}"
            ))
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([InlineKeyboardButton(
        text="🔙 В меню",
        callback_data="back_to_main"
    )])

    try:
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("genre_page_"))
async def genre_page_callback(callback: CallbackQuery, db: Database):
    """Пагинация жанров"""
    # Формат: genre_page_ID_2
    data = callback.data.replace("genre_page_", "", 1)
    parts = data.rsplit("_", 1)
    
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer()
        return
    
    genre_id = parts[0]
    page = int(parts[1])
    
    # Получаем название жанра по ID
    genres = db.get_all_genres()
    genre_name = None
    for genre in genres:
        if str(genre['id']) == genre_id:
            genre_name = genre['name']
            break
    
    if not genre_name:
        await callback.answer("❌ Жанр не найден", show_alert=True)
        return
    
    await show_genre_movies(callback, db, genre_name, page=page)


# ==================== АКТЁРЫ ====================

@router.callback_query(F.data.startswith("actor_"))
async def select_actor(callback: CallbackQuery, db: Database):
    """Выбор актёра"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    actor_hash = callback.data.replace("actor_", "", 1)
    
    import hashlib
    all_actors = db.get_all_actors(limit=10000, offset=0)
    actor_name = None
    for actor in all_actors:
        if hashlib.md5(actor['name'].encode('utf-8')).hexdigest()[:16] == actor_hash:
            actor_name = actor['name']
            break
    
    if not actor_name:
        await callback.answer("❌ Актёр не найден", show_alert=True)
        return
    
    from utils import resolve_actor_alias
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


@router.callback_query(F.data.startswith("actors_page_"))
async def actors_page_callback(callback: CallbackQuery, db: Database):
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
    
    limit = 10
    offset = (page - 1) * limit
    actors = db.get_all_actors(limit=limit, offset=offset)
    total_count = db.get_actors_count()
    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
    
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


# ==================== РЕЖИССЁРЫ ====================

@router.callback_query(F.data.startswith("director_"))
async def select_director(callback: CallbackQuery, db: Database):
    """Выбор режиссёра"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    director_hash = callback.data.replace("director_", "", 1)
    
    import hashlib
    all_directors = db.get_all_directors(limit=10000, offset=0)
    director_name = None
    for director in all_directors:
        if hashlib.md5(director['name'].encode('utf-8')).hexdigest()[:16] == director_hash:
            director_name = director['name']
            break
    
    if not director_name:
        await callback.answer("❌ Режиссёр не найден", show_alert=True)
        return
    
    from utils import resolve_director_alias
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


@router.callback_query(F.data.startswith("directors_page_"))
async def directors_page_callback(callback: CallbackQuery, db: Database):
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
    
    limit = 10
    offset = (page - 1) * limit
    directors = db.get_all_directors(limit=limit, offset=offset)
    total_count = db.get_directors_count()
    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
    
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


# ==================== ПОДПИСКА ====================

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, db: Database):
    """Проверка подписки"""
    from config import Config
    
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in Config.ADMIN_IDS

    wait_msg = await callback.message.answer(get_text("subscription_check_timer", lang, seconds=3))
    import asyncio
    await asyncio.sleep(2)

    result = await check_sub(user_id, db=db, bot=callback.message.bot)

    await wait_msg.delete()

    if result.get('is_subscribed', False):
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            get_text("subscription_check_passed", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    else:
        # Получаем полную информацию о каналах
        all_channels = db.get_channels() or Config.CHANNELS
        failed_channels_data = [
            ch for ch in all_channels
            if ch['name'] in result.get('failed_channels', [])
        ]
        failed = "\n".join([f"• {ch['name']}" for ch in failed_channels_data])
        await callback.message.answer(
            get_text("subscription_check_failed", lang, failed_channels=failed),
            reply_markup=get_channels_keyboard(failed_channels_data, lang),
            disable_web_page_preview=True
        )

    await callback.answer()


# ==================== НАЗАД / МЕНЮ ====================

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, db: Database):
    """Назад в главное меню"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    try:
        await callback.message.edit_text(
            get_text("command_start", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            get_text("command_start", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, db: Database):
    """Назад в меню"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    try:
        await callback.message.edit_text(
            "🎬 Главное меню",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            "🎬 Главное меню",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    
    await callback.answer()


@router.callback_query(F.data == "cancel_to_main")
async def cancel_to_main(callback: CallbackQuery, db: Database):
    """Отмена"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
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
