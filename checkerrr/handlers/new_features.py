"""
Новые фичи: случайный фильм, тренды, достижения, уведомления
"""
import logging
import random
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import Database
from config import Config
from texts import get_text
from keyboards import get_main_keyboard, get_favorites_keyboard
from services import TrendsService, AchievementService, NotificationService
from constants import ACHIEVEMENTS
from utils import format_year_line, format_rating_line

logger = logging.getLogger(__name__)

router = Router()


# ==================== СЛУЧАЙНЫЙ ФИЛЬМ ====================

@router.message(F.text.in_(["🎲 Случайный фильм", "🎲 Random Movie"]))
async def random_movie(message: Message, db: Database):
    """Кнопка 'Случайный фильм'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in Config.ADMIN_IDS
    
    # Получаем случайный фильм из топ-100 по просмотрам
    top_movies = db.get_top_movies(limit=100)
    
    if not top_movies:
        await message.answer(
            "⚠️ В каталоге пока нет фильмов",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        return
    
    movie = random.choice(top_movies)
    await send_movie_details(message, movie, lang, db)


@router.callback_query(F.data == "random_movie")
async def random_movie_callback(callback: CallbackQuery, db: Database):
    """Callback для случайного фильма"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    top_movies = db.get_top_movies(limit=100)
    
    if not top_movies:
        await callback.answer("⚠️ В каталоге пока нет фильмов", show_alert=True)
        return
    
    movie = random.choice(top_movies)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await send_movie_details(callback.message, movie, lang, db)
    await callback.answer()


async def send_movie_details(message: Message, movie: dict, lang: str, db: Database):
    """Отправить детали фильма"""
    user_id = message.from_user.id
    
    # Инкремент просмотров
    db.increment_views(movie['code'])
    db.log_view(movie.get('id'), user_id)
    
    genres = db.get_movie_genres(movie.get('id', 0))
    year_line = format_year_line(movie.get('year'))
    rating_line = format_rating_line(movie.get('rating'))
    
    if genres:
        genres_text = ", ".join(genres)
        response = (
            f"🎬 **{movie['title']}**{year_line}\n\n"
            f"⭐ Рейтинг: {rating_line}\n"
            f"🎭 Жанры: {genres_text}\n"
            f"🔍 Код: `{movie['code']}`\n"
            f"📊 Качество: {movie['quality']}\n"
            f"👁 Просмотров: {movie['views']}\n\n"
            f"🔗 Ссылка: {movie['link']}"
        )
    else:
        response = (
            f"🎬 **{movie['title']}**{year_line}\n\n"
            f"⭐ Рейтинг: {rating_line}\n"
            f"🔍 Код: `{movie['code']}`\n"
            f"📊 Качество: {movie['quality']}\n"
            f"👁 Просмотров: {movie['views']}\n\n"
            f"🔗 Ссылка: {movie['link']}"
        )
    
    # Клавиатура с реакциями и действиями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 Like", callback_data=f"like_{movie['code']}"),
                InlineKeyboardButton(text="👎 Dislike", callback_data=f"dislike_{movie['code']}")
            ],
            [
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{movie['code']}"),
                InlineKeyboardButton(text="🔍 Похожие", callback_data=f"similar_{movie['code']}")
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )
    
    # Отправляем с постером если есть
    if movie.get('poster_url'):
        from aiogram.types import FSInputFile
        import os
        
        poster_path = movie['poster_url']
        if not poster_path.startswith('/'):
            poster_path = os.path.abspath(poster_path)
        
        if os.path.exists(poster_path):
            try:
                await message.answer_photo(
                    photo=FSInputFile(poster_path),
                    caption=response,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                return
            except Exception as e:
                logger.warning(f"Ошибка отправки постера: {e}")
    
    await message.answer(
        response,
        reply_markup=keyboard,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


# ==================== ТРЕНДЫ ====================

@router.message(F.text.in_(["📈 Тренды", "📈 Trends"]))
async def trends(message: Message, db: Database):
    """Кнопка 'Тренды'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in Config.ADMIN_IDS
    
    trends_service = TrendsService(db)
    
    # Получаем тренды за неделю
    trending = trends_service.get_trending_movies(period="week", limit=10)
    now_watching = trends_service.get_now_watching(minutes=5)
    
    text = f"📈 **Тренды**\n\n"
    text += f"👥 Сейчас смотрят: **{now_watching}** чел.\n\n"
    text += f"🔥 **Популярное за неделю**:\n\n"
    
    for i, movie in enumerate(trending, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['movie_title']}{year_line} — `{movie['movie_code']}` 👁 {movie['views_count']}\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 За день", callback_data="trends_day"),
                InlineKeyboardButton(text="📊 За месяц", callback_data="trends_month")
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )
    
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.in_(["trends_day", "trends_week", "trends_month"]))
async def trends_period(callback: CallbackQuery, db: Database):
    """Смена периода трендов"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    period_map = {
        "trends_day": ("day", "За день"),
        "trends_week": ("week", "За неделю"),
        "trends_month": ("month", "За месяц")
    }
    
    period, period_name = period_map.get(callback.data, ("week", "За неделю"))
    
    trends_service = TrendsService(db)
    trending = trends_service.get_trending_movies(period=period, limit=10)
    now_watching = trends_service.get_now_watching(minutes=5)
    
    text = f"📈 **Тренды**\n\n"
    text += f"👥 Сейчас смотрят: **{now_watching}** чел.\n\n"
    text += f"🔥 **{period_name}**:\n\n"
    
    for i, movie in enumerate(trending, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['movie_title']}{year_line} — `{movie['movie_code']}` 👁 {movie['views_count']}\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 За день", callback_data="trends_day"),
                InlineKeyboardButton(text="📊 За месяц", callback_data="trends_month")
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    await callback.answer()


# ==================== МОЙ ПРОФИЛЬ ====================

@router.message(F.text.in_(["👤 Мой профиль", "👤 My Profile"]))
async def my_profile(message: Message, db: Database):
    """Кнопка 'Мой профиль'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in Config.ADMIN_IDS

    # Получаем статистику
    stats = db.get_user_stats(user_id)
    favorites = db.get_user_favorites(user_id)
    last_search = stats.get('last_search_at', 'Никогда')
    if last_search and isinstance(last_search, str):
        last_search = last_search[:19]
    
    # Получаем достижения
    from services import AchievementService
    achievement_service = AchievementService(db)
    user_achievements = achievement_service.get_user_achievements(user_id)
    unlocked_count = sum(1 for a in user_achievements if a.get('is_unlocked'))
    total_count = len(ACHIEVEMENTS)
    
    # Получаем настройки уведомлений
    notifications_enabled = db.get_user_notifications_enabled(user_id)
    
    text = f"👤 **Профиль пользователя**\n\n"
    text += f"🆔 ID: `{user_id}`\n"
    text += f"🔍 Поисков: {stats.get('total_searches', 0)}\n"
    text += f"⭐ В избранном: {len(favorites)}\n"
    text += f"🕐 Последний поиск: {last_search if last_search else 'Никогда'}\n"
    text += f"🏆 Достижения: {unlocked_count}/{total_count}\n"
    text += f"🔔 Уведомления: {'✅ Включены' if notifications_enabled else '❌ Выключены'}\n\n"
    
    # Топ достижений
    if user_achievements:
        text += f"**Ваши достижения:**\n\n"
        for ach in user_achievements[:5]:
            icon = ach['icon']
            name = ach['name_ru'] if lang == "ru" else ach['name_en']
            status = "✅" if ach['is_unlocked'] else "🔒"
            text += f"{status} {icon} {name}\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏆 Все достижения", callback_data="my_achievements"),
                InlineKeyboardButton(text="⭐ Избранное", callback_data="my_favorites")
            ],
            [
                InlineKeyboardButton(text="🔔 Настройки уведомлений", callback_data="my_notifications"),
                InlineKeyboardButton(text="📜 История поиска", callback_data="my_history")
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )
    
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "my_achievements")
async def my_achievements(callback: CallbackQuery, db: Database):
    """Мои достижения"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    from services import AchievementService
    achievement_service = AchievementService(db)
    user_achievements = achievement_service.get_user_achievements(user_id)
    
    unlocked_count = sum(1 for a in user_achievements if a.get('is_unlocked'))
    total_count = len(ACHIEVEMENTS)
    
    text = f"🏆 **Мои достижения**\n\n"
    text += f"📊 Прогресс: **{unlocked_count}/{total_count}**\n\n"
    
    # Разблокированные
    for ach in user_achievements:
        if ach['is_unlocked']:
            icon = ach['icon']
            name = ach['name_ru'] if lang == "ru" else ach['name_en']
            desc = ach['description_ru'] if lang == "ru" else ach['description_en']
            text += f"✅ {icon} **{name}**\n"
            text += f"   {desc}\n"
            if ach.get('unlocked_at'):
                text += f"   📅 {str(ach['unlocked_at'])[:16]}\n\n"
    
    # Заблокированные
    text += f"\n🔒 **Заблокировано:**\n\n"
    for ach in user_achievements:
        if not ach['is_unlocked']:
            icon = ach['icon']
            name = ach['name_ru'] if lang == "ru" else ach['name_en']
            desc = ach['description_ru'] if lang == "ru" else ach['description_en']
            text += f"🔒 {icon} **{name}**\n"
            text += f"   {desc}\n\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В профиль", callback_data="my_profile_btn")]
        ]
    )
    
    await callback.message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "my_favorites")
async def my_favorites_callback(callback: CallbackQuery, db: Database):
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
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В профиль", callback_data="my_profile_btn")]
        ]
    )
    
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_favorites_keyboard(favorites, lang)
    )
    await callback.answer()


@router.callback_query(F.data == "my_notifications")
async def my_notifications(callback: CallbackQuery, db: Database):
    """Мои уведомления"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    enabled = db.get_user_notifications_enabled(user_id)
    
    text = f"🔔 **Настройки уведомлений**\n\n"
    if enabled:
        text += "✅ Уведомления **включены**\n\n"
        text += "Вы будете получать уведомления о:\n"
        text += "• 🎬 Новых фильмах в каталоге\n"
        text += "• 🔔 Напоминаниях о просмотренных фильмах\n"
        text += "• 🏆 Полученных достижениях\n\n"
    else:
        text += "❌ Уведомления **выключены**\n\n"
        text += "Включите чтобы получать:\n"
        text += "• 🎬 Уведомления о новых фильмах\n"
        text += "• 🔔 Напоминания о просмотренных фильмах\n"
        text += "• 🏆 Уведомления о достижениях\n\n"
    
    button_text = "🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data="toggle_notifications"
                )
            ],
            [InlineKeyboardButton(text="🔙 В профиль", callback_data="my_profile_btn")]
        ]
    )
    
    await callback.message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "my_history")
async def my_history(callback: CallbackQuery, db: Database):
    """Моя история поиска"""
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
        text += f"{icon} {item['query']} ({item['query_type']})\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В профиль", callback_data="my_profile_btn")]
        ]
    )
    
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "my_profile_btn")
async def my_profile_btn(callback: CallbackQuery, db: Database):
    """Вернуться в профиль"""
    await my_profile(callback.message, db)
    await callback.answer()


# ==================== ДОСТИЖЕНИЯ (старая кнопка) ====================

@router.message(F.text.in_(["🏆 Достижения", "🏆 Achievements"]))
async def achievements(message: Message, db: Database):
    """Кнопка 'Достижения'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in Config.ADMIN_IDS
    
    achievement_service = AchievementService(db)
    user_achievements = achievement_service.get_user_achievements(user_id)
    
    # Считаем прогресс
    unlocked_count = sum(1 for a in user_achievements if a.get('is_unlocked'))
    total_count = len(ACHIEVEMENTS)
    
    text = f"🏆 **Достижения**\n\n"
    text += f"📊 Прогресс: **{unlocked_count}/{total_count}**\n\n"
    
    # Группируем
    locked = []
    for ach in user_achievements:
        icon = ach['icon']
        name = ach['name_ru'] if lang == "ru" else ach['name_en']
        
        if ach['is_unlocked']:
            text += f"✅ {icon} **{name}**\n"
            text += f"   {ach['description_ru'] if lang == 'ru' else ach['description_en']}\n"
            if ach.get('unlocked_at'):
                text += f"   📅 {str(ach['unlocked_at'])[:16]}\n\n"
        else:
            locked.append((icon, name, ach['description_ru'] if lang == 'ru' else ach['description_en']))
    
    if locked:
        text += f"🔒 **Заблокировано ({len(locked)})**:\n\n"
        for icon, name, desc in locked[:5]:
            text += f"🔒 {icon} **{name}**\n"
            text += f"   {desc}\n\n"
    
    if len(locked) > 5:
        text += f"... и ещё {len(locked) - 5}\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Все достижения", callback_data="achievements_all")
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )
    
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "achievements_all")
async def achievements_all(callback: CallbackQuery, db: Database):
    """Все достижения"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    achievement_service = AchievementService(db)
    text = achievement_service.get_all_achievements_info(lang)
    
    try:
        await callback.message.edit_text(
            text,
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="Markdown"
        )
    
    await callback.answer()


# ==================== УВЕДОМЛЕНИЯ ====================

@router.message(F.text.in_(["🔔 Уведомления", "🔔 Notifications"]))
async def notifications(message: Message, db: Database):
    """Кнопка 'Уведомления'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in Config.ADMIN_IDS
    
    enabled = db.get_user_notifications_enabled(user_id)
    
    text = f"🔔 **Уведомления**\n\n"
    
    if enabled:
        text += "✅ Уведомления **включены**\n\n"
        text += "Вы будете получать уведомления о:\n"
        text += "• 🎬 Новых фильмах в каталоге\n"
        text += "• 🔔 Напоминаниях о просмотренных фильмах\n"
        text += "• 🏆 Полученных достижениях\n\n"
    else:
        text += "❌ Уведомления **выключены**\n\n"
        text += "Включите чтобы получать:\n"
        text += "• 🎬 Уведомления о новых фильмах\n"
        text += "• 🔔 Напоминания о просмотренных фильмах\n"
        text += "• 🏆 Уведомления о достижениях\n\n"
    
    button_text_ru = "🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления"
    button_text_en = "🔕 Disable Notifications" if enabled else "🔔 Enable Notifications"
    button_text = button_text_ru if lang == "ru" else button_text_en
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )
    
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: CallbackQuery, db: Database):
    """Переключить уведомления"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    current = db.get_user_notifications_enabled(user_id)
    db.set_user_notifications(user_id, not current)

    status_ru = "включены" if not current else "выключены"
    status_en = "enabled" if not current else "disabled"

    status = status_ru if lang == "ru" else status_en

    await callback.answer(
        f"✅ Уведомления {status}",
        show_alert=True
    )

    # Обновляем сообщение с новой кнопкой
    enabled = not current  # Теперь уведомления в новом состоянии
    
    text = f"🔔 **Уведомления**\n\n"
    if enabled:
        text += "✅ Уведомления **включены**\n\n"
        text += "Вы будете получать уведомления о:\n"
        text += "• 🎬 Новых фильмах в каталоге\n"
        text += "• 🔔 Напоминаниях о просмотренных фильмах\n"
        text += "• 🏆 Полученных достижениях\n\n"
    else:
        text += "❌ Уведомления **выключены**\n\n"
        text += "Включите чтобы получать:\n"
        text += "• 🎬 Уведомления о новых фильмах\n"
        text += "• 🔔 Напоминания о просмотренных фильмах\n"
        text += "• 🏆 Уведомления о достижениях\n\n"

    button_text_ru = "🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления"
    button_text_en = "🔕 Disable Notifications" if enabled else "🔔 Enable Notifications"
    button_text = button_text_ru if lang == "ru" else button_text_en

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ]
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        # Если нельзя редактировать - отправляем новое и удаляем старое
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
