#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚨 URGENT NEWS — Автопостинг сверх-актуальных новостей

Модуль для парсинга и автопостинга критически важных новостей:
- Парсинг раз в 2-5 минут
- Автопостинг минуя предложку
- ✅ ГЛОБАЛЬНАЯ дедупликация (интеграция с global_dedup.py)
- ✅ МНОГОУРОВНЕВАЯ проверка на дубликаты
- Улучшенная защита от дубликатов
- Система приоритетов (интерес 0-100)

Примеры триггеров:
- Начавшаяся военная операция
- Критические изменения на рынке (обвал/рост > 5%)
- Чрезвычайные происшествия
- Важные политические заявления
"""
import os
import re
import hashlib
import json
import asyncio
import logging
import signal
import ssl
import aiohttp
import aiosqlite
import feedparser
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# ✅ ИМПОРТ ГЛОБАЛЬНОЙ ДЕДУПЛИКАЦИИ
try:
    from global_dedup import (
        get_content_dedup_hash,
        init_global_db,
        is_global_duplicate,
        mark_global_posted,
        check_duplicate_multi_layer,
        is_similar_recent_news,
    )
    GLOBAL_DEDUP_ENABLED = True
except ImportError:
    GLOBAL_DEDUP_ENABLED = False
    logging.warning("⚠️ global_dedup.py не найден — дедупликация работает в базовом режиме")

load_dotenv()

# ================= КОНФИГУРАЦИЯ =================
class UrgentConfig:
    """Конфигурация для срочных новостей"""
    
    # Telegram
    TG_TOKEN = os.getenv("TG_TOKEN", "")
    
    # Каналы для автопостинга
    CHANNELS = {
        "politics": os.getenv("TG_CHANNEL_POLITICS", "-1003659350130"),
        "economy": os.getenv("TG_CHANNEL_ECONOMY", "-1003711339547"),
        "cinema": os.getenv("TG_CHANNEL_CINEMA", "-1003892651191"),
    }
    
    # Источники для срочных новостей (только самые надёжные)
    URGENT_FEEDS = {
        "politics": [
            "https://tass.ru/rss/v2.xml",
            "https://www.interfax.ru/rss.asp",
            "https://ria.ru/export/rss2/archive/index.xml",
        ],
        "economy": [
            "https://tass.ru/rss/v2.xml",
            "https://www.interfax.ru/rss.asp",
            "https://www.vedomosti.ru/rss/news",
        ],
    }
    
    # Интервал парсинга (секунды)
    PARSE_INTERVAL = 120  # 2 минуты

    # Максимальный возраст новостей для срочных (часы)
    MAX_NEWS_AGE_HOURS = 3  # Только новости за последние 3 часа

    # Минимальный приоритет для автопостинга (0-100)
    AUTOPOST_THRESHOLD = 85
    
    #Cooldown между постами в один канал (секунды)
    POST_COOLDOWN = 300  # 5 минут
    
    # Период проверки дубликатов (часы)
    DUPLICATE_CHECK_HOURS = 24
    
    # БД для дедупликации
    DB_PATH = "urgent_news.db"
    
    # Логирование
    LOG_FILE = "logs/urgent_news.log"


config = UrgentConfig()

# ================= ЛОГИРОВАНИЕ =================
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


# ================= КЛЮЧЕВЫЕ СЛОВА ДЛЯ СРОЧНЫХ НОВОСТЕЙ =================
# Триггеры для автопостинга с высоким приоритетом

URGENT_POLITICS_KEYWORDS = {
    # Военные действия
    ("военн", "операци", 100),
    ("начал", "операци", 95),
    ("удар", "ракет", 95),
    ("обстрел", "город", 90),
    ("эскалаци", "конфликт", 90),
    ("мобилизаци", "объявлен", 95),
    ("перемири", "прекращен", 85),
    
    # Критические заявления
    ("путин", "заявлен", 90),
    ("президент", "обращен", 95),
    ("экстрен", "заявлен", 90),
    ("совет", "безопасност", 85),
    
    # Международные отношения
    ("санкц", "введен", 85),
    ("разрыв", "дипломатическ", 90),
    ("нато", "размещен", 85),
    ("ядерн", "угроз", 95),
    
    # Чрезвычайные ситуации
    ("теракт", "совершен", 95),
    ("взрыв", "произошел", 90),
    ("чрезвычайн", "положен", 85),
}

URGENT_ECONOMY_KEYWORDS = {
    # Рынки и финансы
    ("курс", "доллар", 85),
    ("курс", "рубль", 85),
    ("обвал", "рынок", 95),
    ("крах", "биржа", 95),
    ("дефолт", "объявлен", 100),
    ("девальваци", "рубль", 90),
    
    # Ключевые решения
    ("ключевая", "ставка", 85),
    ("цб", "решен", 80),
    ("санкц", "нефть", 90),
    ("эмбарго", "введен", 85),
    
    # Кризисные явления
    ("кризис", "наступил", 90),
    ("рецесси", "экономика", 85),
    ("инфляци", "взлетел", 85),
    ("безработиц", "вырос", 80),
    
    # Энергоресурсы
    ("нефть", "упал", 85),
    ("нефть", "вырос", 80),
    ("газ", "отключен", 90),
    ("энергетическ", "кризис", 90),
}


# ================= ДЕДУПЛИКАЦИЯ =================
async def init_urgent_db():
    """Инициализация БД для срочных новостей + глобальная дедупликация"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS urgent_posted (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE,
                content_hash TEXT NOT NULL,
                title TEXT,
                category TEXT NOT NULL,
                priority INTEGER,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Индексы для быстрой проверки
        await db.execute("CREATE INDEX IF NOT EXISTS idx_urgent_hash ON urgent_posted(content_hash)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_urgent_category ON urgent_posted(category)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_urgent_time ON urgent_posted(posted_at)")

        await db.commit()

    # ✅ Инициализация глобальной дедупликации
    if GLOBAL_DEDUP_ENABLED:
        await init_global_db()
        logger.info("✅ Глобальная дедупликация инициализирована")
    
    logger.info("✅ БД urgent_news инициализирована")


def get_content_hash(title: str, body: str, category: str) -> str:
    """
    Создаёт хеш для дедупликации срочных новостей.
    Использует глобальную функцию для консистентности.
    """
    return get_content_dedup_hash(title, body, category)


async def is_urgent_duplicate(title: str, body: str, category: str, hours: int = None) -> Tuple[bool, str]:
    """
    ✅ МНОГОУРОВНЕВАЯ проверка на дубликаты для срочных новостей.
    Returns: (is_duplicate, reason)
    """
    if hours is None:
        hours = config.DUPLICATE_CHECK_HOURS

    if not GLOBAL_DEDUP_ENABLED:
        # Базовая проверка без глобальной дедупликации
        content_hash = get_content_hash(title, body, category)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with aiosqlite.connect(config.DB_PATH) as db:
            async with db.execute(
                "SELECT 1 FROM urgent_posted WHERE content_hash = ? AND category = ? AND posted_at > ?",
                (content_hash, category, cutoff)
            ) as cursor:
                return (await cursor.fetchone() is not None), "local_hash"

    # ✅ СЛОЙ 0: Проверка на очень похожие заголовки за последний час (для срочных новостей)
    # Это предотвращает публикацию одинаковых новостей с разными формулировками
    from global_dedup import texts_are_similar, DB_PATH as GLOBAL_DB, normalize_text_for_dedup
    cutoff_short = datetime.now(timezone.utc) - timedelta(hours=1)
    
    async with aiosqlite.connect(GLOBAL_DB) as db:
        async with db.execute(
            "SELECT title_preview FROM global_posted WHERE category = ? AND posted_at > ?",
            (category.lower(), cutoff_short)
        ) as cursor:
            rows = await cursor.fetchall()
            for (prev_title,) in rows:
                if prev_title and texts_are_similar(title, prev_title, threshold=0.70):
                    logger.info(f"🔄 Срочная новость - похожий заголовок (70%): '{title[:50]}' ~ '{prev_title[:50]}'")
                    return True, "urgent_similar_title"
                
                # ✅ Дополнительная проверка: одинаковое событие + одинаковое место
                norm_title = normalize_text_for_dedup(title)
                norm_prev = normalize_text_for_dedup(prev_title)
                
                # Если после нормализации обе новости про одно событие и место
                if norm_title == norm_prev and len(norm_title) > 10:
                    logger.info(f"🔄 Срочная новость - одинаковые сущности: '{title[:50]}' == '{prev_title[:50]}'")
                    return True, "urgent_same_event"

    # ✅ Используем многоуровневую проверку
    return await check_duplicate_multi_layer(title, body, category, hours)


async def mark_urgent_posted(link: str, content_hash: str, title: str, category: str, priority: int):
    """Отметить новость как опубликованную (локально + глобально)"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO urgent_posted (link, content_hash, title, category, priority) VALUES (?, ?, ?, ?, ?)",
            (link, content_hash, title, category, priority)
        )
        await db.commit()
    
    # ✅ Отмечаем в глобальной дедупликации
    if GLOBAL_DEDUP_ENABLED:
        await mark_global_posted(content_hash, "urgent_news", "urgent_news", title, category)


# ================= ПРИОРИТЕТЫ =================
def calculate_priority(title: str, summary: str, category: str) -> Tuple[int, List[str]]:
    """
    Рассчитывает приоритет новости (0-100) и возвращает сработавшие триггеры.
    
    Returns:
        (priority, matched_triggers)
    """
    text = f"{title} {summary}".lower()
    
    keywords = URGENT_POLITICS_KEYWORDS if category == "politics" else URGENT_ECONOMY_KEYWORDS
    
    max_priority = 0
    matched = []
    
    for kw1, kw2, priority in keywords:
        if kw1 in text and kw2 in text:
            if priority > max_priority:
                max_priority = priority
            matched.append(f"{kw1}+{kw2}")
    
    # Бонус за свежесть (новости за последний час)
    if "только что" in text or "минут" in text or "сегодня" in text:
        max_priority = min(100, max_priority + 5)
    
    return max_priority, matched


# ================= ПАРСИНГ =================
async def fetch_feed(session: aiohttp.ClientSession, url: str) -> List[dict]:
    """Парсинг RSS ленты"""
    try:
        ssl_ctx = ssl.create_default_context()
        async with session.get(url, ssl=ssl_ctx, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []

            content = await resp.text(encoding='utf-8')
            feed = feedparser.parse(content)

            entries = []
            now = datetime.now(timezone.utc)
            
            for entry in feed.entries[:10]:  # Только последние 10 записей
                title = entry.get('title', '')
                link = entry.get('link', '')
                summary = entry.get('summary', entry.get('description', ''))

                # Очищаем HTML
                summary = re.sub(r'<[^>]+>', '', summary)

                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except:
                        pass

                # ✅ ПРОВЕРКА НА ВОЗРАСТ
                if pub_date:
                    age_hours = (now - pub_date).total_seconds() / 3600
                    if age_hours > config.MAX_NEWS_AGE_HOURS:
                        logger.info(f"⏭️ Пропущена старая новость ({age_hours:.1f}ч > {config.MAX_NEWS_AGE_HOURS}ч): {title[:50]}")
                        continue
                else:
                    # ✅ Если даты нет — пропускаем (это может быть старая новость)
                    logger.info(f"⏭️ Пропущена новость без даты: {title[:50]}")
                    continue

                entries.append({
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'pub_date': pub_date,
                    'source': url
                })

            return entries

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга {url}: {e}")
        return []


# ================= ОТПРАВКА В TELEGRAM =================
async def send_to_telegram(text: str, channel: str, parse_mode: str = "HTML") -> bool:
    """Отправка поста в Telegram"""
    if not config.TG_TOKEN:
        logger.error("❌ TG_TOKEN не настроен")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage"
        payload = {
            "chat_id": channel,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }
        
        ssl_ctx = ssl.create_default_context()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, ssl=ssl_ctx, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Отправлено в {channel}")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"❌ Ошибка отправки: {resp.status} - {error}")
                    return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False


def format_urgent_post(title: str, summary: str, link: str, category: str, priority: int, triggers: List[str]) -> str:
    """
    Форматирование срочного поста — как у обычных ботов.
    Без лишних эмодзи и заголовков "СРОЧНО".
    """
    # Подпись канала
    if category == "politics":
        signature = "@I_Politika"
    elif category == "economy":
        signature = "@eco_steroid"
    else:
        signature = "@Film_orbita"
    
    # Формируем текст как обычный пост
    # Заголовок жирным
    text = f"<b>{title}</b>"
    
    # Тело новости (если есть)
    if summary:
        summary_text = summary[:600]
        if len(summary) > 600:
            summary_text += "..."
        text += f"\n\n{summary_text}"
    
    # Пустая строка + подпись канала
    text += f"\n\n{signature}"
    
    return text


# ================= ОСНОВНОЙ ЦИКЛ =================
class UrgentNewsBot:
    """Бот для срочных новостей"""
    
    def __init__(self):
        self.running = True
        self.last_post_time: Dict[str, float] = {}  # {channel: timestamp}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def init(self):
        """Инициализация"""
        await init_urgent_db()
        self.session = aiohttp.ClientSession()
        logger.info("✅ UrgentNewsBot инициализирован")
    
    async def close(self):
        """Закрытие"""
        if self.session:
            await self.session.close()
        logger.info("👋 UrgentNewsBot остановлен")
    
    async def check_feeds(self, category: str) -> List[dict]:
        """Проверка всех фидов категории"""
        feeds = config.URGENT_FEEDS.get(category, [])
        all_entries = []
        
        tasks = [fetch_feed(self.session, feed) for feed in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_entries.extend(result)
        
        return all_entries
    
    async def process_entry(self, entry: dict, category: str) -> Optional[dict]:
        """Обработка одной новости с многоуровневой проверкой на дубликаты"""
        title = entry['title']
        summary = entry['summary']
        link = entry['link']

        # Рассчитываем приоритет
        priority, triggers = calculate_priority(title, summary, category)

        # Проверяем порог
        if priority < config.AUTOPOST_THRESHOLD:
            return None

        # ✅ МНОГОУРОВНЕВАЯ ПРОВЕРКА НА ДУБЛИКАТЫ
        is_dup, reason = await is_urgent_duplicate(title, summary, category)
        if is_dup:
            logger.info(f"🔄 Дубликат ({reason}): {title[:50]}")
            return None

        # Проверяем cooldown канала
        channel = config.CHANNELS.get(category)
        if channel:
            last_post = self.last_post_time.get(channel, 0)
            if datetime.now().timestamp() - last_post < config.POST_COOLDOWN:
                logger.info(f"⏳ Cooldown для {channel}")
                return None

        # Создаём хеш для публикации
        content_hash = get_content_hash(title, summary, category)

        return {
            'title': title,
            'summary': summary,
            'link': link,
            'category': category,
            'priority': priority,
            'triggers': triggers,
            'content_hash': content_hash
        }
    
    async def post_news(self, news: dict):
        """Публикация срочной новости"""
        channel = config.CHANNELS.get(news['category'])
        if not channel:
            logger.error(f"❌ Канал для {news['category']} не найден")
            return
        
        text = format_urgent_post(
            news['title'],
            news['summary'],
            news['link'],
            news['category'],
            news['priority'],
            news['triggers']
        )
        
        success = await send_to_telegram(text, channel)
        
        if success:
            # Отмечаем как опубликованную
            await mark_urgent_posted(
                news['link'],
                news['content_hash'],
                news['title'],
                news['category'],
                news['priority']
            )
            
            # Обновляем cooldown
            self.last_post_time[channel] = datetime.now().timestamp()
            
            logger.info(f"🚨 ОПУБЛИКОВАНО: {news['title'][:50]} (priority={news['priority']})")
    
    async def cycle(self):
        """Один цикл проверки"""
        logger.info("🔄 Проверка срочных новостей...")
        
        for category in ["politics", "economy"]:
            entries = await self.check_feeds(category)
            logger.info(f"📰 {category}: найдено {len(entries)} новостей")
            
            for entry in entries:
                try:
                    news = await self.process_entry(entry, category)
                    if news:
                        await self.post_news(news)
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки: {e}")
        
        logger.info("✅ Цикл завершён")
    
    async def run(self):
        """Основной цикл работы"""
        logger.info("🚀 Запуск UrgentNewsBot...")
        
        # Обработчики сигналов
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
        
        while self.running:
            try:
                await self.cycle()
                await asyncio.sleep(config.PARSE_INTERVAL)
            except Exception as e:
                logger.error(f"❌ Ошибка цикла: {e}")
                await asyncio.sleep(10)
    
    async def shutdown(self):
        """Корректное завершение"""
        logger.info("🛑 Получен сигнал завершения...")
        self.running = False


# ================= ЗАПУСК =================
async def main():
    """Точка входа"""
    bot = UrgentNewsBot()
    
    try:
        await bot.init()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
