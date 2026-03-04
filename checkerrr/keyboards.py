from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict, Optional
from texts import get_text


def get_channels_keyboard(channels: List[Dict], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура с кнопками подписки на каналы"""
    if not channels:
        return InlineKeyboardMarkup(inline_keyboard=[])

    buttons = []
    for channel in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {channel['name']}",
            url=channel['link']
        )])

    buttons.append([InlineKeyboardButton(
        text=get_text("check_subscription", lang),
        callback_data="check_subscription"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_keyboard(lang: str = "ru", is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Главное меню - простое и понятное.
    Кнопка "🏠 Меню" всегда возвращает в главное состояние.
    """
    keyboard = []

    # Кнопка админки только для админов
    if is_admin:
        admin_text = "👑 Админ-панель" if lang == "ru" else "👑 Admin Panel"
        keyboard.append([KeyboardButton(text=admin_text)])

    # Кнопка профиля
    keyboard.append([KeyboardButton(text="👤 Мой профиль")])

    # Кнопка поиска
    keyboard.append([KeyboardButton(text="🔍 Найти фильм")])

    # Кнопки поиска по категориям
    keyboard.append([
        KeyboardButton(text="🎭 Поиск по жанру"),
        KeyboardButton(text="🎬 Поиск по актёру")
    ])
    keyboard.append([KeyboardButton(text="🎥 Поиск по режиссёру")])

    # Новые фичи
    keyboard.append([
        KeyboardButton(text="🎲 Случайный фильм"),
        KeyboardButton(text="📈 Тренды")
    ])
    
    # Основные кнопки
    keyboard.append([
        KeyboardButton(text="ℹ️ Помощь"),
        KeyboardButton(text="🌐 Язык")
    ])
    keyboard.append([
        KeyboardButton(text="🔥 Топ фильмов")
    ])
    keyboard.append([
        KeyboardButton(text="🛠 Поддержка")
    ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_user_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """
    Дополнительное меню (показывается после /start или подписки).
    """
    keyboard = []
    keyboard.append([
        KeyboardButton(text="ℹ️ Помощь"),
        KeyboardButton(text="🌐 Язык")
    ])
    keyboard.append([
        KeyboardButton(text="⭐ Избранное"),
        KeyboardButton(text="🔥 Топ фильмов")
    ])
    keyboard.append([KeyboardButton(text="📜 История")])
    keyboard.append([KeyboardButton(text="🛠 Поддержка")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_admin_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура админ-панели"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фильм", callback_data="admin_add_movie")],
        [InlineKeyboardButton(text="✏️ Редактировать фильм", callback_data="admin_edit_movie")],
        [InlineKeyboardButton(text="📋 Список фильмов", callback_data="admin_list_movies")],
        [InlineKeyboardButton(text="🗑 Удалить фильм", callback_data="admin_delete_movie")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Статистика пользователей", callback_data="admin_user_stats")],
        [InlineKeyboardButton(text="📤 Экспорт / Импорт", callback_data="admin_import_export")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ])


def get_admin_import_export_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура экспорта/импорта"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Экспорт в CSV", callback_data="admin_export")],
        [InlineKeyboardButton(text="📥 Импорт из CSV", callback_data="admin_import_start")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_back_to_panel")]
    ])


def get_cancel_keyboard(lang: str = "ru", back_to: str = "back_to_main") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены - возвращает в главное меню или админку"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=back_to)]
    ])


def get_admin_movies_keyboard(lang: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Inline-клавиатура для навигации по списку фильмов"""
    if total_pages < 1:
        total_pages = 1
    if current_page < 1:
        current_page = 1
    if current_page > total_pages:
        current_page = total_pages

    buttons = []
    page_buttons = []
    start_page = max(1, current_page - 2)
    end_page = min(total_pages, current_page + 2)

    for page_num in range(start_page, end_page + 1):
        text = f"•{page_num}•" if page_num == current_page else str(page_num)
        page_buttons.append(
            InlineKeyboardButton(text=text, callback_data=f"admin_page_{page_num}")
        )

    if page_buttons:
        buttons.append(page_buttons)

    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️", callback_data=f"admin_page_{current_page - 1}"
        ))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="➡️", callback_data=f"admin_page_{current_page + 1}"
        ))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_back_to_panel")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# === Inline кнопки для фильмов ===

def get_movie_inline_keyboard(movie_code: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Inline-кнопки под сообщением с фильмом"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⭐ В избранное" if lang == "ru" else "⭐ Add to favorites",
                callback_data=f"fav_add_{movie_code}"
            )
        ],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")]
    ])


def get_search_results_keyboard(results: List[Dict], lang: str = "ru", 
                                page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Inline-клавиатура с результатами поиска"""
    buttons = []

    for movie in results:
        year_str = f" ({movie.get('year', '')})" if movie.get('year') else ""
        button_text = f"🎬 {movie['title']}{year_str} — {movie['code']}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"movie_{movie['code']}"
        )])

    # Пагинация
    if total_pages > 1:
        page_buttons = []
        if page > 1:
            page_buttons.append(InlineKeyboardButton(
                text="⬅️", callback_data=f"search_page_{page - 1}"
            ))
        page_buttons.append(InlineKeyboardButton(
            text=f"{page}/{total_pages}", callback_data="search_page_info"
        ))
        if page < total_pages:
            page_buttons.append(InlineKeyboardButton(
                text="➡️", callback_data=f"search_page_{page + 1}"
            ))
        if page_buttons:
            buttons.append(page_buttons)

    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_favorites_keyboard(favorites: List[Dict], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура с избранными фильмами"""
    buttons = []

    for movie in favorites:
        year_str = f" ({movie.get('year', '')})" if movie.get('year') else ""
        button_text = f"🎬 {movie['title']}{year_str}"
        buttons.append([
            InlineKeyboardButton(text=button_text, callback_data=f"movie_{movie['code']}"),
            InlineKeyboardButton(text="❌", callback_data=f"fav_remove_{movie['code']}")
        ])

    if not buttons:
        buttons.append([InlineKeyboardButton(
            text="Пусто" if lang == "ru" else "Empty",
            callback_data="back_to_main"
        )])
    else:
        buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_similar_movies_keyboard(movies: List[Dict], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура с похожими фильмами"""
    buttons = []

    for movie in movies:
        year_str = f" ({movie.get('year', '')})" if movie.get('year') else ""
        button_text = f"🎬 {movie['title']}{year_str}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"movie_{movie['code']}"
        )])

    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_genres_keyboard(genres: List[Dict], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура с жанрами"""
    buttons = []
    row = []

    for genre in genres:
        row.append(InlineKeyboardButton(
            text=genre['name'].capitalize(),
            callback_data=f"genre_{genre['name']}"
        ))
        if len(row) >= 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_genre_movies_keyboard(genre: str, movies: List[Dict], lang: str = "ru",
                              page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура с фильмами жанра (с пагинацией)"""
    buttons = []

    for movie in movies:
        year_str = f" ({movie.get('year', '')})" if movie.get('year') else ""
        button_text = f"🎬 {movie['title']}{year_str} — {movie['code']}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"movie_{movie['code']}"
        )])

    # Пагинация
    if total_pages > 1:
        page_buttons = []
        if page > 1:
            page_buttons.append(InlineKeyboardButton(
                text="⬅️", callback_data=f"genre_page_{genre}_{page - 1}"
            ))
        page_buttons.append(InlineKeyboardButton(
            text=f"{page}/{total_pages}", callback_data="genre_page_info"
        ))
        if page < total_pages:
            page_buttons.append(InlineKeyboardButton(
                text="➡️", callback_data=f"genre_page_{genre}_{page + 1}"
            ))
        if page_buttons:
            buttons.append(page_buttons)

    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_actors_keyboard(actors: List[Dict], lang: str = "ru",
                        page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура с актёрами (с пагинацией)"""
    import hashlib

    buttons = []
    row = []

    for actor in actors:
        # Используем хэш от имени актёра для callback_data (Telegram лимит 64 байта)
        actor_hash = hashlib.md5(actor['name'].encode('utf-8')).hexdigest()[:16]
        film_count = actor.get('film_count', 0)
        button_text = f"{actor['name']} ({film_count})"

        row.append(InlineKeyboardButton(
            text=button_text,
            callback_data=f"actor_{actor_hash}"
        ))
        if len(row) >= 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Пагинация
    if total_pages > 1:
        page_buttons = []
        if page > 1:
            page_buttons.append(InlineKeyboardButton(
                text="⬅️", callback_data=f"actors_page_{page - 1}"
            ))
        page_buttons.append(InlineKeyboardButton(
            text=f"{page}/{total_pages}", callback_data="actors_page_info"
        ))
        if page < total_pages:
            page_buttons.append(InlineKeyboardButton(
                text="➡️", callback_data=f"actors_page_{page + 1}"
            ))
        if page_buttons:
            buttons.append(page_buttons)

    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_directors_keyboard(directors: List[Dict], lang: str = "ru",
                           page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура с режиссёрами (с пагинацией)"""
    import hashlib

    buttons = []
    row = []

    for director in directors:
        # Используем хэш от имени режиссёра для callback_data (Telegram лимит 64 байта)
        director_hash = hashlib.md5(director['name'].encode('utf-8')).hexdigest()[:16]
        film_count = director.get('film_count', 0)
        button_text = f"{director['name']} ({film_count})"

        row.append(InlineKeyboardButton(
            text=button_text,
            callback_data=f"director_{director_hash}"
        ))
        if len(row) >= 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Пагинация
    if total_pages > 1:
        page_buttons = []
        if page > 1:
            page_buttons.append(InlineKeyboardButton(
                text="⬅️", callback_data=f"directors_page_{page - 1}"
            ))
        page_buttons.append(InlineKeyboardButton(
            text=f"{page}/{total_pages}", callback_data="directors_page_info"
        ))
        if page < total_pages:
            page_buttons.append(InlineKeyboardButton(
                text="➡️", callback_data=f"directors_page_{page + 1}"
            ))
        if page_buttons:
            buttons.append(page_buttons)

    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_stats_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура статистики"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 За день", callback_data="stats_top_day"),
            InlineKeyboardButton(text="🔥 За неделю", callback_data="stats_top_week")
        ],
        [InlineKeyboardButton(text="🔍 Пустые поиски", callback_data="stats_empty_searches")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_back_to_panel")]
    ])


def get_user_stats_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура статистики пользователей"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 За день", callback_data="user_stats_day"),
            InlineKeyboardButton(text="📊 За неделю", callback_data="user_stats_week")
        ],
        [
            InlineKeyboardButton(text="📊 За месяц", callback_data="user_stats_month"),
            InlineKeyboardButton(text="📊 За всё время", callback_data="user_stats_all")
        ],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="user_stats_list")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_back_to_panel")]
    ])


def get_movie_edit_keyboard(movie_code: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для редактирования фильма"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"edit_title_{movie_code}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_link_{movie_code}")],
        [InlineKeyboardButton(text="📅 Год", callback_data=f"edit_year_{movie_code}")],
        [InlineKeyboardButton(text="📺 Качество", callback_data=f"edit_quality_{movie_code}")],
        [InlineKeyboardButton(text="⭐ Рейтинг", callback_data=f"edit_rating_{movie_code}")],
        [InlineKeyboardButton(text="🖼 Постер", callback_data=f"edit_poster_{movie_code}")],
        [InlineKeyboardButton(text="🎬 Баннер", callback_data=f"edit_banner_{movie_code}")],
        [InlineKeyboardButton(text="🎥 Трейлер", callback_data=f"edit_trailer_{movie_code}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_edit_movie")]
    ])


def get_delete_confirm_keyboard(movie_code: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Подтверждение удаления"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❌ Да, удалить" if lang == "ru" else "❌ Yes, delete",
                callback_data=f"delete_confirmed_{movie_code}"
            ),
            InlineKeyboardButton(
                text="🏠 Меню", callback_data="back_to_main"
            )
        ]
    ])