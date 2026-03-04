"""
Обработчик поиска фильмов и админ-панели
"""
import logging
import re
import os
from datetime import datetime, timedelta
from aiogram import F, Router, types
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from config import Config as AppConfig
from database import Database
from keyboards import (
    get_main_keyboard,
    get_admin_keyboard,
    get_admin_movies_keyboard,
    get_admin_import_export_keyboard,
    get_stats_keyboard,
    get_user_stats_keyboard,
    get_movie_edit_keyboard,
    get_delete_confirm_keyboard,
    get_cancel_keyboard,
)
from texts import get_text

logger = logging.getLogger(__name__)

router = Router()


# ==================== АДМИН-ПАНЕЛЬ ====================

class AdminStates:
    waiting_for_code = "AdminStates:waiting_for_code"
    waiting_for_title = "AdminStates:waiting_for_title"
    waiting_for_link = "AdminStates:waiting_for_link"
    waiting_for_year = "AdminStates:waiting_for_year"
    waiting_for_quality = "AdminStates:waiting_for_quality"
    waiting_for_rating = "AdminStates:waiting_for_rating"
    waiting_for_genres = "AdminStates:waiting_for_genres"
    waiting_for_poster = "AdminStates:waiting_for_poster"
    waiting_for_trailer = "AdminStates:waiting_for_trailer"
    waiting_for_actors = "AdminStates:waiting_for_actors"
    waiting_for_directors = "AdminStates:waiting_for_directors"
    waiting_for_edit = "AdminStates:waiting_for_edit"
    waiting_for_edit_file = "AdminStates:waiting_for_edit_file"
    waiting_for_csv = "AdminStates:waiting_for_csv"


# ==================== АДМИН-ПАНЕЛЬ ====================

@router.message(F.text.in_(["👑 Админ-панель", "👑 Admin Panel"]))
@router.message(Command("admin"))
async def admin_panel(message: Message, db: Database):
    """Админ-панель"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        get_text("admin_panel_title", lang),
        reply_markup=get_admin_keyboard(lang)
    )


@router.callback_query(F.data == "admin_add_movie")
async def admin_add_movie(callback: CallbackQuery, db: Database, state: FSMContext):
    """Добавить фильм - шаг 1"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        "Отправьте код фильма (только цифры, максимум 10 символов):\n\nПримеры: `1`, `001`, `MATRIX`",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state(AdminStates.waiting_for_code)
    await callback.answer()


@router.callback_query(F.data == "admin_list_movies")
async def admin_list_movies(callback: CallbackQuery, db: Database):
    """Список фильмов"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await show_movies_page(callback.message, db, lang, page=1)
    await callback.answer()


@router.callback_query(F.data == "admin_delete_movie")
async def admin_delete_movie_start(callback: CallbackQuery, db: Database):
    """Удаление фильма - показать список (страница 1)"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await show_delete_movies_page(callback.message, db, lang, page=1)
    await callback.answer()


async def show_delete_movies_page(message, db: Database, lang: str, page: int = 1):
    """Показать страницу фильмов для удаления"""
    PAGE_SIZE = 20
    total_count = db.get_movies_count()
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    
    offset = (page - 1) * PAGE_SIZE
    movies = db.get_all_movies(limit=PAGE_SIZE, offset=offset)
    
    if not movies:
        await message.edit_text(
            get_text("admin_movies_empty", lang),
            reply_markup=get_admin_keyboard(lang)
        )
        return
    
    text = get_text("admin_delete_title", lang)
    text += f"Страница {page}/{total_pages}\n"
    text += "Выберите фильм для удаления:\n\n"
    
    buttons = []
    for movie in movies:
        year_line = f" ({movie['year']})" if movie['year'] else ""
        button_text = f"🎬 {movie['title']}{year_line} — {movie['code']}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"delete_select_{movie['code']}"
        )])
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"delete_page_{page-1}"
        ))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=f"delete_page_{page+1}"
        ))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(
        text=get_text("admin_back_button", lang),
        callback_data="admin_back_to_panel"
    )])
    
    await message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("delete_page_"))
async def delete_page_callback(callback: CallbackQuery, db: Database):
    """Пагинация удаления фильмов"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    try:
        page = int(callback.data.replace("delete_page_", ""))
        await show_delete_movies_page(callback.message, db, lang, page=page)
        await callback.answer()
    except ValueError:
        await callback.answer("❌ Некорректная страница", show_alert=True)


@router.callback_query(F.data == "admin_edit_movie")
async def admin_edit_movie_start(callback: CallbackQuery, db: Database):
    """Редактирование фильма - показать список (страница 1)"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await show_edit_movies_page(callback.message, db, lang, page=1)
    await callback.answer()


async def show_edit_movies_page(message, db: Database, lang: str, page: int = 1):
    """Показать страницу фильмов для редактирования"""
    PAGE_SIZE = 20
    total_count = db.get_movies_count()
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    
    offset = (page - 1) * PAGE_SIZE
    movies = db.get_all_movies(limit=PAGE_SIZE, offset=offset)
    
    if not movies:
        await message.edit_text(
            get_text("admin_movies_empty", lang),
            reply_markup=get_admin_keyboard(lang)
        )
        return
    
    text = get_text("admin_edit_title", lang)
    text += f"Страница {page}/{total_pages}\n"
    text += "Выберите фильм для редактирования:\n\n"
    
    buttons = []
    for movie in movies:
        year_line = f" ({movie['year']})" if movie['year'] else ""
        button_text = f"🎬 {movie['title']}{year_line} — {movie['code']}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"edit_select_{movie['code']}"
        )])
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"edit_page_{page-1}"
        ))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=f"edit_page_{page+1}"
        ))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="admin_back_to_panel"
    )])
    
    await message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("edit_page_"))
async def edit_page_callback(callback: CallbackQuery, db: Database):
    """Пагинация редактирования фильмов"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    try:
        page = int(callback.data.replace("edit_page_", ""))
        await show_edit_movies_page(callback.message, db, lang, page=page)
        await callback.answer()
    except ValueError:
        await callback.answer("❌ Некорректная страница", show_alert=True)


@router.callback_query(F.data.startswith("edit_select_"))
async def edit_select(callback: CallbackQuery, db: Database, state: FSMContext):
    """Выбор фильма для редактирования"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    code = callback.data.replace("edit_select_", "").strip()
    movie = db.get_movie_by_code(code)
    
    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
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


# ==================== ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ ====================

@router.callback_query(F.data.startswith("edit_title_"))
async def edit_title_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования названия"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_title_", "").strip()
    await state.update_data(edit_code=code, edit_field="title")
    await callback.message.answer("✏️ Отправьте новое название фильма:")
    await state.set_state("AdminStates:waiting_for_edit")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_link_"))
async def edit_link_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования ссылки"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_link_", "").strip()
    await state.update_data(edit_code=code, edit_field="link")
    await callback.message.answer("🔗 Отправьте новую ссылку:")
    await state.set_state("AdminStates:waiting_for_edit")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_year_"))
async def edit_year_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования года"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_year_", "").strip()
    await state.update_data(edit_code=code, edit_field="year")
    await callback.message.answer("📅 Отправьте новый год (например: 2023):")
    await state.set_state("AdminStates:waiting_for_edit")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_quality_"))
async def edit_quality_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования качества"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_quality_", "").strip()
    await state.update_data(edit_code=code, edit_field="quality")
    await callback.message.answer("📺 Отправьте новое качество (480p, 720p, 1080p, 4K):")
    await state.set_state("AdminStates:waiting_for_edit")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_rating_"))
async def edit_rating_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования рейтинга"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_rating_", "").strip()
    await state.update_data(edit_code=code, edit_field="rating")
    await callback.message.answer("⭐ Отправьте новый рейтинг (0.0-10.0):")
    await state.set_state("AdminStates:waiting_for_edit")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_poster_"))
async def edit_poster_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования постера"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_poster_", "").strip()
    await state.update_data(edit_code=code, edit_field="poster_url")
    await callback.message.answer(
        "🖼 **Загрузка постера**\n\n"
        "Отправьте изображение как файл (не сжатое) или фото.\n\n"
        "Или отправьте 🔕 для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state("AdminStates:waiting_for_edit_file")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_banner_"))
async def edit_banner_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования баннера"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_banner_", "").strip()
    await state.update_data(edit_code=code, edit_field="banner_url")
    await callback.message.answer(
        "🎬 **Загрузка баннера**\n\n"
        "Отправьте изображение как файл (не сжатое) или фото.\n\n"
        "Или отправьте 🔕 для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state("AdminStates:waiting_for_edit_file")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_trailer_"))
async def edit_trailer_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования трейлера"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    code = callback.data.replace("edit_trailer_", "").strip()
    await state.update_data(edit_code=code, edit_field="trailer_url")
    await callback.message.answer(
        "🎥 **Загрузка трейлера**\n\n"
        "Отправьте видео файл (до 20MB).\n\n"
        "Или отправьте 🔕 для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state("AdminStates:waiting_for_edit_file")
    await callback.answer()


@router.callback_query(F.data.startswith("delete_select_"))
async def delete_select(callback: CallbackQuery, db: Database):
    """Выбор фильма для удаления"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
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


@router.callback_query(F.data.startswith("delete_confirmed_"))
async def delete_confirmed(callback: CallbackQuery, db: Database):
    """Подтверждение удаления"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    code = callback.data.replace("delete_confirmed_", "").strip()
    
    movie = db.get_movie_by_code(code)
    if movie:
        result = db.delete_movie(code)
        if result:
            # Возвращаемся к списку фильмов с пагинацией
            await show_delete_movies_page(callback.message, db, lang, page=1)
        else:
            await callback.message.edit_text(
                f"❌ Не удалось удалить фильм «{movie['title']}»",
                reply_markup=get_admin_keyboard(lang)
            )
    else:
        await callback.message.edit_text("❌ Фильм не найден", reply_markup=get_admin_keyboard(lang))
    
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_panel")
async def admin_back_to_panel(callback: CallbackQuery, db: Database):
    """Назад в админ-панель"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        "👑 Админ-панель",
        reply_markup=get_admin_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_import_export")
async def admin_import_export(callback: CallbackQuery, db: Database):
    """Экспорт/Импорт"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        "📤 **Экспорт / Импорт**\n\nВыберите действие:",
        reply_markup=get_admin_import_export_keyboard(lang),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_export")
async def admin_export(callback: CallbackQuery, db: Database):
    """Экспорт фильмов"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        movies = db.get_all_movies(limit=10000)
        import csv
        output = [['code', 'title', 'year', 'description', 'link', 'poster_url', 'quality', 'views', 'rating']]
        for movie in movies:
            output.append([
                movie['code'], movie['title'], movie['year'] or '',
                movie['description'] or '', movie['link'], movie['poster_url'] or '',
                movie['quality'], movie['views'], movie.get('rating', '') or ''
            ])
        
        with open('movies_export.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(output)
        
        with open('movies_export.csv', 'rb') as file:
            await callback.message.answer_document(
                FSInputFile('movies_export.csv'),
                caption=get_text("admin_export_started", lang)
            )
        
        await callback.answer("✅ Экспорт запущен", show_alert=False)
    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        await callback.message.answer(get_text("admin_export_error", lang, error=str(e)))


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db: Database):
    """Статистика"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_general_stats()
    
    text = get_text("admin_stats_general", lang,
                   total_movies=stats.get('total_movies', 0),
                   total_views=stats.get('total_views', 0),
                   active_users=stats.get('active_users', 0),
                   searches_today=stats.get('searches_today', 0),
                   searches_week=stats.get('searches_week', 0))
    
    await callback.message.edit_text(text, reply_markup=get_stats_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "admin_user_stats")
async def admin_user_stats(callback: CallbackQuery, db: Database):
    """Статистика пользователей"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_user_visits_stats(admin_ids=AppConfig.ADMIN_IDS)
    
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
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 За день", callback_data="user_stats_day")],
            [InlineKeyboardButton(text="📊 За неделю", callback_data="user_stats_week")],
            [InlineKeyboardButton(text="📊 За месяц", callback_data="user_stats_month")],
            [InlineKeyboardButton(text="📊 За всё время", callback_data="user_stats_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "user_stats_day")
async def user_stats_day(callback: CallbackQuery, db: Database):
    """Статистика за день"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_user_visits_stats(admin_ids=AppConfig.ADMIN_IDS, period_days=1)
    
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
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 За неделю", callback_data="user_stats_week")],
            [InlineKeyboardButton(text="📊 За месяц", callback_data="user_stats_month")],
            [InlineKeyboardButton(text="📊 За всё время", callback_data="user_stats_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "user_stats_week")
async def user_stats_week(callback: CallbackQuery, db: Database):
    """Статистика за неделю"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_user_visits_stats(admin_ids=AppConfig.ADMIN_IDS, period_days=7)
    
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
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 За день", callback_data="user_stats_day")],
            [InlineKeyboardButton(text="📊 За месяц", callback_data="user_stats_month")],
            [InlineKeyboardButton(text="📊 За всё время", callback_data="user_stats_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "user_stats_month")
async def user_stats_month(callback: CallbackQuery, db: Database):
    """Статистика за месяц"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_user_visits_stats(admin_ids=AppConfig.ADMIN_IDS, period_days=30)
    
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
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 За день", callback_data="user_stats_day")],
            [InlineKeyboardButton(text="📊 За неделю", callback_data="user_stats_week")],
            [InlineKeyboardButton(text="📊 За всё время", callback_data="user_stats_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "user_stats_all")
async def user_stats_all(callback: CallbackQuery, db: Database):
    """Статистика за всё время"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_user_visits_stats(admin_ids=AppConfig.ADMIN_IDS)
    
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
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 За день", callback_data="user_stats_day")],
            [InlineKeyboardButton(text="📊 За неделю", callback_data="user_stats_week")],
            [InlineKeyboardButton(text="📊 За месяц", callback_data="user_stats_month")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


async def show_movies_page(message, db: Database, lang: str, page: int = 1):
    """Показать страницу фильмов"""
    PAGE_SIZE = 10
    total_count = db.get_movies_count()
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    
    offset = (page - 1) * PAGE_SIZE
    movies = db.get_all_movies(limit=PAGE_SIZE, offset=offset)
    
    if not movies:
        await message.edit_text(
            get_text("admin_movies_empty_hint", lang),
            reply_markup=get_admin_keyboard(lang)
        )
        return
    
    text = get_text("admin_movie_list", lang, page=page, total_pages=total_pages, total=total_count)
    start_idx = (page - 1) * PAGE_SIZE
    for i, movie in enumerate(movies, start=start_idx + 1):
        year_line = f" ({movie['year']})" if movie['year'] else ""
        views = f" 👁 {movie['views']}" if movie['views'] else ""
        text += f"{i}. `{movie['code']}` - {movie['title']}{year_line}{views}\n"
    
    try:
        await message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_admin_movies_keyboard(lang, page, total_pages)
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            await message.answer(
                text,
                parse_mode="Markdown",
                reply_markup=get_admin_movies_keyboard(lang, page, total_pages)
            )


@router.callback_query(F.data.startswith("admin_page_"))
async def admin_navigate_page(callback: CallbackQuery, db: Database):
    """Пагинация фильмов"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    try:
        page = int(callback.data.replace("admin_page_", ""))
        await show_movies_page(callback.message, db, lang, page=page)
        await callback.answer()
    except ValueError:
        await callback.answer("❌ Некорректная страница", show_alert=True)


# ==================== FSM: ДОБАВЛЕНИЕ ФИЛЬМА ====================

@router.callback_query(F.data == "admin_add_movie")
async def admin_add_movie_callback(callback: CallbackQuery, state: FSMContext):
    """Начало добавления фильма через callback"""
    if callback.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        "➕ **Добавление фильма**\n\n"
        "Шаг 1/8: Отправьте код фильма (только цифры, максимум 10 символов):\n\n"
        "Примеры: `1`, `001`, `179`\n\n"
        "Или отправьте 🔕 для отмены",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state("AdminStates:waiting_for_code")
    await callback.answer()


@router.message(F.text.in_(["➕ Добавить фильм", "➕ Add Movie"]))
async def admin_add_movie_start(message: Message, state: FSMContext):
    """Начало добавления фильма через текст"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        "➕ **Добавление фильма**\n\n"
        "Шаг 1/8: Отправьте код фильма (только цифры, максимум 10 символов):\n\n"
        "Примеры: `1`, `001`, `179`\n\n"
        "Или отправьте 🔕 для отмены",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(lang, "admin_back_to_panel")
    )
    await state.set_state("AdminStates:waiting_for_code")


@router.message(StateFilter("AdminStates:waiting_for_code"))
async def process_code(message: Message, state: FSMContext, db: Database):
    """Обработка кода фильма - ТОЛЬКО для добавления, не поиск!"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    # Проверка на отмену
    if message.text.strip() == "🔕":
        await state.clear()
        lang = db.get_user_language(message.from_user.id)
        await message.answer(
            "❌ Добавление отменено",
            reply_markup=get_admin_keyboard(lang)
        )
        return
    
    lang = db.get_user_language(message.from_user.id)
    code = message.text.strip()
    code_clean = re.sub(r'[^\w]', '', code.upper())
    
    if not code_clean or len(code_clean) > 10:
        await message.answer("❌ Неверный формат кода. Код должен содержать до 10 символов.\n\nОтправьте код снова или 🔕 для отмены")
        return
    
    # Проверка на дубликат - ищем точное совпадение
    existing_movie = db.get_movie_by_code(code_clean)
    if existing_movie:
        await message.answer(
            f"⚠️ **ПРЕДУПРЕЖДЕНИЕ: Код уже существует!**\n\n"
            f"🎬 Фильм: {existing_movie['title']}\n"
            f"🔍 Код: `{code_clean}`\n\n"
            f"Отправьте **другой код** для продолжения или 🔕 для отмены.",
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(code=code_clean)
    await message.answer(
        f"✅ Код `{code_clean}` принят.\n\n"
        f"Шаг 2/8: Теперь отправьте название фильма:",
        parse_mode="Markdown"
    )
    await state.set_state("AdminStates:waiting_for_title")


@router.message(F.text, StateFilter("AdminStates:waiting_for_title"))
async def process_title(message: Message, state: FSMContext, db: Database):
    """Обработка названия"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("❌ Название должно содержать минимум 2 символа.")
        return
    
    await state.update_data(title=title)
    await message.answer(f"✅ Название: {title}\n\nТеперь отправьте ссылку на фильм (http/https):", parse_mode="Markdown")
    await state.set_state("AdminStates:waiting_for_link")


@router.message(F.text, StateFilter("AdminStates:waiting_for_link"))
async def process_link(message: Message, state: FSMContext, db: Database):
    """Обработка ссылки"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(message.from_user.id)
    link = message.text.strip()
    
    if not link.startswith(('http://', 'https://')):
        await message.answer("❌ Ссылка должна начинаться с http:// или https://")
        return
    
    await state.update_data(link=link)
    await message.answer(f"✅ Ссылка принята.\n\nТеперь отправьте год выпуска (например: 2023) или пропустите:", parse_mode="Markdown")
    await state.set_state("AdminStates:waiting_for_year")


@router.message(F.text, StateFilter("AdminStates:waiting_for_year"))
async def process_year(message: Message, state: FSMContext, db: Database):
    """Обработка года"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip()
    year = None
    
    if text.isdigit() and 1900 <= int(text) <= 2030:
        year = int(text)
    
    await state.update_data(year=year)
    await message.answer(f"✅ Год: {year if year else 'пропущен'}\n\nТеперь отправьте качество (480p, 720p, 1080p, 4K) или пропустите:", parse_mode="Markdown")
    await state.set_state("AdminStates:waiting_for_quality")


@router.message(F.text, StateFilter("AdminStates:waiting_for_quality"))
async def process_quality(message: Message, state: FSMContext, db: Database):
    """Обработка качества"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip().lower()
    quality = "1080p"
    
    if text in ["480p", "720p", "1080p", "4k"]:
        quality = text.upper() if text == "4k" else text
    
    await state.update_data(quality=quality)
    await message.answer(f"✅ Качество: {quality}\n\nТеперь отправьте рейтинг (0.0-10.0) или пропустите:", parse_mode="Markdown")
    await state.set_state("AdminStates:waiting_for_rating")


@router.message(F.text, StateFilter("AdminStates:waiting_for_rating"))
async def process_rating(message: Message, state: FSMContext, db: Database):
    """Обработка рейтинга"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return
    
    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip()
    rating = 7.5
    
    try:
        rating_val = float(text.replace(',', '.'))
        if 0 <= rating_val <= 10:
            rating = rating_val
    except ValueError:
        pass
    
    await state.update_data(rating=rating)
    await message.answer(f"✅ Рейтинг: {rating}\n\nТеперь отправьте жанры через запятую (например: боевик, фантастика) или пропустите:", parse_mode="Markdown")
    await state.set_state("AdminStates:waiting_for_genres")


@router.message(StateFilter("AdminStates:waiting_for_genres"))
async def process_genres(message: Message, state: FSMContext, db: Database):
    """Обработка жанров"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return

    lang = db.get_user_language(message.from_user.id)
    genres_text = message.text.strip()
    genres = []

    if genres_text and genres_text.lower() != "пропустить":
        genres = [g.strip() for g in genres_text.split(',')]

    await state.update_data(genres=genres)
    await message.answer(
        f"✅ Жанры: {', '.join(genres) if genres else 'N/A'}\n\n"
        f"Шаг 7/11: Отправьте файл постера (изображение) или напишите \"пропустить\":",
        parse_mode="Markdown"
    )
    await state.set_state("AdminStates:waiting_for_poster")


@router.message(StateFilter("AdminStates:waiting_for_poster"))
async def process_poster(message: Message, state: FSMContext, db: Database):
    """Обработка постера - фото или текст"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return

    # Проверяем тип сообщения
    if message.photo:
        # Скачиваем фото
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        
        import os
        os.makedirs("media", exist_ok=True)
        
        data = await state.get_data()
        code = data.get('code', 'unknown')
        file_path = f"media/poster_{code}.jpg"
        
        await message.bot.download_file(file.file_path, file_path)
        
        await state.update_data(poster_url=file_path)
        await message.answer(
            f"✅ Постер сохранён\n\n"
            f"Шаг 8/11: Отправьте файл трейлера (видео) или напишите \"пропустить\":",
            parse_mode="Markdown"
        )
        await state.set_state("AdminStates:waiting_for_trailer")
    
    elif message.text:
        text = message.text.strip()
        
        if text.lower() == "пропустить":
            await state.update_data(poster_url=None)
            await message.answer(
                f"✅ Постер пропущен\n\n"
                f"Шаг 8/11: Отправьте файл трейлера (видео) или напишите \"пропустить\":",
                parse_mode="Markdown"
            )
            await state.set_state("AdminStates:waiting_for_trailer")
        else:
            await message.answer("❌ Отправьте файл изображения или напишите \"пропустить\":")
    
    else:
        await message.answer("❌ Отправьте файл изображения или напишите \"пропустить\":")


@router.message(StateFilter("AdminStates:waiting_for_trailer"))
async def process_trailer(message: Message, state: FSMContext, db: Database):
    """Обработка трейлера - видео или текст"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return

    # Проверяем тип сообщения
    if message.video:
        # Проверяем размер (макс 20MB)
        if message.video.file_size > 20 * 1024 * 1024:
            await message.answer("❌ Файл слишком большой (макс 20MB). Отправьте меньший файл или напишите \"пропустить\":")
            return

        # Скачиваем видео
        video = message.video
        file = await message.bot.get_file(video.file_id)
        
        import os
        os.makedirs("media", exist_ok=True)
        
        data = await state.get_data()
        code = data.get('code', 'unknown')
        file_path = f"media/trailer_{code}.mp4"
        
        await message.bot.download_file(file.file_path, file_path)
        
        await state.update_data(trailer_url=file_path)
        await message.answer(
            f"✅ Трейлер сохранён\n\n"
            f"Шаг 9/11: Отправьте актёров через запятую (например: Ди Каприо, Питт) или напишите \"пропустить\":",
            parse_mode="Markdown"
        )
        await state.set_state("AdminStates:waiting_for_actors")
    
    elif message.text:
        text = message.text.strip()
        
        if text.lower() == "пропустить":
            await state.update_data(trailer_url=None)
            await message.answer(
                f"✅ Трейлер пропущен\n\n"
                f"Шаг 9/11: Отправьте актёров через запятую (например: Ди Каприо, Питт) или напишите \"пропустить\":",
                parse_mode="Markdown"
            )
            await state.set_state("AdminStates:waiting_for_actors")
        else:
            await message.answer("❌ Отправьте файл видео или напишите \"пропустить\":")
    
    else:
        await message.answer("❌ Отправьте файл видео или напишите \"пропустить\":")


@router.message(StateFilter("AdminStates:waiting_for_actors"))
async def process_actors(message: Message, state: FSMContext, db: Database):
    """Обработка актёров"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return

    text = message.text.strip()
    actors = []

    if text.lower() != "пропустить":
        actors = [a.strip() for a in text.split(',')]

    await state.update_data(actors=actors)
    await message.answer(
        f"✅ Актёры: {', '.join(actors) if actors else 'пропущены'}\n\n"
        f"Шаг 10/11: Отправьте режиссёров через запятую (например: Нолан, Спилберг) или напишите \"пропустить\":",
        parse_mode="Markdown"
    )
    await state.set_state("AdminStates:waiting_for_directors")


@router.message(StateFilter("AdminStates:waiting_for_directors"))
async def process_directors(message: Message, state: FSMContext, db: Database):
    """Обработка режиссёров и финальное добавление"""
    if message.from_user.id not in AppConfig.ADMIN_IDS:
        return

    text = message.text.strip()
    directors = []

    if text.lower() != "пропустить":
        directors = [d.strip() for d in text.split(',')]

    await state.update_data(directors=directors)
    
    # Получаем все данные и добавляем фильм
    data = await state.get_data()

    try:
        # Проверяем код ещё раз перед добавлением
        if db.check_code_duplicate(data['code']):
            await message.answer(
                f"❌ ОШИБКА: Код `{data['code']}` уже используется!\n\n"
                f"Начните добавление заново с другим кодом.",
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        success = db.add_movie(
            code=data['code'],
            title=data['title'],
            link=data['link'],
            year=data.get('year'),
            description='',
            poster_url=data.get('poster_url'),
            trailer_url=data.get('trailer_url'),
            quality=data.get('quality', '1080p'),
            rating=data.get('rating', 7.5),
            genres=data.get('genres', []),
            actors=data.get('actors', []),
            directors=data.get('directors', [])
        )

        if success:
            lang = db.get_user_language(message.from_user.id)
            logger.info(f"Фильм добавлен: код={data['code']}, название={data['title']}")
            
            # Отправляем уведомления пользователям
            from services import NotificationService
            from app_types import MovieInfo
            notification_service = NotificationService(message.bot, db)
            
            movie_info = MovieInfo(
                id=0,
                code=data['code'],
                title=data['title'],
                link=data['link'],
                year=data.get('year'),
                description='',
                poster_url=data.get('poster_url'),
                banner_url=None,
                trailer_url=data.get('trailer_url'),
                quality=data.get('quality', '1080p'),
                views=0,
                rating=data.get('rating', 7.5),
                duration=None,
                genres=data.get('genres', [])
            )

            # Отправляем уведомления (не блокируя основной процесс)
            # exclude_admins=False - админы тоже получают уведомления
            import asyncio
            
            async def send_notifications():
                try:
                    count = await notification_service.notify_new_movie(movie_info, exclude_admins=False)
                    logger.info(f"📢 Уведомления отправлены: {count} получателей")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки уведомлений: {e}", exc_info=True)
            
            asyncio.create_task(send_notifications())

            await message.answer(
                f"✅ ФИЛЬМ ДОБАВЛЕН!\n\n"
                f"Код: `{data['code']}`\n"
                f"Название: {data['title']}\n"
                f"Год: {data.get('year', 'N/A')}\n"
                f"Качество: {data.get('quality', '1080p')}\n"
                f"Рейтинг: {data.get('rating', 7.5)}\n"
                f"Жанры: {', '.join(data.get('genres', [])) if data.get('genres') else 'N/A'}\n"
                f"🎬 Актёры: {', '.join(data.get('actors', [])) if data.get('actors') else 'N/A'}\n"
                f"🎥 Режиссёры: {', '.join(data.get('directors', [])) if data.get('directors') else 'N/A'}\n"
                f"🖼️ Постер: {'✅' if data.get('poster_url') else '❌'}\n"
                f"🎥 Трейлер: {'✅' if data.get('trailer_url') else '❌'}\n"
                f"Ссылка: {data['link']}\n\n"
                f"💡 Пользователи могут найти его по коду `{data['code']}`\n\n"
                f"📢 Уведомления отправлены пользователям!",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(lang, is_admin=True)
            )
        else:
            await message.answer(f"❌ Не удалось добавить фильм. Код `{data['code']}` уже используется.", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка добавления фильма: {e}", exc_info=True)
        await message.answer(f"❌ ОШИБКА:\n`{str(e)}`", parse_mode="Markdown")

    await state.clear()
