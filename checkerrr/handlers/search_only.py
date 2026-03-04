"""
Обработчик поиска фильмов по коду (только после нажатия кнопки)
"""
import logging
import re
import os
from aiogram import F, Router, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import Config as AppConfig
from database import Database
from keyboards import get_main_keyboard, get_movie_inline_keyboard
from texts import get_text
from utils import normalize_code_for_search
from utils import format_year_line, format_duration_line, format_rating_line
from cache import MovieCache

logger = logging.getLogger(__name__)

router = Router()


class SearchStates(StatesGroup):
    waiting_for_search = State()


# Обработчик на текстовую кнопку "🔍 Найти фильм"
@router.message(F.text == "🔍 Найти фильм")
async def search_movie_text(message: Message, state: FSMContext, db: Database):
    """Кнопка 'Найти фильм' текстом"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    
    await state.set_state(SearchStates.waiting_for_search)
    
    await message.answer(
        "🔍 **Поиск фильма**\n\n"
        "Введите код фильма (например: `1`, `001`, `179`)\n\n"
        "Или отправьте 🔕 для выхода в меню",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(lang, is_admin=is_admin)
    )


# Обработчик ввода кода в режиме поиска
@router.message(SearchStates.waiting_for_search, F.text)
async def process_search_code(message: Message, state: FSMContext, db: Database):
    """Обработка кода фильма в режиме поиска"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in AppConfig.ADMIN_IDS
    original_text = message.text.strip()
    
    # Проверка на отмену
    if original_text == "🔕":
        await state.clear()
        await message.answer(
            "❌ Поиск отменён",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        return
    
    # Проверка на кнопки меню - выходим из режима поиска
    menu_buttons = [
        "👑 Админ-панель", "Admin Panel", "ℹ️ Помощь", "ℹ️ Instructions",
        "🌐 Язык", "🌐 Language", "🛠 Поддержка", "🛠 Support",
        "⭐ Избранное", "🔥 Топ фильмов", "📜 История",
        "🎲 Случайный фильм", "📈 Тренды", "🏆 Достижения", "🔔 Уведомления",
        "🎭 Поиск по жанру", "🎬 Поиск по актёру", "🎥 Поиск по режиссёру"
    ]
    if original_text in menu_buttons:
        await state.clear()
        return
    
    # Проверяем является ли текст кодом (только цифры)
    if not original_text.isdigit() and not re.match(r'^[A-Za-z0-9]{1,10}$', original_text):
        # Не код - игнорируем или просим ввести код
        await message.answer(
            "❌ Введите код фильма цифрами (например: `1`, `118`, `179`)\n\n"
            "Или отправьте 🔕 для выхода в меню",
            parse_mode="Markdown"
        )
        return
    
    # === ПОИСК ПО КОДУ ===
    cleaned_input = re.sub(r'[^\w]', '', original_text.upper())
    movie = None
    
    # Прямой поиск по коду
    movie = db.get_movie_by_code(cleaned_input)
    
    # Если не найдено и код числовой - пробуем без ведущих нулей
    if not movie and cleaned_input.isdigit():
        normalized = str(int(cleaned_input))
        movie = db.get_movie_by_code(normalized)
    
    # Если не найдено и код числовой - пробуем с ведущими нулями
    if not movie and cleaned_input.isdigit():
        num = int(cleaned_input)
        for fmt in ["{:03d}", "{:04d}", "{:02d}", "{:05d}"]:
            padded = fmt.format(num)
            movie = db.get_movie_by_code(padded)
            if movie:
                break
    
    if movie:
        await MovieCache.set_by_code(movie['code'], movie, 3600)

        if AppConfig.ENABLE_SEARCH_HISTORY:
            db.log_user_search(user_id, original_text, 'code', 1, movie['id'])

        db.increment_views(movie['code'])
        db.log_view(movie.get('id'), user_id)
        
        # Проверяем достижения
        from services import AchievementService
        from constants import AchievementType
        achievement_service = AchievementService(db)
        await achievement_service.check_and_unlock(user_id, AchievementType.FIRST_SEARCH)
        await achievement_service.check_and_unlock(user_id, AchievementType.SEARCH_10)
        await achievement_service.check_and_unlock(user_id, AchievementType.SEARCH_50)
        await achievement_service.check_and_unlock(user_id, AchievementType.SEARCH_100)
        
        movie = db.get_movie_by_code(movie['code'])
        genres = db.get_movie_genres(movie.get('id', 0))
        year_line = format_year_line(movie.get('year'))
        duration_line = format_duration_line(movie.get('duration'))
        rating_line = format_rating_line(movie.get('rating'))
        
        # Форматируем рейтинг визуально
        rating_int = int(movie.get('rating', 0))
        rating_stars = "⭐️" * rating_int
        rating_text = f"{movie.get('rating', 0)}/10 {rating_stars}"
        
        # Постер и трейлер с эмодзи
        poster_emoji = "🖼️" if movie.get('poster_url') else "❌"
        trailer_emoji = "🎥" if movie.get('trailer_url') else "❌"
        
        if genres:
            response = (
                f"✅ **Фильм найден!**\n\n"
                f"🎬 {movie['title']}{year_line}\n"
                f"{duration_line}"
                f"⭐️ Рейтинг: {rating_text}\n"
                f"🎭 Жанры: {', '.join(genres)}\n"
                f"{poster_emoji} Постер: {'Есть' if movie.get('poster_url') else 'Нет'}\n"
                f"{trailer_emoji} Трейлер: {'Есть' if movie.get('trailer_url') else 'Нет'}\n"
                f"⭐️ Код: `{movie['code']}`\n"
                f"📺 Качество: {movie['quality']}\n"
                f"👁️ Просмотров: {movie['views']}\n\n"
                f"⬇️ Ссылка для просмотра:\n{movie['link']}"
            )
        else:
            response = (
                f"✅ **Фильм найден!**\n\n"
                f"🎬 {movie['title']}{year_line}\n"
                f"{duration_line}"
                f"⭐️ Рейтинг: {rating_text}\n"
                f"{poster_emoji} Постер: {'Есть' if movie.get('poster_url') else 'Нет'}\n"
                f"{trailer_emoji} Трейлер: {'Есть' if movie.get('trailer_url') else 'Нет'}\n"
                f"⭐️ Код: `{movie['code']}`\n"
                f"📺 Качество: {movie['quality']}\n"
                f"👁️ Просмотров: {movie['views']}\n\n"
                f"⬇️ Ссылка для просмотра:\n{movie['link']}"
            )
        
        # Отправляем с постером если есть
        if movie.get('poster_url'):
            poster_path = movie['poster_url']
            if not poster_path.startswith('/'):
                poster_path = os.path.abspath(poster_path)

            if os.path.exists(poster_path):
                try:
                    await message.answer_photo(
                        photo=FSInputFile(poster_path),
                        caption=response,
                        reply_markup=get_movie_inline_keyboard(movie['code'], lang),
                        parse_mode="Markdown"
                    )
                    # НЕ очищаем состояние - можно искать дальше
                except Exception as e:
                    logger.warning(f"Ошибка отправки постера: {e}")
                    await message.answer(
                        response,
                        reply_markup=get_movie_inline_keyboard(movie['code'], lang),
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
        else:
            await message.answer(
                response,
                reply_markup=get_movie_inline_keyboard(movie['code'], lang),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

        # Отправляем трейлер если есть (отдельным сообщением)
        if movie.get('trailer_url'):
            trailer_path = movie['trailer_url']
            if not trailer_path.startswith('/'):
                trailer_path = os.path.abspath(trailer_path)

            if os.path.exists(trailer_path):
                try:
                    await message.answer_video(
                        video=FSInputFile(trailer_path),
                        caption=f"🎥 **Трейлер к фильму \"{movie['title']}\"**",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Ошибка отправки трейлера: {e}")
        
        # НЕ очищаем состояние - можно искать дальше
        return
    else:
        # Код не найден - получаем максимальный код из БД
        max_code = db.get_max_movie_code()
        await message.answer(
            f"❌ Фильм с кодом `{original_text}` не найден\n\n"
            f"Проверьте код и попробуйте снова.\n\n"
            f"💡 Доступные коды: от 1 до {max_code}\n\n"
            f"Или отправьте 🔕 для выхода в меню",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(lang, is_admin=is_admin)
        )
        # НЕ очищаем состояние - можно попробовать другой код
