"""
Обработчик реакций (лайки/дизлайки)
"""
import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import Database
from services import ReactionService, SimilarMoviesService, AchievementService
from texts import get_text
from constants import AchievementType

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data.startswith("like_"))
async def like_movie(callback: CallbackQuery, db: Database):
    """Лайк фильма"""
    user_id = callback.from_user.id
    movie_code = callback.data.replace("like_", "")
    
    movie = db.get_movie_by_code(movie_code)
    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return
    
    reaction_service = ReactionService(db)
    movie_id = movie.get('id')
    
    # Добавляем реакцию
    reaction_service.add_reaction(user_id, movie_id, movie_code, 'like')
    
    # Проверяем достижение "Первый лайк" (заглушка, т.к. достижения first_reaction нет)
    # achievement_service.check_and_unlock(user_id, AchievementType.FIRST_SEARCH)
    
    await callback.answer("👍 Like поставлен!", show_alert=False)
    
    # Обновляем клавиатуру с реакциями
    stats = reaction_service.get_movie_reactions(movie_id)
    user_reaction = reaction_service.get_user_reaction(user_id, movie_id)
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"👍 Like {stats['likes']}" + (" ✅" if user_reaction == 'like' else ""),
                    callback_data=f"like_{movie_code}"
                ),
                InlineKeyboardButton(
                    text=f"👎 Dislike {stats['dislikes']}" + (" ✅" if user_reaction == 'dislike' else ""),
                    callback_data=f"dislike_{movie_code}"
                )
            ],
            [
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{movie_code}"),
                InlineKeyboardButton(text="🔍 Похожие", callback_data=f"similar_{movie_code}")
            ]
        ]
    )
    
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass


@router.callback_query(F.data.startswith("dislike_"))
async def dislike_movie(callback: CallbackQuery, db: Database):
    """Дизлайк фильма"""
    user_id = callback.from_user.id
    movie_code = callback.data.replace("dislike_", "")
    
    movie = db.get_movie_by_code(movie_code)
    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return
    
    reaction_service = ReactionService(db)
    movie_id = movie.get('id')
    
    # Добавляем реакцию
    reaction_service.add_reaction(user_id, movie_id, movie_code, 'dislike')
    
    await callback.answer("👎 Dislike поставлен!", show_alert=False)
    
    # Обновляем клавиатуру
    stats = reaction_service.get_movie_reactions(movie_id)
    user_reaction = reaction_service.get_user_reaction(user_id, movie_id)
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"👍 Like {stats['likes']}" + (" ✅" if user_reaction == 'like' else ""),
                    callback_data=f"like_{movie_code}"
                ),
                InlineKeyboardButton(
                    text=f"👎 Dislike {stats['dislikes']}" + (" ✅" if user_reaction == 'dislike' else ""),
                    callback_data=f"dislike_{movie_code}"
                )
            ],
            [
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{movie_code}"),
                InlineKeyboardButton(text="🔍 Похожие", callback_data=f"similar_{movie_code}")
            ]
        ]
    )
    
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass


@router.callback_query(F.data.startswith("similar_"))
async def similar_movies(callback: CallbackQuery, db: Database):
    """Похожие фильмы"""
    user_id = callback.from_user.id
    movie_code = callback.data.replace("similar_", "")
    lang = db.get_user_language(user_id)
    
    movie = db.get_movie_by_code(movie_code)
    if not movie:
        await callback.answer("❌ Фильм не найден", show_alert=True)
        return
    
    similar_service = SimilarMoviesService(db)
    similar = similar_service.get_similar_movies(movie_code, limit=5)
    
    if not similar:
        await callback.answer("😕 Похожие фильмы не найдены", show_alert=True)
        return
    
    text = f"🔍 **Похожие фильмы на \"{movie['title']}\"**:\n\n"
    
    for i, m in enumerate(similar, 1):
        year_line = f" ({m['year']})" if m['year'] else ""
        text += f"{i}. {m['title']}{year_line} — `{m['code']}`\n"
        text += f"   🎭 Жанры: {m.get('genres_match', 0)} совпадений\n\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            *[
                [
                    InlineKeyboardButton(
                        text=f"🎬 {m['title']}",
                        callback_data=f"movie_{m['code']}"
                    )
                ]
                for m in similar[:5]
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"movie_{movie_code}")
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
