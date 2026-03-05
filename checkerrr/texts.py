from typing import Dict

TEXTS: Dict[str, Dict[str, str]] = {
    "ru": {
        # --- Основные тексты ---
        "start_not_subscribed": (
            "⚠️ Для доступа к функциям бота необходимо подписаться на наши каналы:\n\n"
            "{channels_list}\n\n"
            "После подписки нажмите кнопку ниже ↓"
        ),
        "start_subscribed": (
            "🎬 Добро пожаловать в КиноБот!\n\n"
            "✅ Вы подписаны на все каналы\n\n"
            "🔍 Чтобы найти фильм — введите его код в меню 🔍 Найти фильм (например: `1`, `001`, `052`)\n\n"
            "💡 Совет: можете вводить код с нулями или без (001 = 1 = 0001)"
        ),
        "check_subscription": "✅ Проверить подписку",
        "search_placeholder": "🔍 Поиск фильма",
        "movie_not_found": (
            "❌ Фильм с кодом `{code}` не найден\n\n"
            "Проверьте правильность кода или попробуйте поиск по названию"
        ),
        "movie_found": (
            "✅ Фильм найден!\n\n"
            "🎬 {title}\n"
            "{year_line}"
            "{duration_line}"
            "{rating_line}"
            "{genres_line}"
            "⭐ Код: {code}\n"
            "📺 Качество: {quality}\n"
            "👁️ Просмотров: {views}\n\n"
            "⬇️ Ссылка для просмотра:\n{link}"
        ),
        "movie_found_with_genres": (
            "✅ Фильм найден!\n\n"
            "🎬 {title}\n"
            "{year_line}"
            "{duration_line}"
            "{rating_line}"
            "🎭 Жанры: {genres}\n"
            "⭐ Код: {code}\n"
            "📺 Качество: {quality}\n"
            "👁️ Просмотров: {views}\n\n"
            "⬇️ Ссылка для просмотра:\n{link}"
        ),
        "invalid_code": "❌ Неверный формат кода. Введите код фильма (например: `1`, `001`, `123`)",

        # --- Кнопки ---
        "search_button": "🔍 Поиск фильма",
        "help_button": "ℹ️ Инструкция",
        "language_button": "🌐 Язык",
        "support_button": "🛠 Поддержка",

        # --- Команды ---
        "help": (
            "ℹ️ Инструкция по использованию:\n\n"
            "1️⃣ Подпишитесь на все каналы (обязательно)\n"
            "2️⃣ Введите код фильма (например: `1`, `001`, `052`)\n"
            "3️⃣ Получите прямую ссылку на фильм\n"
            "4️⃣ Наслаждайтесь просмотром!\n\n"
            "💡 Коды фильмов можно узнать из списка в разделе «Топ фильмов»"
        ),
        "language_changed": "✅ Язык изменён на Русский",
        "support": "🛠 Техподдержка",
        "admin_panel": "👑 Админ-панель",
        "add_movie": "➕ Добавить фильм",
        "delete_movie": "🗑 Удалить фильм",
        "edit_movie": "✏️ Редактировать фильм",
        "manage_channels": "📡 Управление каналами",
        "back": "🔙 Назад",
        "send_code": "Отправьте код фильма (только цифры):",
        "send_title": "Отправьте название фильма:",
        "send_link": "Отправьте ссылку на фильм:",
        "movie_added": "✅ Фильм `{title}` с кодом `{code}` добавлен!",
        "movie_deleted": "✅ Фильм с кодом `{code}` удалён",
        "movie_updated": "✅ Фильм с кодом `{code}` обновлён",
        "movie_exists": "❌ Фильм с таким кодом уже существует",
        "cancel": "❌ Отмена",

        # --- Новые команды ---
        "command_start": (
            "🎬 Добро пожаловать в КиноБот!\n\n"
            "Для начала работы:\n"
            "1️⃣ Подпишитесь на все каналы\n"
            "2️⃣ Нажмите кнопку «Проверить подписку»\n"
            "3️⃣ Используйте бота для поиска фильмов"
        ),
        "command_help": (
            "ℹ️ Инструкция по использованию:\n\n"
            "1️⃣ Подпишитесь на все каналы (обязательно)\n"
            "2️⃣ Получите код фильма от администратора\n"
            "3️⃣ Отправьте код боту (например: `1` или `001`)\n"
            "4️⃣ Получите прямую ссылку на фильм\n\n"
            "🆕 Поиск по:\n"
            "• Названию\n"
            "• Актёру\n"
            "• Жанру\n\n"
            "❗ Важно: не передавайте коды третьим лицам"
        ),
        "command_language": (
            "🌐 Выберите язык:\n\n"
            "🇷🇺 Русский — нажмите кнопку «🌐 Язык»\n"
            "🇬🇧 English — press «🌐 Language» button\n\n"
            "💡 Для переключения нажмите на соответствующую кнопку"
        ),
        "command_support": (
            "🛠 Техподдержка\n\n"
            "Если у вас возникли проблемы:\n"
            "• Проверьте подписку на каналы\n"
            "• Убедитесь, что код введён правильно\n"
            "• Обратитесь в поддержку: {support_link}"
        ),
        "command_admin": (
            "👑 Админ-панель\n\n"
            "Доступные функции:\n"
            "• Добавить фильм\n"
            "• Редактировать фильм\n"
            "• Удалить фильм\n"
            "• Список фильмов\n"
            "• Статистика\n"
            "• Экспорт/Импорт\n"
            "• Рассылка"
        ),
        "command_invalid": (
            "❌ Неизвестная команда\n\n"
            "Доступные команды:\n"
            "/start — начать работу\n"
            "/help — инструкция\n"
            "/language — сменить язык\n"
            "/stats — статистика (админ)"
        ),
        "command_debug": (
            "🔍 Отладочная информация\n\n"
            "Ваш ID: {user_id}\n"
            "Язык: {lang}\n"
            "Подписка: {subscription_status}\n\n"
            "💡 Для проверки подписки нажмите «Проверить подписку»"
        ),

        # --- Статусы подписки ---
        "subscription_status_subscribed": "✅ Подписан",
        "subscription_status_not_subscribed": "❌ Не подписан",
        "subscription_status_unknown": "❓ Неизвестно",

        # --- Избранное ---
        "favorites_added": "⭐ Фильм добавлен в избранное",
        "favorites_removed": "❌ Фильм удалён из избранного",
        "favorites_empty": "📂 Ваше избранное пусто",
        "favorites_list": "⭐ Ваше избранное ({count} фильмов):\n\n",

        # --- Похожие фильмы ---
        "similar_movies": "🎬 Похожие фильмы:\n\n",
        "no_similar_movies": "😔 Похожих фильмов не найдено",

        # --- Жанры ---
        "genres_list": "🎭 Доступные жанры:\n\n",
        "genre_movies": "🎭 Фильмы в жанре «{genre}»:\n\n",

        # --- История поиска ---
        "search_history": "📜 Ваша история поиска:\n\n",
        "search_history_empty": "📜 История поиска пуста",

        # --- История просмотров ---
        "view_history": "🎬 Ваша история просмотров:\n\n",
        "view_history_empty": "🎬 История просмотров пуста",

        # --- Меню истории ---
        "history_menu": "📂 Выберите тип истории:",

        # --- Статистика пользователя ---
        "user_stats": (
            "📊 Ваша статистика:\n\n"
            "🔍 Всего поисков: {total_searches}\n"
            "⭐ В избранном: {favorites_count}\n"
            "🕐 Последний поиск: {last_search}\n\n"
        ),

        # --- Подписка (улучшенная) ---
        "subscription_check_passed": "✅ Вы подписаны на все каналы!",
        "subscription_check_failed": (
            "❌ Вы не подписаны на каналы:\n\n"
            "{failed_channels}\n\n"
            "Подпишитесь и нажмите «Проверить подписку»"
        ),
        "subscription_check_timer": "⏳ Проверка подписки... ({seconds}с)",

        # --- Админка ---
        "admin_movie_list": "📋 Список фильмов (стр. {page}/{total_pages}, всего: {total}):\n\n",
        "admin_movie_deleted": "✅ Фильм «{title}» (код: {code}) удалён",
        "admin_movie_edit_title": "✏️ Отправьте новое название для фильма:",
        "admin_movie_edit_link": "🔗 Отправьте новую ссылку:",
        "admin_movie_edit_year": "📅 Отправьте новый год:",
        "admin_movie_edit_quality": "📺 Отправьте новое качество (480p, 720p, 1080p, 4K):",
        "admin_movie_edit_rating": "⭐ Отправьте новый рейтинг (0-10):",
        "admin_stats_general": (
            "📊 Общая статистика:\n\n"
            "🎬 Фильмов: {total_movies}\n"
            "👁️ Всего просмотров: {total_views}\n"
            "👥 Активных пользователей: {active_users}\n"
            "🔍 Поисков сегодня: {searches_today}\n"
            "🔍 Поисков за неделю: {searches_week}"
        ),
        "admin_stats_top": "🔥 Топ фильмов ({period}):\n\n",
        "admin_empty_searches": "🔍 Пустые поисковые запросы (за {days} дней):\n\n",
        
        # --- Статистика пользователей ---
        "admin_user_stats": (
            "👥 Статистика пользователей (без учёта админов)\n\n"
            "📊 За {period}:\n"
            "• Посещений: {total_visits}\n"
            "• Уникальных пользователей: {unique_users}\n"
            "• Посещений сегодня: {visits_today}\n"
            "• Посещений за неделю: {visits_week}\n"
            "• Посещений за месяц: {visits_month}\n\n"
            "🔝 Топ пользователей:\n{top_users_list}"
        ),
        "admin_user_stats_full": (
            "👥 Статистика пользователей (за всё время)\n\n"
            "📊 Общие данные:\n"
            "• Всего посещений: {total_visits}\n"
            "• Уникальных пользователей: {unique_users}\n"
            "• Посещений сегодня: {visits_today}\n"
            "• Посещений за неделю: {visits_week}\n"
            "• Посещений за месяц: {visits_month}\n\n"
            "🔝 Топ пользователей:\n{top_users_list}\n\n"
            "🆕 Новые пользователи:\n{new_users_list}"
        ),
        "admin_user_list": (
            "👥 Пользователи (топ {count}):\n\n"
            "{users_list}\n\n"
            "Формат: ID | Поисков | Посещений | В избранном | Подписка | Дата регистрации"
        ),
        "admin_user_activity": (
            "📈 Активность пользователей (за {days} дней):\n\n"
            "{activity_list}"
        ),
        
        # --- Админ-панель тексты ---
        "admin_panel_title": "👑 Админ-панель",
        "admin_channels_title": "📡 Каналы для проверки подписки:\n\n",
        "admin_channels_from_db": "Из базы данных:\n",
        "admin_channels_from_config": "Из конфига (.env):\n",
        "admin_channels_warning": "\n\n⚠️ Важно: бот должен быть администратором во всех каналах",
        "admin_import_start": "📤 Отправьте CSV файл.\n\nФормат: code,title,year,description,link,poster_url,quality,views,rating",
        "admin_import_success": "✅ Импорт завершён!\n\n📊 Добавлено: {added}\n⏭️ Пропущено: {skipped}",
        "admin_health_not_init": "❌ Health checker не инициализирован",
        "admin_delete_title": "🗑 **Удаление фильма**\n\n",
        "admin_edit_title": "✏️ **Редактирование фильма**\n\n",
        "admin_back_button": "🔙 Назад",
        "admin_movies_empty": "📋 База данных пуста",
        "admin_movies_empty_hint": "📋 База данных пуста.",
        "admin_movie_not_found": "❌ Фильм не найден",
        "admin_export_started": "✅ Экспорт запущен",
        "admin_export_error": "❌ Ошибка экспорта: {error}",
        "admin_csv_invalid": "❌ Отправьте файл с расширением .csv",
        "admin_top_movies": "🔥 Топ фильмов:\n\n",
        
        # --- Ошибки валидации ---
        "error_invalid_code": "❌ Неверный формат кода. Код должен содержать до 10 символов.",
        "error_invalid_title": "❌ Название должно содержать минимум 2 символа.",
        "error_invalid_link": "❌ Ссылка должна начинаться с http:// или https://.",
        "error_data_not_found": "❌ Ошибка: данные не найдены. Начните сначала.",
        "error_invalid_year": "❌ Неверный формат года. Отправьте число (например: 2023)",
        "error_invalid_rating": "❌ Рейтинг должен быть от 0.0 до 10.0",
        "error_invalid_rating_format": "❌ Неверный формат рейтинга. Отправьте число (например: 8.5)",
        "error_invalid_quality": "❌ Неверный формат качества. Отправьте: 480p, 720p, 1080p или 4K",
        "error_invalid_image": "❌ Отправьте изображение (jpg, png, etc.)",
        "error_invalid_video": "❌ Отправьте видео (mp4, etc.)",
        "error_invalid_field": "❌ Неверное поле.",
        "error_file_too_large": "❌ Файл слишком большой (макс 20MB).",
        "error_video_too_large": "❌ Видео слишком большое (макс 20MB). Отправьте файл меньшего размера.",
        "error_cancelled": "❌ Загрузка отменена.",
        "error_invalid_page": "❌ Некорректная страница",
        
        # --- Редактирование ---
        "edit_send_title": "✏️ Отправьте новое название фильма:",
        "edit_send_link": "🔗 Отправьте новую ссылку:",
        "edit_send_year": "📅 Отправьте новый год (например: 2023):",
        "edit_send_quality": "📺 Отправьте новое качество (480p, 720p, 1080p, 4K):",
        "edit_send_rating": "⭐ Отправьте новый рейтинг (0.0-10.0):",
        
        # --- Жанры ---
        "genres_empty": "❌ Жанры пока не добавлены в базу",
        "genres_select": "🎭 **Выберите жанр** или введите название жанра текстом:\n\n",
        "genres_unavailable": "🎭 Поиск по жанрам временно недоступен",
        "top_movies_empty": "🔥 Топ фильмов пуст",
        
        # --- Актёры ---
        "actors_empty": "❌ Актёры пока не добавлены в базу",
        "actors_select": "🎬 **Актёры** (страница {page}/{total_pages})\n\nВыберите актёра или введите имя текстом:\n\n",
        
        # --- Режиссёры ---
        "directors_empty": "❌ Режиссёры пока не добавлены в базу",
        "directors_select": "🎥 **Режиссёры** (страница {page}/{total_pages})\n\nВыберите режиссёра или введите имя текстом:\n\n",

        # --- Рассылка ---
        "admin_broadcast_start": (
            "📨 Рассылка пользователям\n\n"
            "Отправьте текст сообщения для рассылки.\n"
            "Поддерживается Markdown."
        ),
        "admin_broadcast_sent": "✅ Рассылка отправлена {count} пользователям",
        "admin_broadcast_error": "❌ Ошибка рассылки: {error}",

        # --- Поиск ---
        "search_by_title": "🎬 Найдено по названию «{query}»:\n\n",
        "search_by_actor": "🎭 Фильмы с актёром «{query}»:\n\n",
        "search_by_genre": "🎭 Фильмы в жанре «{query}»:\n\n",
        "search_results": "💡 Отправьте код фильма для получения ссылки",
        "search_not_found": (
            "❌ Фильм не найден.\n\n"
            "Попробуйте:\n"
            "• Код (например: `1` или `001`)\n"
            "• Название фильма\n"
            "• Имя актёра\n"
            "• Жанр (боевик, комедия...)"
        ),
        "search_empty_query": "❌ Введите поисковый запрос (минимум 2 символа)",

        # --- Health Check ---
        "health_check": (
            "🔍 Health Check\n\n"
            "Статус: **{status}**\n"
            "Время: {timestamp}\n\n"
            "{components}"
        ),
    },

    "en": {
        # --- Основные тексты ---
        "start_not_subscribed": (
            "⚠️ To access bot features you must subscribe to our channels:\n\n"
            "{channels_list}\n\n"
            "After subscribing, press the button below ↓"
        ),
        "start_subscribed": (
            "🎬 Welcome to MovieBot!\n\n"
            "✅ You are subscribed to all channels\n\n"
            "🔍 To find a movie, send:\n"
            "• Movie code (e.g.: `1` or `001`)\n"
            "• Movie title\n"
            "• Actor name\n"
            "• Genre (e.g.: action, comedy)\n\n"
            "💡 Tip: you can enter code with or without leading zeros (001 = 1)"
        ),
        "check_subscription": "✅ Check subscription",
        "search_placeholder": "🔍 Search movie",
        "movie_not_found": (
            "❌ Movie with code `{code}` not found\n\n"
            "Check code correctness or try search by title"
        ),
        "movie_found": (
            "✅ Movie found!\n\n"
            "🎬 {title}\n"
            "{year_line}"
            "{duration_line}"
            "{rating_line}"
            "⭐ Code: `{code}`\n"
            "📺 Quality: {quality}\n"
            "👁️ Views: {views}\n\n"
            "⬇️ Watch link:\n{link}"
        ),
        "movie_found_with_genres": (
            "✅ Movie found!\n\n"
            "🎬 {title}\n"
            "{year_line}"
            "{duration_line}"
            "{rating_line}"
            "🎭 Genres: {genres}\n"
            "⭐ Code: `{code}`\n"
            "📺 Quality: {quality}\n"
            "👁️ Views: {views}\n\n"
            "⬇️ Watch link:\n{link}"
        ),
        "invalid_code": "❌ Invalid code format. Enter movie code (e.g.: `1`, `001`, `123`)",

        # --- Кнопки ---
        "search_button": "🔍 Search Movie",
        "help_button": "ℹ️ Instructions",
        "language_button": "🌐 Language",
        "support_button": "🛠 Support",

        # --- Команды ---
        "help": (
            "ℹ️ Usage instructions:\n\n"
            "1️⃣ Subscribe to all channels (required)\n"
            "2️⃣ Get movie code from administrator\n"
            "3️⃣ Send code to bot (with or without zeros: 001 or 1)\n"
            "4️⃣ Get direct movie link\n\n"
            "🆕 Now you can also search by:\n"
            "• Movie title\n"
            "• Actor name\n"
            "• Genre (action, comedy, drama...)"
        ),
        "language_changed": "✅ Language changed to English",
        "support": "🛠 Support",
        "admin_panel": "👑 Admin Panel",
        "add_movie": "➕ Add Movie",
        "delete_movie": "🗑 Delete Movie",
        "edit_movie": "✏️ Edit Movie",
        "manage_channels": "📡 Manage Channels",
        "back": "🔙 Back",
        "send_code": "Send movie code (digits only):",
        "send_title": "Send movie title:",
        "send_link": "Send movie link:",
        "movie_added": "✅ Movie `{title}` with code `{code}` added!",
        "movie_deleted": "✅ Movie with code `{code}` deleted",
        "movie_updated": "✅ Movie with code `{code}` updated",
        "movie_exists": "❌ Movie with this code already exists",
        "cancel": "❌ Cancel",

        # --- Новые команды ---
        "command_start": (
            "🎬 Welcome to MovieBot!\n\n"
            "To get started:\n"
            "1️⃣ Subscribe to all channels\n"
            "2️⃣ Click «Check subscription»\n"
            "3️⃣ Use the bot to search for movies"
        ),
        "command_help": (
            "ℹ️ Usage instructions:\n\n"
            "1️⃣ Subscribe to all channels (required)\n"
            "2️⃣ Get movie code from administrator\n"
            "3️⃣ Send code to bot (e.g.: `1` or `001`)\n"
            "4️⃣ Get direct movie link\n\n"
            "🆕 Search by:\n"
            "• Title\n"
            "• Actor\n"
            "• Genre\n\n"
            "❗ Important: don't share codes with third parties"
        ),
        "command_language": (
            "🌐 Select language:\n\n"
            "🇷🇺 Russian — press «🌐 Язык» button\n"
            "🇬🇧 English — press «🌐 Language» button\n\n"
            "💡 Tap the corresponding button to switch"
        ),
        "command_support": (
            "🛠 Support\n\n"
            "If you have issues:\n"
            "• Check your channel subscriptions\n"
            "• Ensure code is entered correctly\n"
            "• Contact support: {support_link}"
        ),
        "command_admin": (
            "👑 Admin Panel\n\n"
            "Available functions:\n"
            "• Add movie\n"
            "• Edit movie\n"
            "• Delete movie\n"
            "• Movies list\n"
            "• Statistics\n"
            "• Export/Import\n"
            "• Broadcast"
        ),
        "command_invalid": (
            "❌ Unknown command\n\n"
            "Available commands:\n"
            "/start — start\n"
            "/help — instructions\n"
            "/language — change language\n"
            "/stats — statistics (admin)"
        ),
        "command_debug": (
            "🔍 Debug information\n\n"
            "Your ID: {user_id}\n"
            "Language: {lang}\n"
            "Subscription: {subscription_status}\n\n"
            "💡 Click «Check subscription» to verify"
        ),

        # --- Статусы подписки ---
        "subscription_status_subscribed": "✅ Subscribed",
        "subscription_status_not_subscribed": "❌ Not subscribed",
        "subscription_status_unknown": "❓ Unknown",

        # --- Избранное ---
        "favorites_added": "⭐ Movie added to favorites",
        "favorites_removed": "❌ Movie removed from favorites",
        "favorites_empty": "📂 Your favorites are empty",
        "favorites_list": "⭐ Your favorites ({count} movies):\n\n",

        # --- Похожие фильмы ---
        "similar_movies": "🎬 Similar movies:\n\n",
        "no_similar_movies": "😔 No similar movies found",

        # --- Жанры ---
        "genres_list": "🎭 Available genres:\n\n",
        "genre_movies": "🎭 Movies in genre «{genre}»:\n\n",

        # --- История поиска ---
        "search_history": "📜 Your search history:\n\n",
        "search_history_empty": "📜 Search history is empty",

        # --- История просмотров ---
        "view_history": "🎬 Your view history:\n\n",
        "view_history_empty": "🎬 View history is empty",

        # --- Меню истории ---
        "history_menu": "📂 Select history type:",

        # --- Статистика пользователя ---
        "user_stats": (
            "📊 Your statistics:\n\n"
            "🔍 Total searches: {total_searches}\n"
            "⭐ In favorites: {favorites_count}\n"
            "🕐 Last search: {last_search}\n\n"
        ),

        # --- Подписка ---
        "subscription_check_passed": "✅ You are subscribed to all channels!",
        "subscription_check_failed": (
            "❌ You are not subscribed to:\n\n"
            "{failed_channels}\n\n"
            "Subscribe and press «Check subscription»"
        ),
        "subscription_check_timer": "⏳ Checking subscription... ({seconds}s)",

        # --- Админка ---
        "admin_movie_list": "📋 Movies list (p. {page}/{total_pages}, total: {total}):\n\n",
        "admin_movie_deleted": "✅ Movie «{title}» (code: {code}) deleted",
        "admin_movie_edit_title": "✏️ Send new title for movie:",
        "admin_movie_edit_link": "🔗 Send new link:",
        "admin_movie_edit_year": "📅 Send new year:",
        "admin_movie_edit_quality": "📺 Send new quality (480p, 720p, 1080p, 4K):",
        "admin_movie_edit_rating": "⭐ Send new rating (0-10):",
        "admin_stats_general": (
            "📊 General statistics:\n\n"
            "🎬 Movies: {total_movies}\n"
            "👁️ Total views: {total_views}\n"
            "👥 Active users: {active_users}\n"
            "🔍 Searches today: {searches_today}\n"
            "🔍 Searches this week: {searches_week}"
        ),
        "admin_stats_top": "🔥 Top movies ({period}):\n\n",
        "admin_empty_searches": "🔍 Empty search queries ({days} days):\n\n",
        
        # --- Статистика пользователей ---
        "admin_user_stats": (
            "👥 User statistics (excluding admins)\n\n"
            "📊 For {period}:\n"
            "• Visits: {total_visits}\n"
            "• Unique users: {unique_users}\n"
            "• Visits today: {visits_today}\n"
            "• Visits this week: {visits_week}\n"
            "• Visits this month: {visits_month}\n\n"
            "🔝 Top users:\n{top_users_list}"
        ),
        "admin_user_stats_full": (
            "👥 User statistics (all time)\n\n"
            "📊 General data:\n"
            "• Total visits: {total_visits}\n"
            "• Unique users: {unique_users}\n"
            "• Visits today: {visits_today}\n"
            "• Visits this week: {visits_week}\n"
            "• Visits this month: {visits_month}\n\n"
            "🔝 Top users:\n{top_users_list}\n\n"
            "🆕 New users:\n{new_users_list}"
        ),
        "admin_user_list": (
            "👥 Users (top {count}):\n\n"
            "{users_list}\n\n"
            "Format: ID | Searches | Visits | Favorites | Subscription | Registration date"
        ),
        "admin_user_activity": (
            "📈 User activity ({days} days):\n\n"
            "{activity_list}"
        ),
        
        # --- Admin panel texts ---
        "admin_panel_title": "👑 Admin Panel",
        "admin_channels_title": "📡 Channels for subscription check:\n\n",
        "admin_channels_from_db": "From database:\n",
        "admin_channels_from_config": "From config (.env):\n",
        "admin_channels_warning": "\n\n⚠️ Important: bot must be administrator in all channels",
        "admin_import_start": "📤 Send CSV file.\n\nFormat: code,title,year,description,link,poster_url,quality,views,rating",
        "admin_import_success": "✅ Import completed!\n\n📊 Added: {added}\n⏭️ Skipped: {skipped}",
        "admin_health_not_init": "❌ Health checker not initialized",
        "admin_delete_title": "🗑 **Delete Movie**\n\n",
        "admin_edit_title": "✏️ **Edit Movie**\n\n",
        "admin_back_button": "🔙 Back",
        "admin_movies_empty": "📋 Database is empty",
        "admin_movies_empty_hint": "📋 Database is empty.",
        "admin_movie_not_found": "❌ Movie not found",
        "admin_export_started": "✅ Export started",
        "admin_export_error": "❌ Export error: {error}",
        "admin_csv_invalid": "❌ Please send a .csv file",
        "admin_top_movies": "🔥 Top movies:\n\n",
        
        # --- Validation errors ---
        "error_invalid_code": "❌ Invalid code format. Code must be up to 10 characters.",
        "error_invalid_title": "❌ Title must contain at least 2 characters.",
        "error_invalid_link": "❌ Link must start with http:// or https://.",
        "error_data_not_found": "❌ Error: data not found. Start over.",
        "error_invalid_year": "❌ Invalid year format. Send a number (e.g.: 2023)",
        "error_invalid_rating": "❌ Rating must be from 0.0 to 10.0",
        "error_invalid_rating_format": "❌ Invalid rating format. Send a number (e.g.: 8.5)",
        "error_invalid_quality": "❌ Invalid quality format. Send: 480p, 720p, 1080p or 4K",
        "error_invalid_image": "❌ Please send an image (jpg, png, etc.)",
        "error_invalid_video": "❌ Please send a video (mp4, etc.)",
        "error_invalid_field": "❌ Invalid field.",
        "error_file_too_large": "❌ File is too large (max 20MB).",
        "error_video_too_large": "❌ Video is too large (max 20MB). Send a smaller file.",
        "error_cancelled": "❌ Upload cancelled.",
        "error_invalid_page": "❌ Invalid page",
        
        # --- Editing ---
        "edit_send_title": "✏️ Send new movie title:",
        "edit_send_link": "🔗 Send new link:",
        "edit_send_year": "📅 Send new year (e.g.: 2023):",
        "edit_send_quality": "📺 Send new quality (480p, 720p, 1080p, 4K):",
        "edit_send_rating": "⭐ Send new rating (0.0-10.0):",
        
        # --- Genres ---
        "genres_empty": "❌ No genres added yet",
        "genres_select": "🎭 **Select a genre** or enter genre name as text:\n\n",
        "genres_unavailable": "🎭 Genre search temporarily unavailable",
        "top_movies_empty": "🔥 Top movies is empty",
        
        # --- Actors ---
        "actors_empty": "❌ No actors added yet",
        "actors_select": "🎬 **Actors** (page {page}/{total_pages})\n\nSelect an actor or enter name as text:\n\n",
        
        # --- Directors ---
        "directors_empty": "❌ No directors added yet",
        "directors_select": "🎥 **Directors** (page {page}/{total_pages})\n\nSelect a director or enter name as text:\n\n",

        # --- Рассылка ---
        "admin_broadcast_start": (
            "📨 Broadcast to users\n\n"
            "Send message text for broadcast.\n"
            "Markdown is supported."
        ),
        "admin_broadcast_sent": "✅ Broadcast sent to {count} users",
        "admin_broadcast_error": "❌ Broadcast error: {error}",

        # --- Поиск ---
        "search_by_title": "🎬 Found by title «{query}»:\n\n",
        "search_by_actor": "🎭 Movies with actor «{query}»:\n\n",
        "search_by_genre": "🎭 Movies in genre «{query}»:\n\n",
        "search_results": "💡 Send movie code to get link",
        "search_not_found": (
            "❌ Movie not found.\n\n"
            "Try:\n"
            "• Code (e.g.: `1` or `001`)\n"
            "• Movie title\n"
            "• Actor name\n"
            "• Genre (action, comedy...)"
        ),
        "search_empty_query": "❌ Enter search query (minimum 2 characters)",

        # --- Health Check ---
        "health_check": (
            "🔍 Health Check\n\n"
            "Status: **{status}**\n"
            "Time: {timestamp}\n\n"
            "{components}"
        ),

        # --- Новые фичи ---
        "random_movie": "🎲 Random Movie",
        "trends": "📈 Trends",
        "achievements": "🏆 Achievements",
        "notifications": "🔔 Notifications",

        "trends_title": (
            "📈 **Trends**\n\n"
            "👥 Now watching: **{now_watching}** users\n\n"
            "🔥 **Popular for {period}**:\n\n"
        ),

        "achievements_title": (
            "🏆 **Achievements**\n\n"
            "📊 Progress: **{unlocked}/{total}**\n\n"
        ),

        "achievements_locked": "🔒 Locked",
        "achievements_unlocked": "✅ Unlocked",

        "notifications_enabled": (
            "🔔 **Notifications**\n\n"
            "✅ Notifications **enabled**\n\n"
            "You will receive notifications about:\n"
            "• 🎬 New movies in catalog\n"
            "• 🔔 Reminders about watched movies\n"
            "• 🏆 Unlocked achievements\n\n"
        ),

        "notifications_disabled": (
            "🔔 **Notifications**\n\n"
            "❌ Notifications **disabled**\n\n"
            "Enable to receive:\n"
            "• 🎬 New movie notifications\n"
            "• 🔔 Watched movie reminders\n"
            "• 🏆 Achievement notifications\n\n"
        ),

        "notifications_toggled": "✅ Notifications {status}",

        "similar_movies_title": "🔍 Similar Movies",
        "no_similar_movies_found": "😕 No similar movies found",

        "reactions_like": "👍 Like",
        "reactions_dislike": "👎 Dislike",
        "reactions_like_added": "👍 Like added!",
        "reactions_dislike_added": "👎 Dislike added!",
    }
}


def get_text(key: str, lang: str = "ru", **kwargs) -> str:
    """
    Получает локализованный текст по ключу с подстановкой параметров.
    """
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, TEXTS["ru"].get(key, key))

    try:
        return text.format(**kwargs)
    except KeyError:
        return text
    except Exception:
        return text