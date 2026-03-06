#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏛️ @I_Politika PRODUCTION 2026
✅ Глобальная дедупликация
✅ Circuit breaker для LLM
✅ Кэширование LLM ответов
✅ Защита от выдумывания дат
✅ Фильтрация английских слов
✅ Graceful shutdown
✅ Адаптивный rate limiting
✅ SSL верификация включена
✅ SINGLE INSTANCE LOCK - защита от запуска нескольких копий
"""
import os
import hashlib
import json
import re
import asyncio
import random
import logging
import sys
import signal
import ssl
import pickle
import time
import fcntl
import aiofiles
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse
import feedparser
import aiohttp
import aiosqlite
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv
from rapidfuzz import fuzz

# ✅ DIGEST GENERATOR — для ежедневных дайджестов
from shared import DigestGenerator, schedule_digest_for_category

# ✅ SINGLE INSTANCE LOCK - предотвращает запуск нескольких копий бота
# Не используется при запуске через PM2 (PM2 сам управляет процессами)
LOCK_FILE = Path("politika.lock")

def acquire_single_instance_lock() -> Optional[int]:
    """
    ✅ ПРОВЕРКА: только один экземпляр бота может работать одновременно.
    Возвращает fd блокировки или None если уже запущен.
    ⚠️ НЕ используется при запуске через PM2!
    """
    # Если запущены через PM2 — не используем lock
    if os.environ.get("PM2_HOME") or os.environ.get("PM2_HOME_DIR"):
        logger.info("ℹ️ Запуск через PM2 — lock не используется")
        return None
    
    try:
        LOCK_FILE.parent.mkdir(exist_ok=True)
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
        # Пытаемся получить эксклюзивную блокировку БЕЗ ожидания
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Записываем PID для отладки
        os.write(fd, f"{os.getpid()}\n".encode())
        logger.info(f"🔒 Single-instance lock acquired (PID={os.getpid()})")
        return fd
    except (IOError, OSError) as e:
        logging.error(f"❌ Бот уже запущен или блокировка не удалась: {e}")
        return None

def release_single_instance_lock(fd: int):
    """Освободить блокировку экземпляра"""
    if fd is None:
        return  # PM2 режим
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        LOCK_FILE.unlink(missing_ok=True)
        logging.info("🔓 Single-instance lock released")
    except Exception as e:
        logging.warning(f"⚠️ Ошибка освобождения блокировки: {e}")

try:
    import pymorphy3
    MORPHY = pymorphy3.MorphAnalyzer()
    LEMMATIZATION_AVAILABLE = True
except ImportError:
    LEMMATIZATION_AVAILABLE = False
    MORPHY = None


try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
    translator_en_ru = GoogleTranslator(source='en', target='ru')
except ImportError:
    TRANSLATOR_AVAILABLE = False

try:
    from global_dedup import (
        get_content_dedup_hash,
        init_global_db,
        is_global_duplicate,
        is_global_duplicate_cross_category,
        mark_global_posted,
        get_universal_hash,
        cleanup_global_db,
        is_duplicate_advanced,
        normalize_title_for_dedup,
        check_duplicate_multi_layer
    )
    GLOBAL_DEDUP_ENABLED = True
    logging.info("✅ global_dedup.py загружен")
except ImportError:
    logging.error("❌ КРИТИЧЕСКОЕ: global_dedup.py не найден!")
    logging.error("❌ Без глобальной дедупликации работа бота невозможна")
    logging.error("❌ Аварийная остановка — добавьте global_dedup.py")
    import sys
    sys.exit(1)

load_dotenv()

# ============ ИМПОРТ ИЗ SHARED PACKAGE ============
from shared import (
    write_draft_atomic,
    is_russian_text,
    normalize_text_for_dedup,
)

async def cleanup_old_logs(max_age_days=7, max_file_size_mb=50):
    """🧹 Очистка старых логов через tail (не блокирует RAM)"""
    try:
        log_dir = Path("logs")
        if not log_dir.exists():
            return

        import subprocess
        import time

        current_time = time.time()
        max_age_seconds = max_age_days * 86400
        max_size_bytes = max_file_size_mb * 1024 * 1024

        for log_file in log_dir.glob("*.log"):
            try:
                file_age = current_time - log_file.stat().st_mtime
                if file_age > max_age_seconds:
                    log_file.unlink()
                    logger.info(f"🧹 Удалён старый лог: {log_file.name}")
                    continue

                if log_file.stat().st_size > max_size_bytes:
                    temp_path = log_file.with_suffix(".tmp")
                    result = subprocess.run(
                        ["tail", "-n", "10000", str(log_file)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                            await f.write(result.stdout)
                        os.replace(temp_path, log_file)
                        logger.info(f"🧹 Лог {log_file.name} уменьшен до 10000 строк")
                    else:
                        temp_path.unlink(missing_ok=True)
                        logger.warning(f"⚠️ Ошибка tail: {result.stderr[:100]}")
            except Exception as e:
                logger.error(f"❌ Ошибка обработки лога {log_file.name}: {e}")

        total_size = sum(f.stat().st_size for f in log_dir.glob("*.log"))
        logger.info(f"📊 Логи: {len(list(log_dir.glob('*.log')))} файлов, {total_size / 1024 / 1024:.1f} MB")

    except Exception as e:
        logger.error(f"❌ Ошибка cleanup_old_logs: {e}")



# ================= АЛЕРТЫ =================
class AlertManager:
    """Менеджер алертов в Telegram"""
    def __init__(self, token: str, chat_id: str = "-5181669116"):
        self.token = token
        self.chat_id = chat_id
        self.cooldowns = {}  # {key: last_sent_time}
        self.cooldown_minutes = 30
    
    def _can_send(self, key: str) -> bool:
        import time
        if not self.chat_id:
            return False
        last = self.cooldowns.get(key)
        if not last:
            return True
        return (time.time() - last) > (self.cooldown_minutes * 60)
    
    async def send_alert(self, emoji: str, title: str, message: str, key: str = None):
        if key and not self._can_send(key):
            return
        if not self.chat_id:
            return
        
        import aiohttp
        import ssl
        
        try:
            text = f"{emoji} <b>{title}</b>\n{message}\n<i>{datetime.now().strftime('%H:%M:%S')}</i>"
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": int(self.chat_id),
                "text": text,
                "parse_mode": "HTML"
            }
            
            ssl_ctx = ssl.create_default_context()
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, ssl=ssl_ctx, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Алерт отправлен: {title}")
                        if key:
                            import time
                            self.cooldowns[key] = time.time()
        except Exception as e:
            logger.error(f"❌ Не отправлен алерт: {e}")
    
    async def alert_critical(self, title: str, msg: str, key: str = None):
        await self.send_alert("🚨", title, msg, key)
    
    async def alert_warning(self, title: str, msg: str, key: str = None):
        await self.send_alert("⚠️", title, msg, key)
    
    async def alert_info(self, title: str, msg: str, key: str = None):
        await self.send_alert("ℹ️", title, msg, key)



# ================= УТИЛИТЫ =================
def create_secure_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()

async def write_draft_atomic(draft_path: Path, data: dict):
    temp_path = draft_path.with_suffix(".tmp")
    try:
        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.replace(temp_path, draft_path)
    except Exception as e:
        logger.error(f"❌ Ошибка атомарной записи {draft_path.name}: {e}")
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

# ================= КОНФИГУРАЦИЯ =================
class BotConfig(BaseSettings):
    tg_token: str = Field(default="", min_length=10)
    router_api_key: str = Field(default="", min_length=10)

    channel: str = "@I_Politika"
    signature: str = "@I_Politika"
    model_name: str = "openai/gpt-oss-20b"

    # ✅ Каналы для подписи (из .env)
    signature_politics: str = Field(default="@I_Politika")
    signature_economy: str = Field(default="@eco_steroid")
    signature_cinema: str = Field(default="@Film_orbita")

    # ✅ Категории для глобальной дедупликации (из .env)
    category_politics: str = Field(default="politics")
    category_economy: str = Field(default="economy")
    category_cinema: str = Field(default="cinema")

    max_posts_per_day: int = 48
    max_entries_per_feed: int = 30
    max_candidates: int = 50

    cycle_delay_day_min: int = 600
    cycle_delay_day_max: int = 900
    cycle_delay_night_min: int = 1800
    cycle_delay_night_max: int = 2700

    night_start_hour: int = 22
    night_end_hour: int = 5

    max_news_age_hours: int = 12

    tg_channel_politics: str = Field(default="")
    tg_channel_economy: str = Field(default="")
    tg_channel_cinema: str = Field(default="")
    
    suggestion_chat_id_politics: str = Field(default="")
    suggestion_chat_id_economy: str = Field(default="")
    suggestion_chat_id_cinema: str = Field(default="")

    db_path: str = "polit_memory.db"
    min_delay_between_posts: int = 600
    domain_min_delay: float = 1.2

    autopost_enabled: bool = True  # ✅ Для дайджестов

    fuzzy_threshold: int = 85
    duplicate_check_hours: int = 72

    # ✅ Настройки картинок
    enable_images: bool = True  # Глобальное включение/выключение картинок
    skip_image_domains: list = []  # Домены для пропуска картинок (с водяными знаками)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def category(self) -> str:
        """✅ Автоматически определяет категорию по имени скрипта"""
        import sys
        from pathlib import Path
        script_name = Path(sys.argv[0]).stem.lower()
        
        if 'ekonom' in script_name or 'econ' in script_name:
            return self.category_economy
        elif 'kino' in script_name or 'film' in script_name or 'cinema' in script_name:
            return self.category_cinema
        else:
            return self.category_politics

    @property
    def bot_signature(self) -> str:
        """✅ Возвращает подпись канала для текущей категории"""
        cat = self.category
        if cat == "economy":
            return self.signature_economy
        elif cat == "cinema":
            return self.signature_cinema
        else:
            return self.signature_politics

    @property
    def tg_channel(self) -> str:
        """✅ Возвращает ID канала для текущей категории"""
        cat = self.category
        if cat == "economy":
            return self.tg_channel_economy
        elif cat == "cinema":
            return self.tg_channel_cinema
        else:
            return self.tg_channel_politics

    @property
    def suggestion_chat_id(self) -> str:
        """✅ Возвращает ID предложки для текущей категории"""
        cat = self.category
        if cat == "economy":
            return self.suggestion_chat_id_economy
        elif cat == "cinema":
            return self.suggestion_chat_id_cinema
        else:
            return self.suggestion_chat_id_politics

    def get_cycle_delay(self) -> int:
        current_hour = datetime.now(timezone.utc).hour
        if self.night_start_hour <= current_hour or current_hour < self.night_end_hour:
            return random.randint(self.cycle_delay_night_min, self.cycle_delay_night_max)
        return random.randint(self.cycle_delay_day_min, self.cycle_delay_day_max)

    def is_night_time(self) -> bool:
        current_hour = datetime.now(timezone.utc).hour
        return self.night_start_hour <= current_hour or current_hour < self.night_end_hour

config = BotConfig()

# ================= RSS FEEDS =================
# ✅ ОСНОВНЫЕ ФИДЫ — только проверенные источники
RSS_FEEDS = [
    "https://tass.ru/rss/v2.xml",              # ТАСС — официальные новости
    "https://www.interfax.ru/rss.asp",         # Интерфакс — политика
    "https://ria.ru/export/rss2/archive/index.xml",  # РИА — политика
    "https://lenta.ru/rss/news",               # Лента — новости
]

RSS_FEEDS_PRIORITY = {
    "https://tass.ru/rss/v2.xml": 10,
    "https://ria.ru/export/rss2/archive/index.xml": 10,
    "https://www.interfax.ru/rss.asp": 8,
    "https://lenta.ru/rss/news": 6,
}

RSS_FEEDS_PRIORITY = {
    "https://tass.ru/rss/v2.xml": 10,
    "https://ria.ru/export/rss2/archive/index.xml": 10,
    "https://www.interfax.ru/rss.asp": 8,
    "https://www.vedomosti.ru/rss/news": 7,
    "https://www.kommersant.ru/RSS/news.xml": 7,
    "https://lenta.ru/rss/news": 6,
}

# ================= КЛЮЧЕВЫЕ СЛОВА =================
POLITICS_KEYWORDS = {
    'путин', 'президент', 'правительств', 'госдум', 'депутат', 'министр',
    'кремль', 'мид', 'мвд', 'фсб', 'следком', 'прокурор',
    'выборы', 'голосован', 'партия', 'оппозиц', 'протест', 'митинг',
    'закон', 'законопроект', 'указ', 'постановлен', 'санкц', 'эмбарго',
    'украин', 'донбасс', 'лнр', 'днр', 'сво', 'nato', 'нато',
    'трамп', 'байден', 'си цзиньпин', 'европ', 'евросоюз', 'евразэс',
    'политик', 'дипломат', 'саммит', 'переговор', 'соглашен',
    'референдум', 'конституц', 'суверенитет', 'федерац', 'регион',
    'губернатор', 'мэр', 'администрац', 'власт', 'чиновник',
    'коррупц', 'дело', 'расследован', 'арест', 'обыск', 'возбужден'
}

HIGH_PRIORITY_KEYWORDS = {
    'путин', 'кремль', 'госдума', 'правительство', 'мид рф', 'украина',
    'санкции', 'сво', 'nato', 'нато', 'трамп', 'байден', 'выборы',
    'референдум', 'закон', 'указ', 'арест', 'протест'
}

# ================= ТРИГГЕРЫ ДЛЯ АВТОПОСТИНГА =================
# Пары ключевых слов с приоритетом (0-100) для определения критических новостей
URGENT_TRIGGERS = {
    # Военные действия и конфликты
    ('военн', 'операци', 100),
    ('начал', 'операци', 95),
    ('удар', 'ракет', 95),
    ('обстрел', 'город', 90),
    ('эскалаци', 'конфликт', 90),
    ('мобилизаци', 'объявлен', 95),
    ('перемири', 'прекращен', 85),
    
    # Критические заявления руководства
    ('путин', 'заявлен', 90),
    ('путин', 'подпис', 85),
    ('путин', 'встрет', 80),
    ('президент', 'обращен', 95),
    ('президент', 'заявлен', 85),
    ('экстрен', 'заявлен', 90),
    ('совет', 'безопасност', 85),
    
    # Международные отношения и санкции
    ('санкц', 'введен', 90),
    ('санкц', 'отмен', 85),
    ('разрыв', 'дипломатическ', 95),
    ('нато', 'размещен', 85),
    ('ядерн', 'угроз', 95),
    ('ядерн', 'оружи', 90),
    
    # Чрезвычайные ситуации
    ('теракт', 'совершен', 95),
    ('взрыв', 'произошел', 90),
    ('чрезвычайн', 'положен', 85),
    ('катастроф', 'погиб', 90),
    
    # Важные политические события
    ('выборы', 'результат', 85),
    ('голосован', 'итог', 80),
    ('отставк', 'министр', 85),
    ('отставк', 'губернатор', 85),
    ('назнач', 'министр', 80),
    ('арест', 'чиновник', 85),
    ('задержан', 'коррупц', 85),
}

NON_POLITICS_KEYWORDS = {
    'футбол', 'хоккей', 'баскетбол', 'олимпиад', 'чемпионат',
    'кино', 'фильм', 'сериал', 'актёр', 'режиссёр',
    'музык', 'концерт', 'альбом', 'певец', 'артист'
}


def lemmatize_text(text: str) -> str:
    """🇷🇺 Лемматизация через pymorphy3"""
    if not LEMMATIZATION_AVAILABLE or MORPHY is None:
        return text.lower()
    try:
        words = text.lower().split()
        lemmas = [MORPHY.parse(re.sub(r'[^\w\s]', '', w))[0].normal_form for w in words if w.strip()]
        return ' '.join(lemmas)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка лемматизации: {e}")
        return text.lower()


def lemmatize_keywords(keywords: set) -> set:
    """🇷🇺 Лемматизация keywords"""
    if not LEMMATIZATION_AVAILABLE or MORPHY is None:
        return {kw.lower() for kw in keywords}
    try:
        return {MORPHY.parse(kw)[0].normal_form for kw in keywords}
    except:
        return {kw.lower() for kw in keywords}


POLITICS_KEYWORDS_LEMMA = lemmatize_keywords(POLITICS_KEYWORDS)
HIGH_PRIORITY_KEYWORDS_LEMMA = lemmatize_keywords(HIGH_PRIORITY_KEYWORDS)

# ================= ЛОГИРОВАНИЕ =================
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_dir / "polit_bot.log", encoding="utf-8", delay=True),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logger = logging.getLogger(__name__)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# ================= МЕТРИКИ =================
class BotMetrics:
    """Расширенные метрики бота"""
    def __init__(self):
        self.metrics = {
            'posts_sent': 0,
            'posts_rejected': 0,
            'duplicates_exact': 0,
            'duplicates_fuzzy': 0,
            'duplicates_global': 0,
            'duplicates_content': 0,
            'llm_calls': 0,
            'llm_cache_hits': 0,
            'llm_errors': 0,
            'feeds_processed': 0,
            'candidates_found': 0,
            'fake_dates_blocked': 0,
            'english_words_blocked': 0,
            'errors': []
        }
        self.start_time = datetime.now()

    def log_duplicate(self, method: str):
        """Логирование дубликата + отправка в Prometheus"""
        if 'exact' in method:
            self.metrics['duplicates_exact'] += 1
            if prom_metrics:
                prom_metrics.inc_dup('exact')
        elif 'fuzzy' in method:
            self.metrics['duplicates_fuzzy'] += 1
            if prom_metrics:
                prom_metrics.inc_dup('fuzzy')
        elif 'global' in method:
            self.metrics['duplicates_global'] += 1
            if prom_metrics:
                prom_metrics.inc_dup('global')
        elif 'content' in method:
            self.metrics['duplicates_content'] += 1
            if prom_metrics:
                prom_metrics.inc_dup('content')

    def log_error(self, error: str):
        """Логирование ошибки + отправка в Prometheus"""
        self.metrics['errors'].append({
            'time': datetime.now().isoformat(),
            'error': str(error)[:200]
        })
        self.metrics['llm_errors'] += 1
        if prom_metrics:
            prom_metrics.inc_err()

    def log_post_sent(self, channel: str, post_type: str):
        """Логирование отправленного поста + отправка в Prometheus"""
        self.metrics['posts_sent'] += 1
        if prom_metrics:
            prom_metrics.inc_post(channel, post_type)

    def log_fake_date(self):
        """Логирование заблокированной фейковой даты"""
        self.metrics['fake_dates_blocked'] += 1
        if prom_metrics:
            prom_metrics.inc_date()

    def log_english_blocked(self):
        """Логирование заблокированного английского текста"""
        self.metrics['english_words_blocked'] += 1
        if prom_metrics:
            prom_metrics.inc_eng()

    def log_llm_cache_hit(self):
        """Логирование попадания в кэш LLM"""
        self.metrics['llm_cache_hits'] += 1
        if prom_metrics:
            prom_metrics.inc_cache()

    def log_llm_call(self, operation: str):
        """Логирование вызова LLM"""
        self.metrics['llm_calls'] += 1
        if prom_metrics:
            prom_metrics.inc_llm(operation)

    def print_summary(self):
        uptime = datetime.now() - self.start_time
        total_dup = (self.metrics['duplicates_exact'] +
                     self.metrics['duplicates_fuzzy'] +
                     self.metrics['duplicates_global'] +
                     self.metrics['duplicates_content'])
        cache_rate = 0
        if self.metrics['llm_calls'] > 0:
            cache_rate = (self.metrics['llm_cache_hits'] /
                          (self.metrics['llm_calls'] + self.metrics['llm_cache_hits'])) * 100
        logger.info("=" * 60)
        logger.info("📊 СТАТИСТИКА РАБОТЫ БОТА")
        logger.info(f"   Время работы: {uptime}")
        logger.info(f"   Постов отправлено: {self.metrics['posts_sent']}")
        logger.info(f"   Постов отклонено: {self.metrics['posts_rejected']}")
        logger.info(f"   Дубликатов всего: {total_dup}")
        logger.info(f"   ├─ Точных: {self.metrics['duplicates_exact']}")
        logger.info(f"   ├─ Fuzzy: {self.metrics['duplicates_fuzzy']}")
        logger.info(f"   ├─ Content: {self.metrics['duplicates_content']}")
        logger.info(f"   └─ Глобальных: {self.metrics['duplicates_global']}")
        logger.info(f"   LLM вызовов: {self.metrics['llm_calls']}")
        logger.info(f"   Cache hits: {self.metrics['llm_cache_hits']} ({cache_rate:.1f}%)")
        logger.info(f"   LLM ошибок: {self.metrics['llm_errors']}")
        logger.info(f"   Заблокировано дат: {self.metrics['fake_dates_blocked']}")
        logger.info(f"   Заблокировано англ.: {self.metrics['english_words_blocked']}")
        logger.info(f"   Фидов обработано: {self.metrics['feeds_processed']}")
        logger.info(f"   Кандидатов найдено: {self.metrics['candidates_found']}")
        logger.info("=" * 60)

metrics = BotMetrics()

# ================= PROMETHEUS =================
# 📊 ИСПОЛЬЗУЕМ УНИВЕРСАЛЬНЫЙ МОДУЛЬ ВМЕСТО ЛОКАЛЬНОГО КЛАССА
try:
    from prometheus_metrics import PrometheusMetrics
    prom_metrics = PrometheusMetrics(bot_name='politics', port=8000)
    logger.info("✅ Prometheus метрики запущены на порту 8000 (bot=politics)")
except Exception as e:
    logger.warning(f"⚠️ Prometheus metrics error: {e}")
    prom_metrics = None

# ================= СОСТОЯНИЕ =================
class BotState:
    def __init__(self):
        self.last_post_time = 0
        self.running = True
        self.current_task = None

state = BotState()

pending_dir = Path("pending_posts")
pending_dir.mkdir(exist_ok=True)

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posted (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE,
                hash TEXT NOT NULL,
                title_normalized TEXT,
                theme TEXT NOT NULL,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                duplicate_check_method TEXT
            )
        """)
        # ✅ Таблица для content dedup hash (быстрый поиск дублей по содержанию)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS content_dedup (
                content_hash TEXT PRIMARY KEY,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_dedup_time 
            ON content_dedup(posted_at)
        """)
        await db.commit()
    logger.info("✅ Локальная БД инициализирована")


async def cleanup_old_data():
    """🧹 Очистка старых данных
    ✅ ДОБАВЛЕНО: сжатие бэкапов БД через gzip для экономии места
    """
    try:
        # 1. Очистка БД (посты старше 30 дней)
        async with aiosqlite.connect(config.db_path) as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            cursor = await db.execute("DELETE FROM posted WHERE posted_at < ?", (cutoff,))
            deleted = cursor.rowcount
            await db.commit()
            if deleted > 0:
                logger.info(f"🧹 Удалено {deleted} старых записей из БД")

        # 2. Очистка кэша LLM (если >1000 записей)
        if hasattr(llm, 'cache') and len(llm.cache) > 1000:
            llm.cache = dict(list(llm.cache.items())[-500:])
            llm._save_cache()
            logger.info("🧹 Кэш LLM очищен")

        # 3. Очистка pending (черновики старше 7 дней)
        import os
        pending_dir = Path("pending_posts")
        if pending_dir.exists():
            for f in pending_dir.glob("*.json"):
                try:
                    mtime = f.stat().st_mtime
                    age_days = (datetime.now().timestamp() - mtime) / 86400
                    if age_days > 7:
                        f.unlink()
                        logger.info(f"🧹 Удалён старый черновик: {f.name}")
                except:
                    pass

        # 4. Бэкап БД ✅ СЖАТИЕ ЧЕРЕZ GZIP
        import shutil
        import gzip
        backup_dir = Path("db_backups")
        backup_dir.mkdir(exist_ok=True)
        db_path = Path(config.db_path)
        if db_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            backup_file = backup_dir / f"{db_path.stem}_{timestamp}.db"
            backup_gz_file = backup_dir / f"{db_path.stem}_{timestamp}.db.gz"
            
            # Копируем БД
            shutil.copy2(db_path, backup_file)
            
            # ✅ Сжимаем через gzip
            try:
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(backup_gz_file, 'wb', compresslevel=6) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Удаляем несжатую версию
                backup_file.unlink(missing_ok=True)
                
                # Логируем размер
                original_size = db_path.stat().st_size
                compressed_size = backup_gz_file.stat().st_size
                compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                logger.info(f"💾 Бэкап БД сжат: {backup_gz_file.name} ({compressed_size / 1024 / 1024:.2f} MB, экономия {compression_ratio:.1f}%)")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось сжать бэкап: {e}")
                # Оставляем несжатую версию если сжатие не удалось
                logger.info(f"💾 Бэкап БД: {backup_file.name}")

            # Удаляем бэкапы старше 7 дней (и .db и .gz)
            for old_backup in list(backup_dir.glob("*.db")) + list(backup_dir.glob("*.gz")):
                try:
                    mtime = old_backup.stat().st_mtime
                    age_days = (datetime.now().timestamp() - mtime) / 86400
                    if age_days > 7:
                        old_backup.unlink()
                        logger.info(f"🧹 Удалён старый бэкап: {old_backup.name}")
                except:
                    pass

    except Exception as e:
        logger.error(f"❌ Ошибка очистки: {e}")


async def cleanup_old_posts():
    async with aiosqlite.connect(config.db_path) as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        cursor = await db.execute("DELETE FROM posted WHERE posted_at < ?", (cutoff,))
        deleted = cursor.rowcount
        await db.commit()
        if deleted > 0:
            logger.info(f"🧹 Удалено {deleted} старых записей")

async def save_post(link: str, text_hash: str, source: str,
                    title_normalized: str = "", duplicate_method: str = "none"):
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO posted
            (link, hash, theme, source, title_normalized, duplicate_check_method)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (link, text_hash, "POLITICS", source, title_normalized, duplicate_method)
        )
        await db.commit()

async def save_content_dedup_hash(content_hash: str):
    """✅ Сохранить content dedup hash в локальную БД"""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO content_dedup (content_hash, posted_at) VALUES (?, CURRENT_TIMESTAMP)",
            (content_hash,)
        )
        await db.commit()

async def is_content_duplicate(content_hash: str, hours: int = 72) -> bool:
    """✅ Проверить content dedup hash в локальной БД"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            "SELECT 1 FROM content_dedup WHERE content_hash = ? AND posted_at > ?",
            (content_hash, cutoff)
        ) as cursor:
            return await cursor.fetchone() is not None


# ================= ОБРАБОТКА ТЕКСТА =================
def safe_to_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return '\n'.join(str(x) for x in value if x)
    return str(value).strip()

def clean_html(raw) -> str:
    raw = safe_to_string(raw)
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.select("script, style, noscript, iframe"):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = safe_to_string(text)
    return re.sub(r'\s+', ' ', text.strip())[:4500]

def get_content_hash(title: str, body: str) -> str:
    norm = (title.lower().strip() + body.lower().strip()[:400])
    return hashlib.sha256(norm.encode("utf-8", errors="ignore")).hexdigest()

def get_content_dedup_hash(title: str, body: str, category: str = "") -> str:
    """
    ✅ Создаёт хеш для дедупликации по содержанию.
    Использует глобальную нормализацию из global_dedup.py
    """
    # Импортируем глобальную функцию для консистентности
    from global_dedup import get_content_dedup_hash as global_hash
    return global_hash(title, body, category)

def normalize_title(title: str) -> str:
    title = re.sub(r'[^\w\s\-]', '', title.lower())
    stop_words = {'и', 'в', 'на', 'с', 'по', 'о', 'об', 'из', 'к', 'для', 'что', 'это'}
    words = [w for w in title.split() if w not in stop_words and len(w) > 2]
    return ' '.join(words)

def is_politics_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}") if LEMMATIZATION_AVAILABLE else text
    non_politics_count = sum(1 for word in NON_POLITICS_KEYWORDS if word in text)
    if non_politics_count >= 2:
        return False, 0, 0
    matches = sum(1 for kw in POLITICS_KEYWORDS_LEMMA if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)
    if matches == 0:
        matches = sum(1 for kw in POLITICS_KEYWORDS if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)
    return matches >= 1, matches, high_priority_matches


# ================= КЛАСТЕРИЗАЦИЯ НОВОСТЕЙ =================
def extract_key_entities(text: str) -> Dict[str, List[str]]:
    """
    🎯 Извлекает ключевые сущности из текста для кластеризации.
    Возвращает: {
        'persons': [...],      # Фамилии (Путин, Лавров, и т.д.)
        'organizations': [...], # Организации (Госдума, МИД, Кремль)
        'locations': [...],     # Локации (Москва, Донбасс, Украина)
        'events': [...]         # События (выборы, саммит, референдум)
    }
    """
    text_lower = text.lower()
    
    # 📋 Словари для извлечения сущностей
    PERSONS = {
        'путин', 'президент', 'медведев', 'лавров', 'песков', 'патрушев',
        'мишустин', 'матвиенко', 'володин', 'захарова', 'лукашенко',
        'трамп', 'байден', 'макрон', 'шольц', 'эрдоган', 'си цзиньпин',
        'зеленский', 'нетаньяху', 'ким чен ын', 'путин владимир',
        'губернатор', 'министр', 'депутат', 'сенатор', 'посол'
    }
    
    ORGANIZATIONS = {
        'госдум', 'совет федераци', 'правительств', 'кремль', 'минцифр',
        'минфин', 'минэконом', 'роскомнадзор', 'фсб', 'мвд', 'ск рф', 'прокуратур',
        'мид', 'сбербанк', 'газпром', 'роснефть', 'ростех', 'вэб.рф',
        'нато', 'оон', 'ес', 'евросоюз', 'снг', 'одец', 'брис',
        'партия', 'облдум', 'заксобр', 'администрац'
    }
    
    LOCATIONS = {
        'москв', 'петербург', 'крым', 'севастополь', 'донбасс', 'лнр', 'днр',
        'украин', 'киев', 'харьков', 'одесс', 'запорож', 'херсон',
        'сири', 'турци', 'кит', 'сша', 'америк', 'европ', 'германи', 'франци',
        'белорус', 'казахстан', 'узбекистан', 'сибир', 'дальн', 'урал',
        'регион', 'област', 'город', 'столиц'
    }
    
    EVENTS = {
        'выбор', 'голосован', 'референдум', 'саммит', 'переговор', 'встреч',
        'совещан', 'заявлен', 'подписан', 'указ', 'закон', 'санкц',
        'протест', 'митинг', 'конфликт', 'операци', 'обстрел', 'удар',
        'арест', 'отставк', 'назначен', 'отчёт', 'доклад'
    }
    
    entities = {
        'persons': [],
        'organizations': [],
        'locations': [],
        'events': []
    }
    
    # Извлекаем сущности
    for word in PERSONS:
        if word in text_lower:
            entities['persons'].append(word)
    
    for word in ORGANIZATIONS:
        if word in text_lower:
            entities['organizations'].append(word)
    
    for word in LOCATIONS:
        if word in text_lower:
            entities['locations'].append(word)
    
    for word in EVENTS:
        if word in text_lower:
            entities['events'].append(word)
    
    # Извлекаем имена собственные (заглавные буквы)
    proper_nouns = re.findall(r'[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]+)*', text)
    for noun in proper_nouns[:10]:  # Ограничиваем количество
        noun_lower = noun.lower()
        # Добавляем если это не шум
        if len(noun) >= 3 and noun_lower not in entities['persons']:
            # Проверяем, не является ли это началом предложения
            if not re.match(r'^(В|На|Под|Для|С|По|К|Об|О|Из|За|Через|После)\s', noun + ' '):
                entities['persons'].append(noun_lower)
    
    return entities


def calculate_news_similarity(news1: Dict, news2: Dict) -> float:
    """
    🔍 Рассчитывает схожесть двух новостей (0.0 - 1.0).
    Учитывает:
    - Fuzzy-схожесть заголовков (40%)
    - Пересечение ключевых сущностей (40%)
    - Временна́я близость (20%)
    """
    from difflib import SequenceMatcher
    
    title1 = news1.get('title', '')
    title2 = news2.get('title', '')
    summary1 = news1.get('summary', '')
    summary2 = news2.get('summary', '')
    pub_date1 = news1.get('pub_date')
    pub_date2 = news2.get('pub_date')
    
    # 1. Fuzzy-схожесть заголовков (0.0 - 1.0)
    title_similarity = SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
    
    # 2. Пересечение ключевых сущностей (0.0 - 1.0)
    entities1 = extract_key_entities(f"{title1} {summary1}")
    entities2 = extract_key_entities(f"{title2} {summary2}")
    
    entity_scores = []
    for key in ['persons', 'organizations', 'locations', 'events']:
        set1 = set(entities1.get(key, []))
        set2 = set(entities2.get(key, []))
        if set1 or set2:
            # Jaccard similarity
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            if union > 0:
                entity_scores.append(intersection / union)
    
    entity_similarity = sum(entity_scores) / len(entity_scores) if entity_scores else 0.0
    
    # 3. Временна́я близость (0.0 - 1.0)
    time_similarity = 0.5  # По умолчанию средняя
    if pub_date1 and pub_date2:
        time_diff_hours = abs((pub_date1 - pub_date2).total_seconds()) / 3600
        if time_diff_hours < 1:
            time_similarity = 1.0
        elif time_diff_hours < 3:
            time_similarity = 0.8
        elif time_diff_hours < 6:
            time_similarity = 0.6
        elif time_diff_hours < 12:
            time_similarity = 0.4
        elif time_diff_hours < 24:
            time_similarity = 0.2
        else:
            time_similarity = 0.0
    
    # Итоговая схожесть (взвешенная средняя)
    total_similarity = (
        title_similarity * 0.4 +
        entity_similarity * 0.4 +
        time_similarity * 0.2
    )
    
    return total_similarity


def cluster_news_candidates(candidates: List[Dict], threshold: float = 0.55) -> List[List[Dict]]:
    """
    🍇 Группирует новости в кластеры по смыслу.
    
    Args:
        candidates: Список кандидатов новостей
        threshold: Порог схожести для объединения в кластер (0.0 - 1.0)
    
    Returns:
        Список кластеров, где каждый кластер — список новостей
    """
    if not candidates:
        return []
    
    # Сортируем по приоритету (важные новости первыми)
    sorted_candidates = sorted(
        candidates,
        key=lambda x: (x.get('high_priority_matches', 0) * 5 + x.get('keyword_matches', 0) * 2),
        reverse=True
    )
    
    clusters = []  # [[news1, news2, ...], [news3, news4, ...], ...]
    
    for candidate in sorted_candidates:
        placed = False
        
        # Пытаемся найти подходящий кластер
        for cluster in clusters:
            # Проверяем схожесть с каждой новостью в кластере
            max_similarity_in_cluster = max(
                calculate_news_similarity(candidate, news)
                for news in cluster
            )
            
            if max_similarity_in_cluster >= threshold:
                cluster.append(candidate)
                placed = True
                break
        
        # Если не нашли кластер — создаём новый
        if not placed:
            clusters.append([candidate])
    
    # Логгируем результаты
    logger.info(f"🍇 Кластеризация: {len(candidates)} новостей → {len(clusters)} кластеров")
    for i, cluster in enumerate(clusters, 1):
        if len(cluster) > 1:
            logger.info(f"   Кластер #{i}: {len(cluster)} новостей")
            for news in cluster:
                logger.info(f"      • {news['title'][:50]}")
    
    return clusters


def merge_cluster_news(cluster: List[Dict]) -> Dict:
    """
    🔗 Объединяет новости из одного кластера в одну.

    Логика:
    1. Берём лучший заголовок (от приоритетного источника)
    2. Извлекаем уникальные факты из каждой новости
    3. Формируем единый текст с буллетами

    Returns:
        Объединённый кандидат
    """
    if not cluster:
        return None

    if len(cluster) == 1:
        # Если одна новость — возвращаем как есть
        news = cluster[0]
        return {
            **news,
            'is_merged': False,
            'merged_count': 1
        }

    # 1. Выбираем лучший заголовок (от приоритетного источника)
    priority_order = {
        'https://tass.ru/rss/v2.xml': 1,
        'https://ria.ru/export/rss2/archive/index.xml': 2,
        'https://www.interfax.ru/rss.asp': 3,
        'https://lenta.ru/rss/news': 4,
    }

    best_news = min(
        cluster,
        key=lambda x: priority_order.get(x.get('source', ''), 99)
    )

    # 2. Собираем все уникальные факты из summary
    all_facts = []
    seen_facts = set()

    for news in cluster:
        summary = news.get('summary', '')
        # Разбиваем на предложения
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        for sent in sentences:
            sent = sent.strip()
            # Нормализуем для проверки дубликатов
            sent_norm = re.sub(r'[^\w\s]', '', sent.lower())
            # Добавляем только уникальные факты
            if sent and len(sent) > 20 and sent_norm not in seen_facts:
                seen_facts.add(sent_norm)
                all_facts.append(sent)

    # 3. Формируем объединённый текст
    # Берём заголовок из лучшей новости
    merged_title = best_news['title']

    # Формируем тело из уникальных фактов (с буллетами)
    # Первые 1-2 предложения — основной текст, остальные — буллетами
    if len(all_facts) >= 3:
        # Первое предложение как основное
        main_text = all_facts[0]
        # Остальные — буллетами
        bullet_facts = []
        for fact in all_facts[1:8]:
            # Очищаем от лишних пробелов и переносов
            fact_clean = re.sub(r'\s+', ' ', fact).strip()
            if len(fact_clean) > 15:
                bullet_facts.append(f"• {fact_clean}")
        merged_body = main_text + '\n\n' + '\n'.join(bullet_facts)
    else:
        # Если мало фактов — просто объединяем
        merged_body = '\n\n'.join(all_facts[:6])

    # 4. Создаём объединённый кандидат
    merged = {
        'title': merged_title,
        'link': best_news['link'],
        'pub_date': best_news['pub_date'],
        'source': best_news['source'],
        'hash': best_news['hash'],
        'title_normalized': best_news['title_normalized'],
        'keyword_matches': max(n.get('keyword_matches', 0) for n in cluster),
        'high_priority_matches': max(n.get('high_priority_matches', 0) for n in cluster),
        'summary': merged_body,
        'is_merged': True,
        'merged_count': len(cluster),
        'cluster_sources': list(set(n.get('source', '') for n in cluster))
    }

    logger.info(f"🔗 Объединено {len(cluster)} новостей в одну: {merged_title[:50]}")

    return merged


def is_digest_headline(title: str) -> bool:
    """
    ✅ ФИЛЬТР ДАЙДЖЕСТОВ/СВОДОК.
    Отфильтровывает заголовки вида:
    - "Спецоперация, 28 февраля: ..."
    - "28 февраля: сводка событий"
    - "Хронология событий за 28 февраля"
    """
    # Паттерн: "Тема, DD месяца: ..." или "DD месяца: ..."
    digest_patterns = [
        r'^[а-яё]+,\s+\d{1,2}\s+[а-я]+\s*:',  # "Спецоперация, 28 февраля:"
        r'^\d{1,2}\s+[а-я]+[:\s]',  # "28 февраля:" или "28 февраля ..."
        r'сводк[аи]',  # "сводка", "сводке"
        r'дайджест',  # "дайджест"
        r'хронологи[яи]',  # "хронология"
        r'за\s+\d{1,2}\s+[а-я]+',  # "за 28 февраля"
    ]
    
    for pattern in digest_patterns:
        if re.search(pattern, title.lower()):
            return True
    
    return False


def has_video_reference(title: str, summary: str) -> bool:
    """
    ✅ ФИЛЬТР НОВОСТЕЙ ПРО ВИДЕО.
    Блокирует новости где упоминается видео, но у нас нет возможности его прикрепить.
    
    Блокируем если:
    - В заголовке есть слово "видео" или "видеозапись"
    - В описании есть явные паттерны типа "опубликовано видео", "появилось видео" и т.д.
    """
    # Проверяем заголовок на явное упоминание видео
    if 'видео' in title.lower() or 'видеозапись' in title.lower():
        return True
    
    # Проверяем описание на явные паттерны
    video_patterns = [
        r'опубликовано\s+видео',
        r'появилось\s+видео',
        r'выложили\s+видео',
        r'записали\s+видео',
        r'снимок\s+видео',
        r'видеозапись',
    ]
    
    summary_lower = summary.lower()
    
    for pattern in video_patterns:
        if re.search(pattern, summary_lower):
            return True
    
    return False


def calculate_priority(title: str, summary: str) -> Tuple[int, List[str]]:
    """
    Рассчитывает приоритет новости (0-100) и возвращает сработавшие триггеры.
    ✅ ДОБАВЛЕНО: поддержка комбинаций из 3 слов с повышенным приоритетом

    Returns:
        (priority, matched_triggers)
    """
    text = f"{title} {summary}".lower()

    max_priority = 0
    matched = []
    matched_triples = []

    # ✅ 1. ПРОВЕРКА ДВУХСЛОВНЫХ КОМБИНАЦИЙ (как раньше)
    for kw1, kw2, priority in URGENT_TRIGGERS:
        if kw1 in text and kw2 in text:
            if priority > max_priority:
                max_priority = priority
            matched.append(f"{kw1}+{kw2}")

    # ✅ 2. ПРОВЕРКА ТРЁХСЛОВНЫХ КОМБИНАЦИЙ (дополнительный бонус +10)
    # Особо важные комбинации из 3 слов
    urgent_triples = [
        # Военные действия
        ("начал", "военн", "операци"),
        ("нанес", "ракет", "удар"),
        ("объявлен", "воен", "положен"),
        ("прекращен", "огонь", "перемири"),
        ("подписан", "указ", "мобилизаци"),
        
        # Критические заявления
        ("путин", "подписал", "указ"),
        ("путин", "провел", "совещан"),
        ("президент", "обратился", "народ"),
        ("экстрен", "заявлен", "правительств"),
        
        # Международные отношения
        ("введен", "пакет", "санкц"),
        ("разорван", "дипломатическ", "отношен"),
        ("принят", "закон", "санкц"),
        
        # Чрезвычайные ситуации
        ("произошел", "теракт", "город"),
        ("объявлен", "чрезвычайн", "положен"),
        ("эвакуаци", "населен", "пункт"),
        
        # Экономика (если понадобится)
        ("обвал", "фондов", "рынок"),
        ("объявлен", "дефолт", "стран"),
        ("ключев", "ставка", "повышен"),
    ]
    
    for kw1, kw2, kw3 in urgent_triples:
        if kw1 in text and kw2 in text and kw3 in text:
            matched_triples.append(f"{kw1}+{kw2}+{kw3}")
            # Трёхсловные комбинации дают +10 к приоритету
            max_priority = min(100, max_priority + 10)

    # Бонус за свежесть (новости за последний час)
    if "только что" in text or "минут" in text or "сегодня" in text:
        max_priority = min(100, max_priority + 5)

    # Бонус за множественные совпадения
    total_matches = len(matched) + len(matched_triples)
    if total_matches >= 2:
        max_priority = min(100, max_priority + 5)
    if total_matches >= 4:
        max_priority = min(100, max_priority + 10)
    
    # ✅ Бонус за трёхсловные комбинации
    if matched_triples:
        logger.info(f"🔥 Найдены трёхсловные комбинации: {matched_triples}")
        max_priority = min(100, max_priority + 5)

    return max_priority, matched + matched_triples


def is_russian_text(text: str, min_ratio: float = 0.7) -> bool:
    if LANGDETECT_AVAILABLE:
        try:
            lang = detect(text[:500])
            return lang == "ru"
        except LangDetectException:
            pass
    cyrillic = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF or c in "ёЁ")
    alpha = sum(1 for c in text if c.isalpha())
    return alpha > 0 and (cyrillic / alpha) >= min_ratio

def translate_foreign_words(text: str) -> str:
    if not TRANSLATOR_AVAILABLE:
        return text
    try:
        pattern = r'\b([a-zA-Z]{3,})\b'

        def replace_word(match):
            word = match.group(1)
            # Пропускаем аббревиатуры и заглавные слова (имена, бренды, СМИ, компании)
            if word[0].isupper() or word.isupper():
                return word
            # Пропускаем изв����тные термины
            skip_words = {
                'nato', 'brics', 'swift', 'covid', 'opec', 'g7', 'g20',
                'usa', 'usd', 'eur', 'rub', 'gbp', 'jpy', 'cny',
                'gdp', 'ceo', 'ipo', 'api', 'ai', 'it', 'pr', 'hr',
                'un', 'eu', 'who', 'imf', 'wto'
            }
            if word.lower() in skip_words:
                return word
            try:
                translated = translator_en_ru.translate(word.lower())
                return translated
            except:
                return word

        return re.sub(pattern, replace_word, text)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка перевода: {e}")
        return text

def validate_html_tags(text: str) -> str:
    open_b = text.count('<b>')
    close_b = text.count('</b>')
    open_i = text.count('<i>')
    close_i = text.count('</i>')
    if open_b > close_b:
        text += '</b>' * (open_b - close_b)
    if open_i > close_i:
        text += '</i>' * (open_i - close_i)
    if close_b > open_b:
        for _ in range(close_b - open_b):
            text = text.replace('</b>', '', 1)
    if close_i > open_i:
        for _ in range(close_i - open_i):
            text = text.replace('</i>', '', 1)
    return text

def postprocess_text(raw) -> str:
    """Постобработка текста с правильными отступами"""
    CHANNEL = config.bot_signature

    if isinstance(raw, list):
        raw = '\n'.join(str(item) for item in raw if item)

    raw = safe_to_string(raw)
    if not raw or len(raw) < 20:
        return f"<b>Политическая новость</b>\n\n{CHANNEL}"

    raw = translate_foreign_words(raw)
    raw = re.sub(r'(Заголовок:|Первый абзац:|Второй абзац:|Третий абзац:)\s*', '', raw)

    header_match = re.search(r'\*\*(.+?)\*\*|\*(.+?)\*', raw)
    extracted_header = (
        header_match.group(1) if header_match and header_match.group(1)
        else (header_match.group(2) if header_match else None)
    )

    if header_match:
        raw = raw.replace(header_match.group(0), '', 1).strip()

    clean_text = re.sub(r'(\*\*|__|\\*|_|#|`|```|\[|\])', '', raw)
    clean_text = re.sub(r'[ \t]+', ' ', clean_text)
    clean_text = re.sub(r'\n\s*\n\s*\n+', '\n', clean_text)
    clean_text = clean_text.strip()

    if not clean_text or len(clean_text) < 20:
        return f"<b>Политическая новость</b>\n\n{CHANNEL}"

    sentences = re.split(r'(?<=[.!?])\s+', clean_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    noise_patterns = [
        r'политические новости',
        r'новости политики',
        r'подробност[иые]\s+(можно\s+)?найти',
        r'информаци[яю]\s+(можно\s+)?найти',
        r'читайте\s+(также|подробнее)',
        r'узнайте\s+больше',
        r'смотрите\s+по\s+ссылке',
        r'доступн[ао]\s+на\s+сайте',
        r'перейдите\s+по\s+ссылке',
        # ✅ Дни недели и даты — мета-комментарии
        r'^(суббота|воскресенье|понедельник|вторник|среда|четверг|пятница)\s*[–—:]\s+день',
        r'^(суббота|воскресенье|понедельник|вторник|среда|четверг|пятница)\s*,\s*когда',
        r'день,\s*когда\s+',
        # ✅ Мета-комментарии про публ����кацию
        r'опубликовал[оа][^\.]*информацию',
        r'сообщил[оа][^\.]*данные',
        r'представил[оа][^\.]*отчёт',
    ]

    def is_noise(sentence):
        s_lower = sentence.lower()
        return any(re.search(pattern, s_lower) for pattern in noise_patterns)

    sentences = [s for s in sentences if not is_noise(s)]

    if not sentences:
        return f"<b>Политическая новость</b>\n\n{CHANNEL}"

    # ✅ ИСПРАВЛЕНО: sentences вместо sentences[:120]
    if extracted_header and len(extracted_header) > 10:
        header = f"🏛️{extracted_header[:120]}🏛️"
        body_sentences = sentences
    else:
        header = f"🏛️{sentences[:120]}🏛️" if sentences else "🏛️Политическая новость🏛️"
        body_sentences = sentences[1:]

    if body_sentences:
        paragraphs = []
        temp_group = []
        for i, sent in enumerate(body_sentences):
            temp_group.append(sent)
            if len(temp_group) >= 2 or i == len(body_sentences) - 1:
                paragraphs.append(' '.join(temp_group))
                temp_group = []
            if len(paragraphs) >= 3:
                break
        # ✅ ИСПРАВЛЕНО: \n\n между абзацами
        body = "\n\n".join(paragraphs)
    else:
        body = ""

    # ✅ ИСПРАВЛЕНО: \n\n после заголовка
    if body and len(body) > 30:
        formatted = f"<b>{header}</b>\n\n{body}"
    else:
        formatted = f"<b>{header}</b>"

    # ✅ ИСПРАВЛЕНО: \n\n перед подписью
    formatted = formatted.rstrip() + f"\n\n{CHANNEL}"

    # 🔽 ЛИМИТЫ: с картинкой 1024, без картинки 4096
    # Оставляем запа�� 1000 символов для возможности добавления фото
    MAX_POST_LENGTH = 1000  # ← С запасом для фото
    TRUNCATE_LENGTH = 950
    MIN_TRUNCATE_SPACE = 600

    if len(formatted) > MAX_POST_LENGTH:
        temp_text = formatted.replace(f"\n\n{CHANNEL}", "")
        truncated = temp_text[:TRUNCATE_LENGTH]
        
        # 🔍 УМНАЯ ОБРЕЗКА: ищем конец после��него完整ного предложения
        last_period = truncated.rfind('.')
        if last_period > MIN_TRUNCATE_SPACE:
            final_body = truncated[:last_period + 1]
        else:
            last_space = truncated.rfind(' ')
            if last_space > MIN_TRUNCATE_SPACE:
                final_body = truncated[:last_space] + '...'
            else:
                final_body = truncated + '...'
        
        if final_body.count('<b>') > final_body.count('</b>'):
            final_body += '</b>'
        # ✅ ИСПРАВЛЕНО: \n\n перед подписью при обрезке
        formatted = final_body + f"\n\n{CHANNEL}"

    formatted = validate_html_tags(formatted)
    return formatted

# ================= ПРОВЕРКА ДУБЛИКАТОВ =================
class DuplicateDetector:
    """✅ Обёртка над универсальной функцией из global_dedup"""
    
    async def is_duplicate_advanced(
        self,
        title: str,
        summary: str,
        link: str,
        pub_date: Optional[datetime],
        db_path: str
    ) -> Tuple[bool, str]:
        """Вызывает универсальную функцию из global_dedup"""
        if not GLOBAL_DEDUP_ENABLED:
            return False, "unique"
        
        return await is_duplicate_advanced(
            title=title,
            summary=summary,
            link=link,
            local_db_path=db_path,
            category=config.category,
            duplicate_check_hours=config.duplicate_check_hours,
            global_enabled=True
        )

# ================= АДАПТ��ВНЫЙ RATE LIMITER =================
class AdaptiveRateLimiter:
    def __init__(self):
        self.request_times = []
        self.error_count = 0

    async def wait(self):
        now = asyncio.get_event_loop().time()
        self.request_times = [t for t in self.request_times if now - t < 60]
        if len(self.request_times) > 20:
            delay = 5 + (self.error_count * 2)
        elif config.is_night_time():
            delay = random.uniform(3, 6)
        else:
            delay = random.uniform(1.5, 3.5)
        await asyncio.sleep(delay)
        self.request_times.append(now)

    def report_error(self):
        self.error_count = min(self.error_count + 1, 10)

    def report_success(self):
        self.error_count = max(self.error_count - 1, 0)


class TelegramRateLimiter:
    """🛡️ Rate limiter для Telegram (защита от 429)"""
    def __init__(self):
        self.request_times = []
        self.last_429_time = 0
        self.cooldown = 60

    async def wait(self):
        now = asyncio.get_event_loop().time()
        if self.last_429_time and now - self.last_429_time < self.cooldown:
            wt = self.cooldown - (now - self.last_429_time)
            logger.warning(f"⏳ RL: {wt:.0f} сек после 429")
            await asyncio.sleep(wt)
            now = asyncio.get_event_loop().time()
        self.request_times = [t for t in self.request_times if now - t < 60]
        if len(self.request_times) >= 18:
            delay = 3.0 + (len(self.request_times) - 18) * 0.5
            await asyncio.sleep(delay)
        self.request_times.append(now)

    def report_429(self):
        self.last_429_time = asyncio.get_event_loop().time()
        self.request_times = []
        logger.warning("🚨 Telegram 429")

    def report_success(self):
        now = asyncio.get_event_loop().time()
        if self.last_429_time and now - self.last_429_time > 3600:
            self.last_429_time = 0

telegram_rate_limiter = TelegramRateLimiter()

# ================= LLM КЛИЕНТ =================
class CachedLLMClient:
    """LLM клиент с TTL-кэшированием (7 дней)"""
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.router_api_key,
            base_url="https://routerai.ru/api/v1"
        )
        self.rate_limiter = AdaptiveRateLimiter()
        self.circuit_breaker_fails = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_open_until = 0
        self.cache_file = Path("llm_cache_pol.pkl")
        self.cache_ttl_days = 7
        self.cache = self._load_cache()
        self._cleanup_old_cache()

    def _load_cache(self) -> Dict:
        """Загружает кэш из файла. Формат: {key: {'result': str, 'timestamp': float}}"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    cache = pickle.load(f)
                logger.info(f"💾 Загружен кэш: {len(cache)} записей")
                return cache
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки кэша: {e}")
        return {}

    def _save_cache(self):
        """Сохраняет кэш в файл"""
        try:
            if len(self.cache) > 2000:
                self.cache = dict(list(self.cache.items())[-1000:])
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка сохранения кэша: {e}")

    def _cleanup_old_cache(self):
        """Удаляет записи старше TTL (7 дней)"""
        if not self.cache:
            return
        
        cutoff_time = time.time() - (self.cache_ttl_days * 86400)
        old_keys = []
        
        for key, value in self.cache.items():
            # Поддерживаем старый формат (просто строка) и новый (dict с timestamp)
            if isinstance(value, dict):
                timestamp = value.get('timestamp', 0)
                if timestamp < cutoff_time:
                    old_keys.append(key)
            else:
                # Старый формат — считаем что запись старая и удаляем
                old_keys.append(key)
        
        for key in old_keys:
            del self.cache[key]
        
        if old_keys:
            logger.info(f"🧹 Очищено {len(old_keys)} устаревших записей кэша (> {self.cache_ttl_days} дней)")
            self._save_cache()

    def _get_cache_key(self, title: str, summary: str, operation: str) -> str:
        text = f"{operation}:{title[:100]}:{summary[:200]}"
        return hashlib.sha256(text.encode()).hexdigest()

    async def _circuit_breaker_check(self):
        now = asyncio.get_event_loop().time()
        if self.circuit_breaker_fails >= self.circuit_breaker_threshold:
            if now < self.circuit_breaker_open_until:
                wait_time = int(self.circuit_breaker_open_until - now)
                logger.warning(f"⚠️ Circuit breaker открыт (осталось {wait_time} сек)")
                raise Exception("Circuit breaker is open")
            else:
                logger.info("🔄 Circuit breaker: попытка восстановления")
                self.circuit_breaker_fails = 0

    def _extract_content_from_response(self, response) -> Optional[str]:
        try:
            if hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
                if hasattr(choice, 'message'):
                    msg = choice.message
                    content = None
                    if hasattr(msg, 'content'):
                        content = msg.content
                    if content is None and hasattr(msg, '__dict__'):
                        content = msg.__dict__.get('content')
                    if content is not None:
                        if isinstance(content, list):
                            content = '\n'.join(str(i) for i in content if i)
                        content = str(content).strip()
                        if content:
                            return content

            if hasattr(response, 'model_dump'):
                try:
                    data = response.model_dump()
                    choices = data.get('choices', [])
                    if choices:
                        msg = choices[0].get('message', {}) or {}
                        content = msg.get('content', '')
                        if isinstance(content, list):
                            content = '\n'.join(str(i) for i in content if i)
                        if content and str(content).strip():
                            return str(content).strip()
                except Exception:
                    pass

            logger.warning(
                f"⚠️ Не удалось извлечь контент. "
                f"Тип: {type(response).__name__}, "
                f"dump: {str(response.model_dump() if hasattr(response, 'model_dump') else repr(response))[:400]}"
            )
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения контента: {e}")
            return None

    def _contains_fake_dates(self, text: str) -> bool:
        """
        ✅ Проверка на выдуманные даты — ТОЛЬКО явные фейки событий.
        Разрешает легитимные упоминания: "уровней 2024 года", "в 2025 году ожидается"
        Блокирует: "28 февраля 2024 года произошло", "в 2023 году начал" (конкретные события)
        """
        text_lower = text.lower()
        
        # ✅ Блокируем ТОЛЬКО конкретные даты событий (день + месяц + год или год в контексте события)
        fake_event_patterns = [
            # Конкретная дата + год + событие: "28 февраля 2024 года начал", "15 марта 2025 произошел"
            r'\d{1,2}\s+(?:янв|февр|мар|апр|ма|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+(?:2023|2024|2025)\s*(?:года|г\.?)?\s*[,.]?\s*(?:начал|произош|удар|обстрел|убил|взорвал|подписал|объявил)',
            # Год + событие в прошедшем времени: "в 2024 году начал", "2023 году произошел"
            r'(?:в\s+)?(?:2023|2024|2025)\s*году\s+(?:начал|произош|удар|обстрел|убил|взорвал|подписал|объявил|случил)',
            # Событие + дату: "начал операцию 28 февраля 2024", "произошел взрыв 15 марта 2025"
            r'(?:начал|произош|удар|обстрел|убил|взорвал)[а-я]*\s+(?:в\s+)?(?:2023|2024|2025)\s*(?:году|год)?',
        ]
        
        for pattern in fake_event_patterns:
            if re.search(pattern, text_lower):
                logger.warning(f"🚨 Обнаружена выдуманная дата события: {text[:100]}")
                metrics.log_fake_date()
                return True
        
        return False

    def _contains_too_much_english(self, text: str) -> bool:
        allowed_english = {
            # Организации и страны
            'usa', 'nato', 'un', 'eu', 'cnn', 'bbc', 'fbi', 'cia',
            'trump', 'biden', 'putin', 'g7', 'g20', 'brexit',
            'covid', 'who', 'brics', 'swift', 'opec',
            # ✅ Географические названия
            'dubai', 'dxb', 'dwc', 'tehran', 'iran', 'israel',
            'telaviv', 'jerusalem', 'kiev', 'minsk', 'moscow',
            'washington', 'london', 'berlin', 'paris', 'beijing',
            'sharm', 'elsheikh', 'egypt', 'qatar', 'doha',
            # ✅ Отраслевые термины
            'airports', 'airport', 'flight', 'flights',
            'oil', 'gas', 'military', 'army', 'defense',
            # ✅ Имена собственные (спорт, политики)
            'usik', 'wbc', 'ring', 'magazine', 'mma', 'ufc',
            'zelensky', 'netanyahu', 'lavrov', 'katar',
        }
        english_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        suspicious = [w for w in english_words if w not in allowed_english]
        if len(suspicious) > 5:  # ✅ Увеличили порог с 3 до 5
            logger.warning(f"🚨 Много английских слов: {suspicious[:5]}")
            metrics.log_english_blocked()
            return True
        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            f"⚠️ LLM classify: попытка {retry_state.attempt_number}/3, "
            f"ожидание {retry_state.next_action.sleep:.1f} сек"
        )
    )
    async def classify(self, title: str, summary: str) -> Optional[str]:
        cache_key = self._get_cache_key(title, summary, "classify")
        if cache_key in self.cache:
            cached_value = self.cache[cache_key]
            # Поддерживаем старый формат (строка) и новый (dict)
            if isinstance(cached_value, dict):
                result = cached_value.get('result')
            else:
                result = cached_value
            if result:
                logger.info("💾 Cache hit: classify")
                metrics.log_llm_cache_hit()
                return result

        await self._circuit_breaker_check()
        await self.rate_limiter.wait()
        metrics.log_llm_call('classify')

        prompt = (
            "Классифицируй новость. Ответь: POLITICS или NONE.\n"
            "POLITICS = власть/выборы/дипломатия/конфликты/чиновники\n"
            "NONE = спорт/кино/музыка\n"
            f"Заголов��к: {title}\nТекст: {summary[:200]}"  # ← 200 вместо 500
        )

        try:
            response = await self.client.chat.completions.create(
                model=config.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.15,
                max_tokens=200,  # ✅ Увеличено с 100 до 200 чтобы не обрезалось
                timeout=20.0
            )
            content = self._extract_content_from_response(response)
            if not content:
                return None

            result = "POLITICS" if "POLITICS" in content.upper() else None
            # Сохраняем в новом формате с timestamp
            self.cache[cache_key] = {'result': result, 'timestamp': time.time()}
            if len(self.cache) % 10 == 0:
                self._save_cache()
            self.rate_limiter.report_success()
            self.circuit_breaker_fails = max(0, self.circuit_breaker_fails - 1)
            return result

        except Exception as e:
            logger.warning(f"⚠️ LLM classify error: {str(e)[:100]}")
            metrics.log_error(f"classify: {e}")
            self.rate_limiter.report_error()
            self.circuit_breaker_fails += 1
            if self.circuit_breaker_fails >= self.circuit_breaker_threshold:
                self.circuit_breaker_open_until = asyncio.get_event_loop().time() + 60
            await asyncio.sleep(random.uniform(2, 4))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            f"⚠️ LLM rewrite: попытка {retry_state.attempt_number}/3, "
            f"ожидание {retry_state.next_action.sleep:.1f} сек"
        )
    )
    async def rewrite(self, title: str, body: str) -> Optional[str]:
        cache_key = self._get_cache_key(title, body, "rewrite")
        if cache_key in self.cache:
            cached_value = self.cache[cache_key]
            # Поддерживаем старый формат (строка) и новый (dict)
            if isinstance(cached_value, dict):
                result = cached_value.get('result')
            else:
                result = cached_value
            if result:
                logger.info("💾 Cache hit: rewrite")
                metrics.log_llm_cache_hit()
                return result

        await self._circuit_breaker_check()
        await self.rate_limiter.wait()
        metrics.log_llm_call('rewrite')

        current_date = datetime.now().strftime('%d.%m.%Y')
        current_year = datetime.now().year

        prompt = (
            "Ты — редактор политического Telegram-канала. Перепиши новость в информативном стиле.\n"
            "СТРОГИЕ ПРАВИЛА ФОРМАТИРОВАН����Я:\n"
            "1. Первое предложение — заголовок в **двойных звёздочках**: **Заголовок здесь**\n"
            "2. После заголовка — пустая строка, затем 2-3 абзаца по 2-3 предложения\n"
            "3. Между абзацами — пу����тая строка\n"
            "ПРАВИЛА СОДЕРЖАНИЯ:\n"
            "4. Только русский язык (кроме: NATO, USA, EU, FBI, CIA, названия компаний)\n"
            "5. Конкретно и по делу, без воды\n"
            "6. Максимум 700 ��имволов\n"            "5. **СОХРАНЯЙ оригинальные ��азва����ия компаний** (AZUR air, Boeing, Wagner Group)\n"
            "7. НЕ добавляй: \"Заголовок:\", \"Первый абзац:\", \"читайте также\"\n"
            "ЗАПРЕТ НА ДАТЫ:\n"
            "8. ❌ НЕ выдумывай даты и числа\n"
            "9. ❌ НЕ указывай 2023, 2024, 2025\n"
            f"10. Текущая дата: {current_date}, год: {current_year}\n\n"
            f"Заголовок: {title}\n"
            f"Текст: {body[:2000]}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=config.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3500,  # ✅ Увеличено с 2000 до 3500 чтобы не обрезалось
                timeout=45.0
            )
            result = self._extract_content_from_response(response)

            if not result or len(result) < 50:
                logger.warning(f"⚠️ Рерайт слишком короткий: {len(result) if result else 0} символов")
                return None

            # Исправляем одинарные звёздочки на двойные
            if not re.search(r'\*\*(.+?)\*\*', result):
                if re.search(r'\*(.+?)\*', result):
                    result = re.sub(r'^\*(.+?)\*', r'**\1**', result)
                    logger.info("✓ Исправлены одинарные звёздочки на двойные")

            if self._contains_fake_dates(result):
                logger.warning("⚠️ Рерайт содержит выдуманные даты, отклонён")
                return None

            if self._contains_too_much_english(result):
                logger.warning("⚠️ Рерайт содержит слишком много английских слов")
                return None

            # Сохраняем в новом формате с timestamp
            self.cache[cache_key] = {'result': result, 'timestamp': time.time()}
            if len(self.cache) % 10 == 0:
                self._save_cache()
            self.rate_limiter.report_success()
            self.circuit_breaker_fails = max(0, self.circuit_breaker_fails - 1)
            return result

        except Exception as e:
            logger.warning(f"⚠️ LLM rewrite error: {str(e)[:100]}")
            metrics.log_error(f"rewrite: {e}")
            self.rate_limiter.report_error()
            self.circuit_breaker_fails += 1
            if self.circuit_breaker_fails >= self.circuit_breaker_threshold:
                self.circuit_breaker_open_until = asyncio.get_event_loop().time() + 60
            await asyncio.sleep(random.uniform(2, 4))
            return None

# ================= Fuzzy ДЕДУПЛИКАЦИЯ =================
def is_fuzzy_duplicate(title: str, hours: int = 24) -> bool:
    """
    🔍 Fuzzy проверка дубликатов по заголовку (85%+ схожесть)
    """
    from difflib import SequenceMatcher
    import aiosqlite

    title_norm = normalize_title(title)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    with aiosqlite.connect(config.db_path) as db:
        cursor = db.execute(
            """SELECT title_normalized FROM posted
               WHERE posted_at > ? AND title_normalized IS NOT NULL
               ORDER BY posted_at DESC LIMIT 200""",
            (cutoff,)
        )
        recent_posts = cursor.fetchall()
        cursor.close()

        for post in recent_posts:
            stored = post[0] if isinstance(post, tuple) else post
            if not stored:
                continue
            similarity = SequenceMatcher(None, title_norm.lower(), stored.lower()).ratio()
            if similarity >= 0.85:
                return True
    return False

# ================= ОБРАБОТКА RSS =================
# Кэш RSS фидов (TTL = 5 минут)
RSS_CACHE_DIR = Path("rss_cache")
RSS_CACHE_TTL = 300  # 5 минут в секундах

def get_cache_path(feed_url: str) -> Path:
    """Возвращает пу��ь к файлу кэша для URL"""
    RSS_CACHE_DIR.mkdir(exist_ok=True)
    cache_key = hashlib.md5(feed_url.encode()).hexdigest()
    return RSS_CACHE_DIR / f"{cache_key}.cache"

async def get_cached_feed(feed_url: str) -> Optional[bytes]:
    """Получает RSS из кэша если он свежий (< 5 минут)"""
    try:
        cache_path = get_cache_path(feed_url)
        if cache_path.exists():
            stat = cache_path.stat()
            age = time.time() - stat.st_mtime
            if age < RSS_CACHE_TTL:
                async with aiofiles.open(cache_path, 'rb') as f:
                    data = await f.read()
                logger.debug(f"💾 RSS кэш hit: {feed_url[:40]} (возраст: {age:.0f} сек)")
                return data
            else:
                logger.debug(f"🕒 RSS кэш устарел: {feed_url[:40]} (возраст: {age:.0f} сек)")
    except Exception as e:
        logger.debug(f"⚠️ Ошибка чтения кэша RSS: {e}")
    return None

async def save_cached_feed(feed_url: str, data: bytes):
    """Сохраняет RSS в кэш"""
    try:
        cache_path = get_cache_path(feed_url)
        temp_path = cache_path.with_suffix(".tmp")
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(data)
        os.replace(temp_path, cache_path)
        logger.debug(f"💾 RSS кэш save: {feed_url[:40]}")
    except Exception as e:
        logger.debug(f"⚠️ Ошибка записи кэша RSS: {e}")


async def fetch_article_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return ""
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup.select("script, style, noscript, iframe, aside, footer, header, nav"):
                tag.decompose()
            selectors = [
                "article.article", "div.article__body", "div.article-body",
                "div.article__text", "div.article-text", "div.article-content",
                "div.entry-content", "div.post-content"
            ]
            for selector in selectors:
                block = soup.select_one(selector)
                if block:
                    paragraphs = []
                    for p in block.find_all("p"):
                        text = safe_to_string(p.get_text(strip=True))
                        if len(text) > 20:
                            paragraphs.append(text)
                    if len(paragraphs) >= 2:
                        return " ".join(paragraphs[:12])
            paragraphs = []
            for p in soup.find_all("p"):
                text = safe_to_string(p.get_text(strip=True))
                if len(text) > 50:
                    paragraphs.append(text)
            if len(paragraphs) >= 3:
                return " ".join(paragraphs[:15])
            return clean_html(soup.get_text())
    except Exception as e:
        logger.debug(f"Error fetching {url[:60]}: {str(e)[:80]}")
        return ""


async def process_feed(
    session: aiohttp.ClientSession,
    feed_url: str,
    llm: CachedLLMClient,
    duplicate_detector: DuplicateDetector
) -> List[Dict]:
    candidates = []

    try:
        # Проверяем кэш перед HTTP запросом
        content = await get_cached_feed(feed_url)
        
        if content is None:
            # Кэша нет или устарел — делаем HTTP запрос
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*'
            }
            async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status != 200:
                    logger.warning(f"❌ {feed_url[:50]} HTTP {resp.status}")
                    return candidates

                content = await resp.read()
                # Сохраняем в кэш
                await save_cached_feed(feed_url, content)
        
        feed = feedparser.parse(content)

        if not feed.entries:
            logger.warning(f"⚠️ {feed_url[:50]} — нет записей")
            return candidates

        metrics.metrics['feeds_processed'] += 1
        logger.info(f"✅ {feed_url[:50]}: {len(feed.entries)} записей")

        for entry in feed.entries[:config.max_entries_per_feed]:
            link = safe_to_string(getattr(entry, "link", "")).strip()
            title = clean_html(safe_to_string(getattr(entry, "title", "")))
            summary = clean_html(safe_to_string(
                getattr(entry, "summary", "") or getattr(entry, "description", "")
            ))

            if not link or not title or len(title) < 10:
                continue

            pub_date = None
            for attr in ["published_parsed", "updated_parsed", "created_parsed"]:
                val = getattr(entry, attr, None)
                if val:
                    try:
                        pub_date = datetime(*val[:6], tzinfo=timezone.utc)
                        break
                    except:
                        pass
            if not pub_date:
                pub_date = datetime.now(timezone.utc)

            age_hours = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
            if age_hours > config.max_news_age_hours:
                continue

            # ✅ СЛОЙ 1: Проверка локальной дедупликации
            is_dup, dup_method = await duplicate_detector.is_duplicate_advanced(
                title, summary, link, pub_date, config.db_path
            )
            if is_dup:
                metrics.log_duplicate(dup_method)
                continue

            # ✅ СЛОЙ 1.5: ПРОВЕРКА НА ОЧЕНЬ СВЕЖИЕ ПУБЛИКАЦИИ (urgent_news.py)
            # Предотвращает дублирование с urgent_news.py который постит сразу в канал
            if GLOBAL_DEDUP_ENABLED:
                try:
                    from global_dedup import is_similar_recent_news
                    # Проверяем за последние 5 минут — если urgent_news только что запостил
                    if await is_similar_recent_news(title, config.category, hours=0.08, threshold=0.70):
                        logger.info(f"🔄 ОТКЛОНЁН: urgent_news только что опубликовал (5 мин): {title[:60]}")
                        metrics.log_duplicate("global_urgent_conflict")
                        continue
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка проверки urgent-конфликта: {e}")

            is_suitable, keyword_matches, high_priority_matches = is_politics_candidate(title, summary)
            if not is_suitable:
                logger.debug(f"⏭️ Не политика: {title[:50]}")
                if prom_metrics:
                    prom_metrics.inc_rejected('not_politics')
                continue

            # ✅ ФИЛЬТР ДАЙДЖЕСТОВ/СВОДОК
            if is_digest_headline(title):
                logger.info(f"⏭️ Дайджест/сводка: {title[:60]}")
                if prom_metrics:
                    prom_metrics.inc_rejected('digest')
                continue

            # ✅ ФИЛЬТР НОВОСТЕЙ ПРО ВИДЕО
            if has_video_reference(title, summary):
                logger.info(f"⏭️ Видео-новость (без видео): {title[:60]}")
                if prom_metrics:
                    prom_metrics.inc_rejected('no_video')
                continue

            logger.info(f"✓ Ключевые слова ({keyword_matches}, HOT:{high_priority_matches}): {title[:60]}")

            # ✅ ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА НА ДУБЛИКАТЫ ДЛЯ HOT-ПОСТОВ
            # Если пост HOT (много ключевых слов), проверяем строже
            if high_priority_matches >= 1 or keyword_matches >= 2:
                # Проверяем через global_dedup расширенную проверку
                if GLOBAL_DEDUP_ENABLED:
                    try:
                        from global_dedup import is_similar_recent_news_extended
                        if await is_similar_recent_news_extended(title, config.category, hours=72, threshold=0.65):
                            logger.info(f"🔄 HOT-дубликат (extended): {title[:60]}")
                            metrics.log_duplicate("global_extended")
                            continue
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка extended проверки HOT: {e}")
                logger.info(f"⚡ Автоодобрено (HOT/2+ ключ.слова): {title[:60]}")
            else:
                logger.info(f"🔍 LLM проверка: {title[:60]}")
                classification = await llm.classify(title, summary)
                if classification != "POLITICS":
                    logger.info(f"⏭️ LLM отклонил: {title[:60]}")
                    metrics.metrics['posts_rejected'] += 1
                    if prom_metrics:
                        prom_metrics.inc_rejected('low_priority')
                    continue
                logger.info(f"✅ LLM одобрил: {title[:60]}")

            # ✅ БЕЗ fetch и БЕЗ рерайта — просто сохраняем кандидата
            content_hash = get_content_hash(title, summary)
            title_norm = normalize_title(title)

            candidates.append({
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "source": feed_url,
                "hash": content_hash,
                "title_normalized": title_norm,
                "keyword_matches": keyword_matches,
                "high_priority_matches": high_priority_matches,
                "summary": summary,
            })

            metrics.metrics['candidates_found'] += 1
            if prom_metrics:
                prom_metrics.set_candidates(len(candidates) + 1)
            logger.info(f"✨ КАНДИДАТ #{metrics.metrics['candidates_found']}: {title[:60]}")

            if len(candidates) >= 5:
                break

        # ✅ УБРАНА ЗАДЕРЖКА для ускорения

    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Таймаут {feed_url[:50]}")
    except Exception as e:
        logger.error(f"❌ {feed_url[:50]}: {e}")

    return candidates

async def collect_candidates(llm: CachedLLMClient, duplicate_detector: DuplicateDetector) -> List[Dict]:
    # Сортируем фиды по приоритету (высокий приоритет первым)
    feeds = sorted(
        RSS_FEEDS.copy(),
        key=lambda x: RSS_FEEDS_PRIORITY.get(x, 5),
        reverse=True
    )
    logger.info(f"🔄 Начинаем загрузку {len(feeds)} фидов (по приоритету)...")
    for i, feed in enumerate(feeds):
        priority = RSS_FEEDS_PRIORITY.get(feed, 5)
        logger.debug(f"   {i+1}. {feed[:40]} (приоритет: {priority})")

    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, force_close=False)  # ⚡ Больше соединений
    timeout = aiohttp.ClientTimeout(total=20, connect=5, sock_read=10)  # ⚡ Ускорено

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [process_feed(session, feed, llm, duplicate_detector) for feed in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates = []
        for result in results:
            if isinstance(result, list):
                all_candidates.extend(result)

        # ✅ ИСПРАВЛЕНО: фильтр — только словари
        all_candidates = [c for c in all_candidates if isinstance(c, dict)]

        # ✅ Фильтр: только словари
        all_candidates = [c for c in all_candidates if isinstance(c, dict)]

        # 🎯 ВНУТРЕННИЙ РЕЙТИНГ
        for c in all_candidates:
            age_hours = (datetime.now(timezone.utc) - c["pub_date"]).total_seconds() / 3600
            freshness_bonus = 5 if age_hours < 2 else (3 if age_hours < 4 else 1)
            
            c["rating"] = (
                c.get("high_priority_matches", 0) * 5 +
                c.get("keyword_matches", 0) * 2 +
                freshness_bonus
            )
            logger.info(f"✓ Рейтинг {c['rating']}: {c['title'][:60]}")
        
        all_candidates.sort(key=lambda x: x.get("rating", 0), reverse=True)

        logger.info(f"📊 Обработано фидов: {metrics.metrics['feeds_processed']}/{len(feeds)}")
        logger.info(f"📊 Найдено кандидатов: {len(all_candidates)}")

        return all_candidates[:config.max_candidates]

# ================= ОТПРАВКА В TELEGRAM =================
async def send_to_channel(
    session: aiohttp.ClientSession,
    text: str,
    link: str,
    priority: int = 0,
    triggers: List[str] = None
) -> bool:
    """
    🔥 ОТПРАВКА СРАЗУ В КАНАЛ (минуя предложку)
    Для критических новостей с priority >= 95
    ✅ Переиспользует сессию из основного цикла
    """
    text = safe_to_string(text)
    text = validate_html_tags(text)

    if not text or len(text) < 50:
        logger.error("❌ Текст слишком короткий для автопостинга")
        return False

    bold_count = text.count('<b>')
    if bold_count > 1:
        logger.error(f"❌ Обнаружено {bold_count} жирных заголовков вместо 1")
        return False

    if not is_russian_text(text, min_ratio=0.70):
        logger.critical("❌ Текст не на русском языке!")
        return False

    try:
        # 📝 Отправляем только текст
        url = f"https://api.telegram.org/bot{config.tg_token}/sendMessage"
        payload = {
            "chat_id": config.tg_channel,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        async with session.post(url, json=payload) as response:
            result = await response.json()
            if result.get("ok"):
                metrics.log_post_sent(config.category, 'autopost')
                trigger_info = f" ({', '.join(triggers)})" if triggers else ""
                logger.info(f"🚨 АВТОПОСТ ОПУБЛИКОВАН (priority={priority}{trigger_info})")
                return True
            else:
                logger.error(f"❌ Ошибка Telegram: {result.get('description')}")
                return False

    except asyncio.TimeoutError:
        logger.error("❌ Таймаут при отправке в Telegram (60 сек)")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        metrics.log_error(f"send_to_channel: {e}")
        return False


async def send_to_suggestion(
    session: aiohttp.ClientSession,
    text: str,
    link: str,
    pub_date: Optional[datetime],
    original_title: str = ""
) -> bool:
    text = safe_to_string(text)
    text = validate_html_tags(text)

    if not text or len(text) < 50:
        logger.error("❌ Текст слишком короткий")
        return False

    bold_count = text.count('<b>')
    if bold_count > 1:
        logger.error(f"❌ Обнаружено {bold_count} жирных заголовков вместо 1")
        return False

    noise_patterns = [
        r'подробност[иые]\s+(можно\s+)?найти',
        r'информаци[яю]\s+(можно\s+)?найти',
        r'читайте\s+(также|подробнее)',
        r'узнайте\s+больше'
    ]
    text_lower = text.lower()
    for pattern in noise_patterns:
        if re.search(pattern, text_lower):
            logger.error(f"❌ Обнаружен мета-комментарий: {pattern}")
            return False

    if not is_russian_text(text, min_ratio=0.70):
        logger.critical("❌ Текст не на русском языке!")
        return False

    post_id = hashlib.md5(text[:200].encode("utf-8")).hexdigest()[:16]
    draft_path = pending_dir / f"{post_id}.json"

    draft_data = {
        "text": text,
        "link": link,
        "channel_id": config.tg_channel,
        "suggestion_chat_id": config.suggestion_chat_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "post_id": post_id,
        "status": "pending",
    }

    await write_draft_atomic(draft_path, draft_data)

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Опубликовать", "callback_data": f"publish_{config.tg_channel}_{post_id}"},
            {"text": "✏️ Редактировать", "callback_data": f"edit_{post_id}"},
            {"text": "❌ Отклонить", "callback_data": f"reject_{post_id}"}
        ]]
    }

    caption = text[:4090] if len(text) > 4090 else text
    payload = {
        "chat_id": config.suggestion_chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
        "disable_web_page_preview": False
    }
    url = f"https://api.telegram.org/bot{config.tg_token}/sendMessage"
    try:
        async with session.post(url, json=payload) as response:
            result = await response.json()
            if result.get("ok"):
                metrics.log_post_sent('politics', 'manual')
                logger.info(f"✅ Пост отправлен в предложку (ID: {post_id})")
            else:
                logger.error(f"❌ Ошибка Telegram: {result.get('description')}")
                return False
    except asyncio.TimeoutError:
        logger.error("❌ Таймаут при отправке в Telegram (60 сек)")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        metrics.log_error(f"send_to_suggestion: {e}")
        return False

    # ✅ Глобальная дедупликация по оригинальному заголовку
    if GLOBAL_DEDUP_ENABLED:
        try:
            title_for_hash = original_title if original_title else text[:100]
            content_hash = get_universal_hash(title_for_hash, link, pub_date, config.category)
            await mark_global_posted(
                content_hash,
                config.tg_channel,
                config.category,
                title_for_hash[:100],
                config.category
            )
        except Exception as e:
            logger.warning(f"⚠️ Ошибка отметки в глобальной БД: {e}")

    return True

async def send_to_suggestion_with_retry(
    session: aiohttp.ClientSession,
    text: str,
    link: str,
    pub_date: Optional[datetime],
    original_title: str = "",
    max_retries: int = 3
) -> bool:
    for attempt in range(1, max_retries + 1):
        logger.info(f"📤 Попытка отправки {attempt}/{max_retries}")
        result = await send_to_suggestion(session, text, link, pub_date, original_title)
        if result:
            return True
        if attempt < max_retries:
            wait_time = attempt * 5
            logger.warning(f"⏳ Ожидание {wait_time} сек перед повтором...")
            await asyncio.sleep(wait_time)
    return False

# ================= ОСНОВНОЙ ЦИКЛ =================
async def collect_and_process_news(
    llm: CachedLLMClient,
    duplicate_detector: DuplicateDetector,
    session: aiohttp.ClientSession
):
    start_time = time.time()
    try:
        candidates = await collect_candidates(llm, duplicate_detector)

        if not candidates:
            logger.warning("📭 Нет подходящих кандидатов")
            return 0

        # 🍇 КЛАСТЕРИЗАЦИЯ НОВОСТЕЙ ПО СМЫСЛУ
        # Группируем похожие новости из разных фидов в одну
        clusters = cluster_news_candidates(candidates, threshold=0.55)
        
        # Объединяем новости внутри кластеров
        merged_candidates = []
        for cluster in clusters:
            merged = merge_cluster_news(cluster)
            if merged:
                merged_candidates.append(merged)
        
        # Пересчитываем рейтинги для объединённых кандидатов
        for c in merged_candidates:
            age_hours = (datetime.now(timezone.utc) - c["pub_date"]).total_seconds() / 3600
            freshness_bonus = 5 if age_hours < 2 else (3 if age_hours < 4 else 1)
            # Бонус за объединение нескольких новостей
            merge_bonus = c.get('merged_count', 1) * 2
            
            c["rating"] = (
                c.get("high_priority_matches", 0) * 5 +
                c.get("keyword_matches", 0) * 2 +
                freshness_bonus +
                merge_bonus
            )
        
        # Сортируем по рейтингу
        merged_candidates.sort(key=lambda x: x.get("rating", 0), reverse=True)
        
        logger.info("=" * 60)
        logger.info(f"📊 ТОП-{min(3, len(merged_candidates))} кандидатов для публикации:")
        for i, c in enumerate(merged_candidates[:3], 1):
            age_h = (datetime.now(timezone.utc) - c["pub_date"]).total_seconds() / 3600
            merged_info = f" (объединено {c.get('merged_count', 1)})" if c.get('is_merged') else ""
            logger.info(f"   {i}. [{c.get('rating', 0):>3}] {c['title'][:60]} (возраст: {age_h:.1f}ч, HOT:{c.get('high_priority_matches', 0)}, ключ:{c.get('keyword_matches', 0)}{merged_info})")
        logger.info("=" * 60)

        # Пробуем топ-3 на случай если рерайт упадёт
        for idx, best in enumerate(merged_candidates[:3], 1):
            if not isinstance(best, dict):
                logger.error(f"❌ Кандидат не словарь, а {type(best)}")
                continue

            logger.info(f"▶️ [{idx}/3] Обработка: {best['title'][:70]}")

            # 🔥 РАССЧИТЫВАЕМ ПРИОРИТЕТ НОВОСТИ
            priority, triggers = calculate_priority(best["title"], best["summary"])
            logger.info(f"   🔥 Приоритет: {priority} (триггеры: {triggers if triggers else 'нет'})")

            # ✅ Fetch только для победителя
            full_text = await fetch_article_text(session, best["link"])
            body = full_text if full_text and len(full_text) > 150 else best["summary"]

            if len(body) < 40:
                logger.warning(f"   ⚠️ ОТКЛОНЁН: Текст слишком короткий ({len(body)} символов)")
                continue

            # ✅ Рерайт только для победителя
            logger.info(f"   🤖 LLM рерайт...")
            rewritten = await llm.rewrite(best["title"], body)
            if not rewritten:
                logger.warning(f"   ⚠️ ОТКЛОНЁН: LLM рерайт вернул пусто")
                continue

            final_text = postprocess_text(rewritten)
            if not final_text or len(final_text) < 50:
                logger.warning(f"   ⚠️ ОТКЛОНЁН: Постпроцессинг неудачен ({len(final_text) if final_text else 0} символов)")
                continue

            if not is_russian_text(final_text):
                logger.warning(f"   ❌ ОТКЛОНЁН: Не русский текст")
                continue

            logger.info(f"   ✅ Рерайт успешен: {len(final_text)} символов")

            # 🔥 3-УРОВНЕВАЯ ЛОГИКА ПУБЛИКАЦИИ
            if priority >= 95:
                # 🔥 CRITICAL: Автопостинг сразу в канал (минуя предложку)
                logger.info(f"🚨 CRITICAL NEWS (priority={priority}): Публикация сразу в канал!")
                send_result = await send_to_channel(session, final_text, best["link"], priority, triggers)
                if send_result:
                    # Сохраняем в локальную БД
                    final_hash = get_content_hash(final_text[:200], best["link"])
                    await save_post(
                        best["link"],
                        final_hash,
                        best["source"],
                        best["title_normalized"],
                        "autopost_critical"
                    )
                    # ✅ Сохраняем в ГЛОБАЛЬНУЮ БД (дедупликация между ботами)
                    if GLOBAL_DEDUP_ENABLED:
                        try:
                            content_hash = get_universal_hash(best["title"], best["link"], best["pub_date"], config.category)
                            await mark_global_posted(
                                content_hash,
                                config.tg_channel,
                                config.category,
                                best["title"][:100],
                                config.category
                            )
                            logger.info(f"🌐 Отметка в глобальной БД: {best['title'][:50]}")
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка глобальной отметки: {e}")

                    content_dedup_hash = get_content_dedup_hash(best["title"], best["summary"])
                    await save_content_dedup_hash(content_dedup_hash)
                    state.last_post_time = asyncio.get_event_loop().time()
                    logger.info(f"✅✅✅ АВТОПОСТ ОПУБЛИКОВАН В КАНАЛ: {best['title'][:60]}")
                    return 1
                else:
                    logger.warning("⚠️ Автопостинг не удался, пробуем следующего")
                    continue

            elif priority >= 85:
                # ⚡ HOT: Минуя LLM classify, но в предложку
                logger.info(f"⚡ HOT NEWS (priority={priority}): Отправка в предложку (без classify)")
                send_result = await send_to_suggestion_with_retry(session, final_text, best["link"], best["pub_date"], best["title"])
                if send_result:
                    final_hash = get_content_hash(final_text[:200], best["link"])
                    await save_post(
                        best["link"],
                        final_hash,
                        best["source"],
                        best["title_normalized"],
                        "hot_news"
                    )
                    content_dedup_hash = get_content_dedup_hash(best["title"], best["summary"])
                    await save_content_dedup_hash(content_dedup_hash)
                    state.last_post_time = asyncio.get_event_loop().time()
                    logger.info(f"✅✅✅ ОПУБЛИКОВАНО В ПРЕДЛОЖКУ (HOT): {best['title'][:60]}")
                    return 1
                else:
                    logger.warning("⚠️ Отправка в предложку не удалась, пробуем следующего")
                    continue

            else:
                # 📝 NORMAL: Полная проверка (LLM classify уже пройден в process_feed)
                logger.info(f"📝 NORMAL NEWS (priority={priority}): Отправка в предложку")
                send_result = await send_to_suggestion_with_retry(session, final_text, best["link"], best["pub_date"], best["title"])
                if send_result:
                    final_hash = get_content_hash(final_text[:200], best["link"])
                    await save_post(
                        best["link"],
                        final_hash,
                        best["source"],
                        best["title_normalized"],
                        "posted"
                    )
                    content_dedup_hash = get_content_dedup_hash(best["title"], best["summary"])
                    await save_content_dedup_hash(content_dedup_hash)
                    state.last_post_time = asyncio.get_event_loop().time()
                    logger.info(f"✅✅✅ ОПУБЛИКОВАНО В ПРЕДЛОЖКУ: {best['title'][:60]}")
                    return 1
                else:
                    logger.warning("⚠️ Отправка не удалась, пробуем следующего")
                    continue

        logger.warning("=" * 60)
        logger.warning("❌ ВСЕ ТОП-3 КАНДИДАТА ОТКЛОНЕНЫ")
        logger.warning(f"   Всего найдено кандидатов: {len(candidates)}")
        for i, c in enumerate(candidates[:3], 1):
            logger.warning(f"   {i}. {c['title'][:60]}")
        logger.warning("=" * 60)
        return 0
    finally:
        elapsed = time.time() - start_time
        if prom_metrics:
            prom_metrics.observe_proc_time(elapsed)
        logger.info(f"⏱️ Время обработки цикла: {elapsed:.2f} сек")

# ================= GRACEFUL SHUTDOWN =================
async def graceful_shutdown(llm: CachedLLMClient):
    logger.info("🛑 Завершение работы бота...")
    if state.current_task and not state.current_task.done():
        try:
            await asyncio.wait_for(state.current_task, timeout=30)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Таймаут ожидания задачи")
    llm._save_cache()
    await cleanup_old_posts()
    await cleanup_old_data()
    await cleanup_old_logs()
    if GLOBAL_DEDUP_ENABLED:
        try:
            await cleanup_global_db(days=30)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки глобальной БД: {e}")
    metrics.print_summary()
    logger.info("✅ Бот остановлен корректно")

# ================= MAIN =================
async def main():
    # ✅ SINGLE INSTANCE CHECK через PM2
    # PM2 сам управляет процессами, lock не нужен
    logger.info("ℹ️ Запуск politika.py")
    
    await init_db()

    if GLOBAL_DEDUP_ENABLED:
        try:
            await init_global_db()
            logger.info("✅ Глобальная БД дедупликации инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации глобальной БД: {e}")

    llm = CachedLLMClient()
    alert_manager = AlertManager(config.tg_token)
    duplicate_detector = DuplicateDetector()

    # ✅ ЗАПУСК ПЛАНИРОВЩИКА ДАЙДЖЕСТОВ (ежедневно в 22:00)
    digest_task = None
    if config.autopost_enabled:
        try:
            digest_task = asyncio.create_task(
                schedule_digest_for_category(llm, alert_manager.telegram, config, "politics", hour=22)
            )
            logger.info("✅ Планировщик дайджестов запущен (22:00 daily)")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить планировщик дайджестов: {e}")

    logger.info("=" * 60)
    logger.info("🚀 @I_Politika PRODUCTION 2026")
    logger.info(f"   Категория: {config.category.upper()}")
    logger.info(f"   Модель: {config.model_name}")
    logger.info(f"   Лимит: {config.max_posts_per_day} постов/день")
    logger.info(f"   🌐 Перевод: {'ВКЛ' if TRANSLATOR_AVAILABLE else 'ВЫКЛ'}")
    logger.info(f"   🔄 Fuzzy порог: {config.fuzzy_threshold}%")
    logger.info(f"   💾 Кэш: {len(llm.cache)} записей")
    logger.info(f"   ���� Глобальная дедупликация: {'✅' if GLOBAL_DEDUP_ENABLED else '❌'}")
    logger.info(f"   ☀️ ДЕНЬ: {config.cycle_delay_day_min//60}-{config.cycle_delay_day_max//60} мин")
    logger.info(f"   🌙 НОЧЬ: {config.cycle_delay_night_min//60}-{config.cycle_delay_night_max//60} мин")
    logger.info("=" * 60)

    ssl_context = create_secure_ssl_context()
    connector = aiohttp.TCPConnector(limit=10, force_close=True, ssl=ssl_context, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=60, connect=15)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        cycle = 0
        try:
            while state.running:
                cycle += 1
                time_label = "🌙 НОЧЬ" if config.is_night_time() else "☀️ ДЕНЬ"

                logger.info("=" * 60)
                logger.info(f"🔄 Цикл #{cycle} | {time_label} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info("=" * 60)

                try:
                    state.current_task = asyncio.create_task(
                        collect_and_process_news(llm, duplicate_detector, session)
                    )
                    posts_published = await state.current_task

                    # ✅ НОЧНЫЕ ЗАДЕРЖКИ: 1.5-2x длиннее чем днем
                    is_night = config.is_night_time()
                    night_multiplier = 1.8 if is_night else 1.0

                    if posts_published > 0:
                        logger.info(f"✅ Опубликовано: {posts_published}")
                        # ✅ Нашли новость — следующая через 10-15 минут (ночью 18-27 мин)
                        base_delay_min = 600
                        base_delay_max = 900
                        delay = random.randint(
                            int(base_delay_min * night_multiplier),
                            int(base_delay_max * night_multiplier)
                        )
                        if is_night:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (НОЧЬ 1.8x, была публикация)")
                        else:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (была публикация)")
                    else:
                        # ✅ Не нашли новостей — следующая через 5-10 минут (ночью 9-18 мин)
                        base_delay_min = 300
                        base_delay_max = 600
                        delay = random.randint(
                            int(base_delay_min * night_multiplier),
                            int(base_delay_max * night_multiplier)
                        )
                        if is_night:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (НОЧЬ 1.8x, нет новостей)")
                        else:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (нет новостей, ищем дальше)")

                    if cycle % 10 == 0:
                        await cleanup_old_posts()
                        await cleanup_old_data()
                        await cleanup_old_logs()

                    if cycle % 5 == 0:
                        llm._save_cache()

                    logger.info(f"😴 {time_label} | Следующий цикл через {delay // 60} мин {delay % 60} сек")
                    await asyncio.sleep(delay)

                except asyncio.CancelledError:
                    logger.info("🛑 Цикл прерван сигналом отмены")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка в цикле: {e}", exc_info=True)
                    metrics.log_error(f"main_loop: {e}")
                    error_delay = 900 if config.is_night_time() else 600
                    logger.info(f"⏳ Ожидание {error_delay // 60} минут после ошибки")
                    await asyncio.sleep(error_delay)
        finally:
            # Graceful shutdown при выходе из цикла
            await graceful_shutdown(llm)

def signal_handler(signum, frame):
    logger.info(f"🛑 Получен сигнал остановки: {signum}")
    state.running = False

# ================= ТЕСТЫ =================
async def run_tests():
    print("\n" + "=" * 60)
    print("🧪 ЗАПУСК ТЕСТОВ POLITIKA")
    print("=" * 60)
    passed = 0
    failed = 0

    tests = [
        ("normalize_title", lambda: "путин" in normalize_title("Путин подписал указ!")),
        ("clean_html", lambda: "Текст" in clean_html("<p>Текст</p>")),
        ("get_content_hash", lambda: get_content_hash("T", "B") == get_content_hash("T", "B")),
        ("get_content_dedup_hash", lambda: len(get_content_dedup_hash("Заголовок", "Текст")) == 64),
        ("is_politics_candidate", lambda: is_politics_candidate("Путин провел совещание", "Президент")),
        ("validate_html_tags", lambda: validate_html_tags("<b>Заголовок") == "<b>Заголовок</b>"),
        ("ssl_context", lambda: isinstance(create_secure_ssl_context(), ssl.SSLContext)),
        ("postprocess_text", lambda: "\n\n" in postprocess_text("**Заголовок**\n\nТекст поста здесь.")),

        # Тесты postprocess_text
        ("postprocess_empty", lambda: "Политическая новость" in postprocess_text("")),
        ("postprocess_short", lambda: "Политическая новость" in postprocess_text("коротко")),
        ("postprocess_noise", lambda: "Политическая новость" in postprocess_text("подробности можно найти на сайте")),
        ("postprocess_long", lambda: len(postprocess_text("**Заголовок**\n\n" + "Sentence. " * 100)) <= 900),
        ("postprocess_html_tags", lambda: postprocess_text("**Заголовок**\n\nТекст").count('<b>') == postprocess_text("**Заголовок**\n\nТекст").count('</b>')),
        ("postprocess_double_newlines", lambda: postprocess_text("**Заголовок**\n\nТекст").count('\n\n') >= 1),
        ("postprocess_channel_signature", lambda: len(postprocess_text("**Заголовок**\n\nТекст")) > 20 and "\n\n" in postprocess_text("**Заголовок**\n\nТекст")),
        ("postprocess_very_long", lambda: len(postprocess_text("**H**\n\n" + "A" * 2000)) <= 900),
        ("postprocess_unbalanced_b", lambda: "</b>" in postprocess_text("**Заголовок**\n\nТекст <b>жирный")),
        ("postprocess_multiple_paragraphs", lambda: "\n\n" in postprocess_text("**Заголовок**\n\nПервый важный абзац текста.\n\nВторой важный абзац текста.\n\nТретий важный абзац текста.")),

        # ✅ Тесты кластеризации новостей
        ("extract_key_entities", lambda: 'путин' in extract_key_entities("Путин провел совещание в Кремле")['persons']),
        ("extract_key_entities_org", lambda: 'госдум' in extract_key_entities("Госдума приняла закон")['organizations']),
        ("extract_key_entities_loc", lambda: 'москв' in extract_key_entities("В Москве прошло событие")['locations']),
        ("extract_key_entities_event", lambda: 'выбор' in extract_key_entities("Выборы состоялись вчера")['events']),
        ("calculate_news_similarity_same", lambda: calculate_news_similarity(
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил новый закон', 'pub_date': datetime.now(timezone.utc)},
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил новый закон', 'pub_date': datetime.now(timezone.utc)}
        ) > 0.8),
        ("calculate_news_similarity_different", lambda: calculate_news_similarity(
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил закон', 'pub_date': datetime.now(timezone.utc)},
            {'title': 'В Москве открыли театр', 'summary': 'Новый культурный центр начал работу', 'pub_date': datetime.now(timezone.utc)}
        ) < 0.5),
        ("cluster_news_candidates", lambda: len(cluster_news_candidates([
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил закон', 'pub_date': datetime.now(timezone.utc), 'source': 'tass', 'high_priority_matches': 1, 'keyword_matches': 2},
            {'title': 'Путин утвердил указ', 'summary': 'Президент подписал документ', 'pub_date': datetime.now(timezone.utc), 'source': 'ria', 'high_priority_matches': 1, 'keyword_matches': 2},
        ], threshold=0.5)) == 1),
        ("merge_cluster_news_single", lambda: merge_cluster_news([
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил закон', 'pub_date': datetime.now(timezone.utc), 
             'source': 'https://tass.ru/rss/v2.xml', 'link': 'http://test', 'hash': 'abc', 'title_normalized': 'путин указ',
             'high_priority_matches': 1, 'keyword_matches': 2}
        ])['is_merged'] == False),
        ("merge_cluster_news_merged", lambda: merge_cluster_news([
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил закон. Новые меры вступают в силу.', 'pub_date': datetime.now(timezone.utc),
             'source': 'https://tass.ru/rss/v2.xml', 'link': 'http://test1', 'hash': 'abc1', 'title_normalized': 'путин указ',
             'high_priority_matches': 1, 'keyword_matches': 2},
            {'title': 'Путин утвердил документ', 'summary': 'Президент подписал важный указ. Документ опубликован.', 'pub_date': datetime.now(timezone.utc),
             'source': 'https://ria.ru/export/rss2/archive/index.xml', 'link': 'http://test2', 'hash': 'abc2', 'title_normalized': 'путин указ',
             'high_priority_matches': 1, 'keyword_matches': 2},
        ])['is_merged'] == True),
        ("merge_cluster_news_has_bullets", lambda: '•' in merge_cluster_news([
            {'title': 'Путин подписал указ', 'summary': 'Президент утвердил закон. Меры вступают в силу с завтра.', 'pub_date': datetime.now(timezone.utc),
             'source': 'https://tass.ru/rss/v2.xml', 'link': 'http://test1', 'hash': 'abc1', 'title_normalized': 'путин указ',
             'high_priority_matches': 1, 'keyword_matches': 2},
            {'title': 'Путин утвердил документ', 'summary': 'Президент подписал указ. Документ опубликован на портале.', 'pub_date': datetime.now(timezone.utc),
             'source': 'https://ria.ru/export/rss2/archive/index.xml', 'link': 'http://test2', 'hash': 'abc2', 'title_normalized': 'путин указ',
             'high_priority_matches': 1, 'keyword_matches': 2},
        ])['summary']),
    ]

    for name, test_fn in tests:
        print(f"\n📝 Тест: {name}")
        try:
            assert test_fn()
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    print("=" * 60)
    return failed == 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    else:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен пользователем")
        except Exception as e:
            logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
            sys.exit(1)
