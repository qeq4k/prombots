import os
import sys

# Пытаемся загрузить .env, но не падаем если его нет
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("⚠️ Библиотека python-dotenv не установлена. Используются значения по умолчанию.")


class Config:
    # ✅ ВАЛИДАЦИЯ BOT_TOKEN
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    if not BOT_TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не установлен в .env файле!")
        print("Создайте файл .env и добавьте: BOT_TOKEN=ваш_токен_от_BotFather")
        sys.exit(1)

    # ✅ ВАЛИДАЦИЯ ADMIN_IDS
    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    if not admin_ids_raw:
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: ADMIN_IDS не установлен. Админ-панель будет недоступна!")
        ADMIN_IDS = []
    else:
        try:
            ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]
            if not ADMIN_IDS:
                print("⚠️ ADMIN_IDS пустой или содержит некорректные значения")
        except ValueError:
            print("❌ ОШИБКА: ADMIN_IDS содержит некорректные значения. Используйте числа через запятую")
            ADMIN_IDS = []

    # ✅ ФИЛЬТРАЦИЯ ПУСТЫХ КАНАЛОВ
    CHANNELS = []
    for i in range(1, 4):
        name = os.getenv(f"CHANNEL{i}_NAME", "")
        link = os.getenv(f"CHANNEL{i}_LINK", "")
        chat_id = os.getenv(f"CHANNEL{i}_ID", "")

        if name and link and chat_id:
            CHANNELS.append({"name": name, "link": link, "id": chat_id})

    if not CHANNELS:
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Каналы не настроены. Проверка подписки отключена!")
        print("Добавьте в .env: CHANNEL1_NAME, CHANNEL1_LINK, CHANNEL1_ID")

    DATABASE_PATH = os.getenv("DATABASE_PATH", "movies.db")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))
    SUPPORT_LINK = os.getenv("SUPPORT_LINK", "https://t.me/your_support")

    # 🆕 REDIS CONFIGURATION
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None) or None
    USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"

    # 🆕 ANALYTICS CONFIGURATION
    ENABLE_ANALYTICS = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
    ENABLE_SEARCH_HISTORY = os.getenv("ENABLE_SEARCH_HISTORY", "true").lower() == "true"
    EMPTY_SEARCHES_LOG_DAYS = int(os.getenv("EMPTY_SEARCHES_LOG_DAYS", "30"))

    # 🆕 CACHE CONFIGURATION
    SEARCH_CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL", "600"))  # 10 минут
    SUBSCRIPTION_CACHE_TTL = int(os.getenv("SUBSCRIPTION_CACHE_TTL", "60"))
    MOVIE_CACHE_TTL = int(os.getenv("MOVIE_CACHE_TTL", "3600"))  # 1 час

    # 🆕 PAGINATION
    MOVIES_PER_PAGE = int(os.getenv("MOVIES_PER_PAGE", "10"))
    SEARCH_RESULTS_PER_PAGE = int(os.getenv("SEARCH_RESULTS_PER_PAGE", "5"))

    # 🆕 RECOMMENDATIONS
    ENABLE_SIMILAR_MOVIES = os.getenv("ENABLE_SIMILAR_MOVIES", "true").lower() == "true"
    SIMILAR_MOVIES_COUNT = int(os.getenv("SIMILAR_MOVIES_COUNT", "5"))

    # 🆕 HEALTH CHECK
    ENABLE_HEALTH_CHECK = os.getenv("ENABLE_HEALTH_CHECK", "true").lower() == "true"
