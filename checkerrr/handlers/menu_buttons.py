"""
Обработчики старых кнопок меню
"""
import logging
import base64
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import Config as AppConfig
from database import Database
from keyboards import (
    get_main_keyboard,
    get_genres_keyboard,
    get_actors_keyboard,
    get_directors_keyboard,
    get_favorites_keyboard,
    get_search_results_keyboard,
    get_admin_keyboard,
)
from texts import get_text
from utils import resolve_genre_alias, resolve_actor_alias, resolve_director_alias

logger = logging.getLogger(__name__)

router = Router()


# ==================== ℹ️ ПОМОЩЬ ====================

@router.message(F.text.in_(["ℹ️ Помощь", "ℹ️ Instructions"]))
async def help_button(message: Message, db: Database):
    """Кнопка 'Помощь'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    await message.answer(
        get_text("help", lang),
        reply_markup=get_main_keyboard(lang, is_admin=is_admin),
        parse_mode="Markdown"
    )


# ==================== 🌐 ЯЗЫК ====================

@router.message(F.text.in_(["🌐 Язык", "🌐 Language"]))
async def language_button(message: Message, db: Database):
    """Кнопка 'Язык'"""
    user_id = message.from_user.id
    current_lang = db.get_user_language(user_id)
    new_lang = "en" if current_lang == "ru" else "ru"
    
    is_admin = user_id in AppConfig.ADMIN_IDS
    db.set_user_language(user_id, new_lang)
    
    await message.answer(
        get_text("language_changed", new_lang),
        reply_markup=get_main_keyboard(new_lang, is_admin=is_admin)
    )


# ==================== 🛠 ПОДДЕРЖКА ====================

@router.message(F.text.in_(["🛠 Поддержка", "🛠 Support"]))
async def support_button(message: Message, db: Database):
    """Кнопка 'Поддержка'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    await message.answer(
        get_text("command_support", lang, support_link=AppConfig.SUPPORT_LINK),
        reply_markup=get_main_keyboard(lang, is_admin=is_admin),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


# ==================== 👑 АДМИН-ПАНЕЛЬ ====================

@router.message(F.text.in_(["👑 Админ-панель", "👑 Admin Panel"]))
async def admin_panel_button(message: Message, db: Database):
    """Кнопка 'Админ-панель'"""
    user_id = message.from_user.id
    
    if user_id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(user_id)
    
    from keyboards import get_admin_keyboard
    await message.answer(
        get_text("admin_panel_title", lang),
        reply_markup=get_admin_keyboard(lang)
    )


# ==================== 🎭 ПОИСК ПО ЖАНРУ ====================

@router.message(F.text == "🎭 Поиск по жанру")
async def search_by_genre_button(message: Message, db: Database):
    """Кнопка 'Поиск по жанру' - страница 1"""
    await show_genres_page(message, db, page=1)


async def show_genres_page(message: Message, db: Database, page: int = 1):
    """Показывает страницу жанров с пагинацией"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS

    genres = db.get_all_genres()
    if not genres:
        await message.answer(
            get_text("genres_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        return

    # Пагинация жанров
    PAGE_SIZE = 10
    total_count = len(genres)
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))

    offset = (page - 1) * PAGE_SIZE
    page_genres = genres[offset:offset + PAGE_SIZE]

    text = get_text("genres_select", lang)
    text += f"Страница {page}/{total_pages}\n\n"
    for genre in page_genres:
        text += f"• {genre['name']}\n"

    # Клавиатура с жанрами и пагинацией - используем ID жанра
    keyboard_buttons = []
    for genre in page_genres:
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"🎭 {genre['name']}",
            callback_data=f"genre_id_{genre['id']}"
        )])

    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"genres_page_{page-1}"
        ))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=f"genres_page_{page+1}"
        ))
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append([InlineKeyboardButton(
        text="🔙 В меню",
        callback_data="back_to_main"
    )])

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )


@router.callback_query(F.data.startswith("genres_page_"))
async def genres_page_callback(callback: CallbackQuery, db: Database):
    """Пагинация списка жанров"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        page = int(callback.data.replace("genres_page_", ""))
    except ValueError:
        await callback.answer()
        return

    genres = db.get_all_genres()
    if not genres:
        await callback.answer("❌ Жанры не найдены", show_alert=True)
        return

    # Пагинация жанров
    PAGE_SIZE = 10
    total_count = len(genres)
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))

    offset = (page - 1) * PAGE_SIZE
    page_genres = genres[offset:offset + PAGE_SIZE]

    text = get_text("genres_select", lang)
    text += f"Страница {page}/{total_pages}\n\n"
    for genre in page_genres:
        text += f"• {genre['name']}\n"

    # Клавиатура с жанрами и пагинацией
    keyboard_buttons = []
    for genre in page_genres:
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"🎭 {genre['name']}",
            callback_data=f"genre_id_{genre['id']}"
        )])

    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"genres_page_{page-1}"
        ))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=f"genres_page_{page+1}"
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


# ==================== 🎬 ПОИСК ПО АКТЁРУ ====================

@router.message(F.text == "🎬 Поиск по актёру")
async def search_by_actor_button(message: Message, db: Database):
    """Кнопка 'Поиск по актёру' - страница 1"""
    await show_actors_page(message, db, page=1)


async def show_actors_page(message: Message, db: Database, page: int = 1):
    """Показывает страницу актёров"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    limit = 10
    offset = (page - 1) * limit
    actors = db.get_all_actors(limit=limit, offset=offset)
    total_count = db.get_actors_count()
    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
    
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


# ==================== 🎥 ПОИСК ПО РЕЖИССЁРУ ====================

@router.message(F.text == "🎥 Поиск по режиссёру")
async def search_by_director_button(message: Message, db: Database):
    """Кнопка 'Поиск по режиссёру' - страница 1"""
    await show_directors_page(message, db, page=1)


async def show_directors_page(message: Message, db: Database, page: int = 1):
    """Показывает страницу режиссёров"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    limit = 10
    offset = (page - 1) * limit
    directors = db.get_all_directors(limit=limit, offset=offset)
    total_count = db.get_directors_count()
    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
    
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


# ==================== ⭐ ИЗБРАННОЕ ====================

@router.message(F.text == "⭐ Избранное")
async def favorites_button(message: Message, db: Database):
    """Кнопка 'Избранное'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    favorites = db.get_user_favorites(user_id)
    
    if not favorites:
        await message.answer(
            get_text("favorites_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=user_id in AppConfig.ADMIN_IDS)
        )
        return
    
    text = get_text("favorites_list", lang, count=len(favorites))
    for movie in favorites[:10]:
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"🎬 {movie['title']}{year_line} — `{movie['code']}`\n"
    
    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_favorites_keyboard(favorites, lang)
    )


# ==================== 🔥 ТОП ФИЛЬМОВ ====================

@router.message(F.text == "🔥 Топ фильмов")
async def top_movies_button(message: Message, db: Database):
    """Кнопка 'Топ фильмов'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    top = db.get_top_movies(limit=10)
    
    if not top:
        await message.answer(
            get_text("top_movies_empty", lang),
            reply_markup=get_main_keyboard(lang, is_admin=user_id in AppConfig.ADMIN_IDS)
        )
        return
    
    text = get_text("admin_top_movies", lang)
    for i, movie in enumerate(top, 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        text += f"{i}. {movie['title']}{year_line} — `{movie['code']}` 👁 {movie['views']}\n"
    
    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_search_results_keyboard(top, lang)
    )


# ==================== 🎭 ЖАНРЫ ====================

@router.message(F.text == "🎭 Жанры")
async def genres_button(message: Message, db: Database):
    """Кнопка 'Жанры'"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    await message.answer(
        get_text("genres_unavailable", lang),
        reply_markup=get_main_keyboard(lang, is_admin=user_id in AppConfig.ADMIN_IDS)
    )


# ==================== 📊 МОЯ СТАТИСТИКА ====================

@router.message(F.text == "📊 Моя статистика")
async def my_stats_button(message: Message, db: Database):
    """Кнопка 'Моя статистика'"""
    user_id = message.from_user.id
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

    await message.answer(text)


# ==================== 📜 ИСТОРИЯ ====================

@router.message(F.text == "📜 История")
async def history_button(message: Message, db: Database):
    """Кнопка 'История' - показывает меню выбора"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    from keyboards import get_history_menu_keyboard
    
    await message.answer(
        get_text("history_menu", lang, default="📂 Выберите тип истории:"),
        reply_markup=get_history_menu_keyboard(lang)
    )
