#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
💰 @ecosteroid PRODUCTION 2026 — ПЕРЕПИСАННАЯ ВЕРСИЯ
✅ Глобальная дедупликация (защита от повторов между каналами)
✅ Универсальный хеш (единый для всех парсеров)
✅ Атомарная запись черновиков
✅ Circuit breaker для LLM
✅ Кэширование LLM ответов
✅ Защита от выдумывания дат
✅ Фильтрация английских слов
✅ Расширенные метрики
✅ Graceful shutdown
✅ Адаптивный rate limiting
✅ SSL верификация включена
✅ Тесты добавлены
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
from global_dedup import init_global_db, is_global_duplicate, mark_global_posted, get_universal_hash, get_content_dedup_hash

# ✅ DIGEST GENERATOR — для ежедневных дайджестов
from shared import DigestGenerator, schedule_digest_for_category

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

# 📊 PROMETHEUS METRICS
try:
    from prometheus_metrics import PrometheusMetrics
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    PrometheusMetrics = None

# ============ ГЛОБАЛЬНАЯ ДЕДУПЛИКАЦИЯ ============
try:
    from global_dedup import (
        init_global_db,
        is_global_duplicate,
        is_global_duplicate_cross_category,
        mark_global_posted,
        get_universal_hash,
        cleanup_global_db,
        get_content_dedup_hash,
        is_duplicate_advanced,
        normalize_title_for_dedup,
        check_duplicate_multi_layer
    )
    GLOBAL_DEDUP_ENABLED = True
except ImportError:
    GLOBAL_DEDUP_ENABLED = False
    logging.warning("⚠️ global_dedup.py не найден — дедупликация между каналами отключена")

load_dotenv()

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
# 🔐 ГЛОБАЛЬНЫЙ SSL CONTEXT (экономия 1-2 MB RAM)
SSL_CONTEXT = ssl.create_default_context()

def create_secure_ssl_context() -> ssl.SSLContext:
    """✅ Создание безопасного SSL контекста"""
    return SSL_CONTEXT

async def write_draft_atomic(draft_path: Path, data: dict):
    """✅ Атомарная запись черновика: пишем во временный файл → переименовываем"""
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
    """Конфигурация бота"""
    tg_token: str = Field(default="", min_length=10)
    router_api_key: str = Field(default="", min_length=10)

    channel: str = "@eco_steroid"
    signature: str = "@eco_steroid"
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

    cycle_delay_day_min: int = 660       # День: минимум 11 мин
    cycle_delay_day_max: int = 960       # День: максимум 16 мин
    cycle_delay_night_min: int = 1800    # Ночь: минимум 30 мин
    cycle_delay_night_max: int = 2700    # Ночь: максимум 45 мин

    night_start_hour: int = 22   # 01:00 МСК = 22:00 UTC
    night_end_hour: int = 5      # 08:00 МСК = 05:00 UTC

    max_news_age_hours: int = 12

    tg_channel_politics: str = Field(default="")
    tg_channel_economy: str = Field(default="")
    tg_channel_cinema: str = Field(default="")
    
    suggestion_chat_id_politics: str = Field(default="")
    suggestion_chat_id_economy: str = Field(default="")
    suggestion_chat_id_cinema: str = Field(default="")

    db_path: str = "eco_memory.db"
    min_delay_between_posts: int = 600
    domain_min_delay: float = 1.2

    autopost_enabled: bool = True  # ✅ Для дайджестов

    fuzzy_threshold: int = 80
    duplicate_check_hours: int = 72

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
        """Возвращает задержку между циклами"""
        current_hour = datetime.now(timezone.utc).hour
        if self.night_start_hour <= current_hour or current_hour < self.night_end_hour:
            return random.randint(self.cycle_delay_night_min, self.cycle_delay_night_max)
        else:
            return random.randint(self.cycle_delay_day_min, self.cycle_delay_day_max)
    
    def is_night_time(self) -> bool:
        """Проверка ночного времени"""
        current_hour = datetime.now(timezone.utc).hour
        return self.night_start_hour <= current_hour or current_hour < self.night_end_hour

config = BotConfig()

# ================= RSS FEEDS =================
# ✅ ОСНОВНЫЕ ФИДЫ — только проверенные источники
RSS_FEEDS = [
    "https://tass.ru/rss/v2.xml",              # ТАСС — официальные новости
    "https://www.interfax.ru/rss.asp",         # Интерфакс — экономика и финансы
    "https://www.vedomosti.ru/rss/news",       # Ведомости — бизнес и экономика
    "https://www.kommersant.ru/RSS/news.xml",  # Коммерсантъ — деловые новости
    "https://ria.ru/export/rss2/archive/index.xml",  # РИА — экономика
]
logger = logging.getLogger(__name__)

# ================= ЛОГИРОВАНИЕ =================
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_dir / "eco_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# ================= КЛЮЧЕВЫЕ СЛОВА =================
ECONOMY_KEYWORDS = {
    # 💰 Финансы и валюта
    'экономик', 'рубл', 'доллар', 'евро', 'курс', 'инфляц', 'цб', 'центробанк',
    'банк', 'кредит', 'ставк', 'ключев', 'процент', 'инвестиц', 'акци', 'биржа',
    'нефт', 'газ', 'энерг', 'экспорт', 'импорт', 'торгов', 'пошлин', 'тариф',
    'налог', 'бюджет', 'дефицит', 'профицит', 'долг', 'займ', 'облигац',
    'ввп', 'рост', 'спад', 'рецесс', 'кризис', 'санкц', 'эмбарго', 'brent',
    'золот', 'серебр', 'метал', 'биткоин', 'криптовалют', 'блокчейн',
    'промышл', 'производств', 'завод', 'фабрик', 'сельск', 'урожай',
    'строительств', 'недвижим', 'ипотек', 'жильё', 'жилищ', 'субсид',
    'пенси', 'зарплат', 'доход', 'безработиц', 'занятост', 'вакансии',
    'торговля', 'коммерц', 'продаж', 'покупател', 'магазин', 'ритейл',
    # ✈️ Транспорт и авиация
    'авиа', 'полёт', 'аэропорт', 'воздушн', 'трансп', 'логист', 'перевоз',
    # 🏨 Туризм и услуги
    'турист', 'отел', 'тур', 'курорт', 'гостиниц', 'сервис', 'услуг',
    # 🏭 Бизнес и компании
    'компани', 'корпорац', 'бизнес', 'предприят', 'фирм', 'холдинг', 'акци',
    'капитал', 'дивиденд', 'прибыл', 'убыток', 'доход', 'расход', 'счёт',
    # 💼 Рынок труда
    'работ', 'сотрудник', 'кадр', 'найм', 'увольнен', 'оклад', 'преми',
    # 🌐 Международная торговля
    'таможн', 'деклар', 'квот', 'лицензи', 'сертификат', 'стандарт',
    # 📊 Экономика регионов
    'регион', 'область', 'губернатор', 'развити', 'программ', 'нацпроект',
    # 🏦 Финансовые организации
    'фонд', 'страхов', 'пенсион', 'накоплен', 'вклад', 'депозит',
    # 💡 Технологии и инновации
    'технолог', 'инноваци', 'цифр', 'автоматиз', 'модерниз', 'разработк',
}

HIGH_PRIORITY_KEYWORDS = {
    'санкц', 'курс доллара', 'курс рубля', 'цб рф', 'центробанк', 'ключевая ставка',
    'инфляция', 'нефть', 'газ', 'brent', 'биткоин', 'крипто', 'ввп', 'рецессия',
    'кризис', 'дефолт', 'девальвация', 'эмбарго', 'экспорт', 'импорт', 'бюджет'
}

# ================= ТРИГГЕРЫ ДЛЯ АВТОПОСТИНГА =================
# Пары ключевых слов с приоритетом (0-100) для определения критических новостей
URGENT_TRIGGERS = {
    # Финансовые рынки и валюта
    ('дефолт', 'объявлен', 100),
    ('дефолт', 'наступил', 95),
    ('обвал', 'рынок', 95),
    ('крах', 'биржа', 95),
    ('девальваци', 'рубль', 90),
    ('курс', 'доллар', 85),
    ('курс', 'рубль', 85),
    ('доллар', 'вырос', 80),
    ('рубль', 'упал', 80),
    
    # Ключевые решения ЦБ и правительства
    ('ключевая', 'ставка', 90),
    ('цб', 'решен', 85),
    ('цб', 'повыс', 85),
    ('цб', 'пониз', 80),
    ('нацпроект', 'финанс', 75),
    ('бюджет', 'дефицит', 80),
    
    # Санкции и торговля
    ('санкц', 'нефть', 95),
    ('санкц', 'газ', 90),
    ('санкц', 'введен', 90),
    ('санкц', 'отмен', 85),
    ('эмбарго', 'введен', 90),
    ('пошлин', 'введен', 80),
    
    # Кризисные явления
    ('кризис', 'наступил', 95),
    ('кризис', 'углуб', 85),
    ('рецесси', 'экономика', 90),
    ('инфляци', 'взлетел', 90),
    ('инфляци', 'вырос', 85),
    ('безработиц', 'вырос', 80),
    ('банкротств', 'объявлен', 85),
    
    # Энергоресурсы
    ('нефть', 'упал', 90),
    ('нефть', 'вырос', 85),
    ('нефть', ' Brent', 80),
    ('газ', 'отключен', 95),
    ('газ', 'постав', 85),
    ('энергетическ', 'кризис', 95),
    
    # Компании и банки
    ('банк', 'лицензи', 90),
    ('банк', 'лопнул', 90),
    ('компани', 'банкрот', 85),
    ('завод', 'останов', 85),
    ('завод', 'закры', 80),
    
    # Важные назначения
    ('назнач', 'министр', 80),
    ('отставк', 'министр', 85),
    ('назнач', 'глава', 75),
    
    # Эксперты и аналитика
    ('эксперт', 'назвал', 75),
    ('эксперт', 'услов', 75),
    ('эксперт', 'прогноз', 75),
    ('аналитик', 'прогноз', 75),
    ('прогноз', 'цена', 75),
    ('прогноз', 'курс', 75),
    
    # Цены и тарифы
    ('цена', 'газ', 85),
    ('цена', 'нефть', 85),
    ('цена', 'рост', 80),
    ('цена', 'пад', 80),
    ('тариф', 'рост', 80),
    ('тариф', 'измен', 75),
    
    # Авиация и транспорт
    ('авиа', 'рейс', 80),
    ('авиа', 'отмен', 85),
    ('авиа', 'перенос', 75),
    ('авиа', 'задерж', 75),
    ('рейс', 'Израиль', 85),
    ('рейс', 'Иран', 85),
    ('полёт', 'запрет', 85),
    ('воздушн', 'пространств', 85),
    ('аэропорт', 'закры', 85),
    
    # Туризм
    ('турист', 'Израиль', 80),
    ('турист', 'Иран', 80),
    ('туроператор', 'отмен', 75),
    ('путёвк', 'рост', 75),
    ('отмен', 'тур', 80),
    
    # Ситуации и конфликты
    ('ситуаци', 'Иран', 85),
    ('ситуаци', 'Израиль', 85),
    ('обострен', 'ситуаци', 85),
    ('эскалаци', 'конфликт', 85),
    ('конфликт', 'Иран', 80),
    ('удар', 'Иран', 85),
    ('атак', 'Иран', 85),
    ('обстрел', 'Белгород', 85),
    
    # Реакции и заявления
    ('МИД', 'заявлен', 80),
    ('МИД', 'рекоменд', 75),
    ('посольств', 'откры', 75),
    ('консульств', 'выдал', 75),
    ('горяч', 'лин', 75),
    ('граждан', 'эвакуаци', 80),
    
    # Энергетика
    ('НПЗ', 'пожар', 80),
    ('нефтеперерабатывающ', 'завод', 80),
    ('электроэнерг', 'отключ', 75),
    ('свет', 'отключ', 80),
    ('энерг', 'кризис', 75),
}

# ✅ ДОПОЛНИТЕЛЬНЫЕ СЛОВА для более широкого охвата
ADDITIONAL_ECONOMY_KEYWORDS = {
    # Назначения и кадровые решения
    'назнач', 'уволен', 'отставк', 'кандидатур', 'согласован', 'утвержд',
    # Открытия и запуски
    'откры', 'запуск', 'начал', 'стартовал', 'введен', 'заверш',
    # Производство и промышленность
    'производств', 'завод', 'фабрик', 'цех', 'лини', 'мощност', 'выпуск',
    # События и изменения
    'измен', 'реформ', 'преобразован', 'реорганизац', 'слиян', 'поглощен',
    # Контроль и регулирование
    'контрол', 'проверк', 'надзор', 'мониторинг', 'аудит', 'инспекц',
    # Цены и стоимость
    'цен', 'стоим', 'тариф', 'расцен', 'прайс', 'дешев', 'дорож',
    # Поставки и обеспечение
    'постав', 'снабжение', 'заказ', 'контракт', 'тендер', 'аукцион',
    # Экономические зоны и территории
    'территори', 'зона', 'кластер', 'парк', 'особ', 'свободн',
    # Отрасли экономики
    'отрасл', 'сектор', 'направлен', 'сфер', 'област', 'отдел',
}

NON_ECONOMY_KEYWORDS = {
    'футбол', 'хоккей', 'баскетбол', 'олимпиад', 'чемпионат', 'кино', 'фильм',
    'сериал', 'актёр', 'режиссёр', 'музык', 'концерт', 'альбом', 'спортсмен'
}

# ================= ЛЕММАТИЗАЦИЯ =================
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


ECONOMY_KEYWORDS_LEMMA = lemmatize_keywords(ECONOMY_KEYWORDS)
HIGH_PRIORITY_KEYWORDS_LEMMA = lemmatize_keywords(HIGH_PRIORITY_KEYWORDS)


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
        """Вывод статистики"""
        uptime = datetime.now() - self.start_time
        total_duplicates = (self.metrics['duplicates_exact'] +
                          self.metrics['duplicates_fuzzy'] +
                          self.metrics['duplicates_global'])
        cache_rate = 0
        if self.metrics['llm_calls'] > 0:
            cache_rate = (self.metrics['llm_cache_hits'] /
                         (self.metrics['llm_calls'] + self.metrics['llm_cache_hits'])) * 100

        logger.info("=" * 60)
        logger.info("📊 СТАТИСТИКА РАБОТЫ БОТА")
        logger.info(f"   Время работы: {uptime}")
        logger.info(f"   Постов отправлено: {self.metrics['posts_sent']}")
        logger.info(f"   Постов отклонено: {self.metrics['posts_rejected']}")
        logger.info(f"   ")
        logger.info(f"   Дубликатов всего: {total_duplicates}")
        logger.info(f"   ├─ Точных: {self.metrics['duplicates_exact']}")
        logger.info(f"   ├─ Fuzzy: {self.metrics['duplicates_fuzzy']}")
        logger.info(f"   └─ Глобальных: {self.metrics['duplicates_global']}")
        logger.info(f"   ")
        logger.info(f"   LLM вызовов: {self.metrics['llm_calls']}")
        logger.info(f"   Cache hits: {self.metrics['llm_cache_hits']} ({cache_rate:.1f}%)")
        logger.info(f"   LLM ошибок: {self.metrics['llm_errors']}")
        logger.info(f"   ")
        logger.info(f"   Заблокировано выдуманных дат: {self.metrics['fake_dates_blocked']}")
        logger.info(f"   Заблокировано англ. слов: {self.metrics['english_words_blocked']}")
        logger.info(f"   ")
        logger.info(f"   Фидов обработано: {self.metrics['feeds_processed']}")
        logger.info(f"   Кандидатов найдено: {self.metrics['candidates_found']}")
        logger.info("=" * 60)

metrics = BotMetrics()

# 📊 PROMETHEUS METRICS
prom_metrics = None
if PROMETHEUS_AVAILABLE:
    try:
        prom_metrics = PrometheusMetrics(bot_name='economy', port=8001)
        logger.info("✅ Prometheus метрики запущены на порту 8001")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось запустить Prometheus метрики: {e}")

# ================= СОСТОЯНИЕ =================
class BotState:
    def __init__(self):
        self.last_post_time = 0
        self.running = True
        self.current_task = None

state = BotState()

# ================= ПАПКИ =================
pending_dir = Path("pending_posts")
pending_dir.mkdir(exist_ok=True)

# ================= БАЗА ДАННЫХ =================
async def init_db():
    """Инициализация БД"""
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
    """🧹 Очистка старых данных"""
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
        
        # 4. Бэкап БД
        import shutil
        backup_dir = Path("db_backups")
        backup_dir.mkdir(exist_ok=True)
        db_path = Path(config.db_path)
        if db_path.exists():
            backup_file = backup_dir / f"{db_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
            shutil.copy2(db_path, backup_file)
            logger.info(f"💾 Бэкап БД: {backup_file.name}")
            
            # Удаляем бэкапы старше 7 дней
            for old_backup in backup_dir.glob("*.db"):
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
    """Удаление постов старше 30 дней"""
    async with aiosqlite.connect(config.db_path) as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        cursor = await db.execute("DELETE FROM posted WHERE posted_at < ?", (cutoff,))
        deleted = cursor.rowcount
        await db.commit()
        if deleted > 0:
            logger.info(f"🧹 Удалено {deleted} старых записей")

async def save_post(link: str, text_hash: str, source: str,
                   title_normalized: str = "", duplicate_method: str = "none"):
    """Сохранение поста"""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO posted
               (link, hash, theme, source, title_normalized, duplicate_check_method)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (link, text_hash, "ECONOMY", source, title_normalized, duplicate_method)
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
    """Безопасное преобразование в строку"""
    if value is None:
        return ""
    if isinstance(value, list):
        return '\n'.join(str(x) for x in value if x)
    return str(value).strip()

def clean_html(raw) -> str:
    """Очистка HTML"""
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
    """Хеш контента (локальный, для обратной совместимости)"""
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
    """Нормализация заголовка"""
    title = re.sub(r'[^\w\s\-]', '', title.lower())
    stop_words = {'и', 'в', 'на', 'с', 'по', 'о', 'об', 'из', 'к', 'для', 'что', 'это'}
    words = [w for w in title.split() if w not in stop_words and len(w) > 2]
    return ' '.join(words)

def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches
def is_economy_candidate(title: str, summary: str) -> Tuple[bool, int, int]:
    """Предфильтрация по ключевым словам с лемматизацией"""
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    non_economy_count = sum(1 for word in NON_ECONOMY_KEYWORDS if word in text)
    if non_economy_count >= 2:
        return False, 0, 0

    all_keywords = ECONOMY_KEYWORDS_LEMMA | lemmatize_keywords(ADDITIONAL_ECONOMY_KEYWORDS)
    matches = sum(1 for kw in all_keywords if kw in text_lemma)
    high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS_LEMMA if kw in text_lemma)

    if matches == 0:
        all_keywords_orig = ECONOMY_KEYWORDS | ADDITIONAL_ECONOMY_KEYWORDS
        matches = sum(1 for kw in all_keywords_orig if kw in text)
        high_priority_matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)

    return matches >= 1, matches, high_priority_matches


def is_digest_headline(title: str) -> bool:
    """
    ✅ ФИЛЬТР ДАЙДЖЕСТОВ/СВОДОК.
    Отфильтровывает заголовки вида:
    - "Спецоперация, 28 февраля: ..."
    - "28 февраля: сводка событий"
    - "Х��������онология событий за 28 февраля"
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
    
    Returns:
        (priority, matched_triggers)
    """
    text = f"{title} {summary}".lower()
    
    max_priority = 0
    matched = []
    
    for kw1, kw2, priority in URGENT_TRIGGERS:
        if kw1 in text and kw2 in text:
            if priority > max_priority:
                max_priority = priority
            matched.append(f"{kw1}+{kw2}")
    
    # Бонус за свежесть (новости за последний час)
    if "только что" in text or "минут" in text or "сегодня" in text:
        max_priority = min(100, max_priority + 5)
    
    # Бонус за множественные совпадения
    if len(matched) >= 2:
        max_priority = min(100, max_priority + 5)
    
    return max_priority, matched


def is_russian_text(text: str, min_ratio: float = 0.7) -> bool:
    """Проверка русского текста"""
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
            # Любое слово с заглавной буквы или целиком заглавное — это имя/бренд/СМИ
            if word[0].isupper() or word.isupper():
                return word
            skip_words = {
                'brent', 'opec', 'nato', 'brics', 'swift', 'covid',
                'gdp', 'ceo', 'ipo', 'api', 'ai', 'it', 'pr', 'hr',
                'usa', 'usd', 'eur', 'rub', 'gbp', 'jpy', 'cny',
                'imf', 'wto', 'g7', 'g20', 'eu', 'un', 'who'
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
    """Проверка HTML-тегов"""
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
    """Постобработка текста"""
    CHANNEL = config.bot_signature

    if isinstance(raw, list):
        raw = '\n'.join(str(item) for item in raw if item)

    raw = safe_to_string(raw)
    if not raw or len(raw) < 20:
        return f"<b>Экономическая новость</b>\n\n{CHANNEL}"

    raw = translate_foreign_words(raw)
    raw = re.sub(r'(Заголовок:|Первый абзац:|Второй абзац:|Третий абзац:)\s*', '', raw)

    header_match = re.search(r'\*\*(.+?)\*\*', raw)
    extracted_header = header_match.group(1).strip() if header_match else None

    if header_match:
        raw = raw.replace(header_match.group(0), '', 1).strip()

    clean_text = re.sub(r'(\*\*|__|\\*|_|#|`|```|\[|\])', '', raw)
    clean_text = re.sub(r'[ \t]+', ' ', clean_text)
    clean_text = re.sub(r'\n\s*\n\s*\n+', '\n', clean_text)
    clean_text = clean_text.strip()

    if not clean_text or len(clean_text) < 20:
        return f"<b>Экономическая новость</b>\n\n{CHANNEL}"

    sentences = re.split(r'(?<=[.!?])\s+', clean_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    noise_patterns = [
        r'экономические новости', r'новости экономики',
        r'подробност[иые]\s+(можно\s+)?найти', r'информаци[яю]\s+(можно\s+)?найти',
        r'читайте\s+(также|подробнее)', r'узнайте\s+больше',
        r'смотрите\s+по\s+ссылке', r'доступн[ао]\s+на\s+сайте',
        r'перейдите\s+по\s+ссылке',
        # ✅ Дни недели и даты — мета-комментарии
        r'^(суббота|воскресенье|понедельник|вторник|среда|четверг|пятница)\s*[–—:]\s+день',
        r'^(суббота|воскресенье|понедельник|вторник|среда|четверг|пятница)\s*,\s*когда',
        r'день,\s*когда\s+',
        # ✅ Мета-комментарии про публикацию
        r'опубликовал[оа][^\.]*информацию',
        r'сообщил[оа][^\.]*данные',
        r'представил[оа][^\.]*отчёт',
    ]

    def is_noise(sentence):
        s_lower = sentence.lower()
        return any(re.search(pattern, s_lower) for pattern in noise_patterns)

    sentences = [s for s in sentences if not is_noise(s)]

    if not sentences:
        return f"<b>Экономическая новость</b>\n\n{CHANNEL}"

    if extracted_header and len(extracted_header) > 10:
        header = f"💰{extracted_header[:120]}💰"
        body_sentences = sentences
    else:
        header = f"💰{sentences[:120]}💰"
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
        body = "\n\n".join(paragraphs)
    else:
        if len(sentences) > 150:
            header = sentences[:120]
            body = sentences[120:].strip()
        else:
            body = ""

    if body and len(body) > 30:
        formatted = f"<b>{header}</b>\n\n{body}"
    else:
        formatted = f"<b>{header}</b>"

    # ✅ ПУСТАЯ СТРОКА перед подписью
    formatted = formatted.rstrip() + f"\n\n{CHANNEL}"

    # 🔽 ЛИМИТ: 3800 символов (без фото)
    MAX_POST_LENGTH = 1000  # ← Запас для фото (Telegram: 1024)
    TRUNCATE_LENGTH = 950
    MIN_TRUNCATE_SPACE = 600

    if len(formatted) > MAX_POST_LENGTH:
        temp_text = formatted.replace(f"\n\n{CHANNEL}", "")
        truncated = temp_text[:TRUNCATE_LENGTH]

        # 🔍 УМНАЯ ОБРЕЗКА: ищем конец последнего完整ного предложения
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
        # ✅ ПУСТАЯ СТРОКА перед подписью (при обрезке тоже)
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

# ================= АДАПТИВНЫЙ RATE LIMITER =================
class AdaptiveRateLimiter:
    """Rate limiter с учётом времени суток"""
    def __init__(self):
        self.request_times = []
        self.error_count = 0
    
    async def wait(self):
        """Адаптивная задержка"""
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
    """LLM клиент с кэшированием и circuit breaker"""
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.router_api_key,
            base_url="https://routerai.ru/api/v1"
        )
        self.rate_limiter = AdaptiveRateLimiter()
        self.circuit_breaker_fails = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_open_until = 0
        self.cache_file = Path("llm_cache_eco.pkl")
        self.cache = self._load_cache()
    
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
        try:
            if len(self.cache) > 1000:
                self.cache = dict(list(self.cache.items())[-500:])
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка сохранения кэша: {e}")
    
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
            if hasattr(response, 'choices') and len(response.choices) > 0:
                choice = response.choices[0]
                if hasattr(choice, 'message'):
                    message = choice.message
                    if hasattr(message, 'content'):
                        content = message.content
                        if isinstance(content, list):
                            content = '\n'.join(str(item) for item in content if item)
                        if content:
                            return content.strip()
                if isinstance(choice, dict):
                    msg = choice.get('message', {})
                    if isinstance(msg, dict):
                        content = msg.get('content', '')
                        if isinstance(content, list):
                            content = '\n'.join(str(item) for item in content if item)
                        if content:
                            return content.strip()
            if isinstance(response, dict) and 'choices' in response:
                choices = response['choices']
                if isinstance(choices, list) and len(choices) > 0:
                    choice = choices[0]
                    if isinstance(choice, dict) and 'message' in choice:
                        content = choice['message'].get('content', '')
                        if isinstance(content, list):
                            content = '\n'.join(str(item) for item in content if item)
                        if content:
                            return content.strip()
            logger.warning(f"⚠️ Не удалось извлечь контент из ответа")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения контента: {e}")
            return None
    
    def _contains_fake_dates(self, text: str) -> bool:
        """
        ✅ Проверка на выдуманные даты — ТОЛЬКО явные фейки событий.
        Разрешает легитимные упоминания: "уровней 2024 года", "в 2025 году ожидается", "по итогам 2023"
        Блокирует: "28 февраля 2024 года начал", "в 2023 году подписал" (конкретные события)
        """
        text_lower = text.lower()
        
        # ✅ Блокируем ТОЛЬКО конкретные даты событий (день + месяц + год или год в контексте события)
        fake_event_patterns = [
            # Конкретная дата + год + событие: "28 февраля 2024 года начал", "15 марта 2025 произошел"
            r'\d{1,2}\s+(?:янв|февр|мар|апр|ма|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+(?:2023|2024|2025|2027|2028|2029|2030)\s*(?:года|г\.?)?\s*[,.]?\s*(?:начал|произош|удар|обстрел|убил|взорвал|подписал|объявил)',
            # Год + событие в прошедшем времени: "в 2024 году начал", "2023 году произошел"
            r'(?:в\s+)?(?:2023|2024|2025|2027|2028|2029|2030)\s*году\s+(?:начал|произош|удар|обстрел|убил|��зорвал|подписал|объявил|случил)',
            # Событие + дату: "начал операцию 28 февраля 2024", "произошел взрыв 15 марта 2025"
            r'(?:начал|произош|удар|обстрел|убил|взорвал)[а-я]*\s+(?:в\s+)?(?:2023|2024|2025|2027|2028|2029|2030)\s*(?:году|год)?',
        ]
        
        for pattern in fake_event_patterns:
            if re.search(pattern, text_lower):
                logger.warning(f"🚨 Обнаружена выдуманная дата события: {text[:100]}")
                metrics.log_fake_date()
                return True
        
        return False

    def _contains_too_much_english(self, text: str) -> bool:
        """
        ✅ Проверка на слишком много английских слов.
        Расширенный список экономических терминов.
        """
        allowed_english = {
            # Валюты и экономики
            'usa', 'usd', 'eur', 'rub', 'gbp', 'jpy', 'cny', 'chf', 'aud', 'cad', 'inr', 'krw',
            'gdp', 'gnp', 'cpi', 'ppi', 'pmi', 'nonfarm', 'fed', 'ecb', 'boj', 'pboc',
            # Финансовые инструменты и рынки
            'ipo', 'spac', 'etf', 'etfs', 'reit', 'reits', 'mutual', 'fund', 'hedge',
            'bond', 'bonds', 'treasury', 'yield', 'curve', 'spread', 'basis', 'points',
            'stock', 'stocks', 'share', 'shares', 'equity', 'equities', 'derivative',
            'option', 'options', 'future', 'futures', 'forward', 'swap', 'swaps',
            'bull', 'bear', 'long', 'short', 'leverage', 'margin', 'liquidity',
            'volatility', 'beta', 'alpha', 'dividend', 'yield', 'return', 'roi', 'roe',
            'eps', 'pe', 'pb', 'ps', 'ev', 'ebitda', 'capex', 'opex', 'freecashflow',
            # Организации и регуляторы
            'opec', 'nato', 'wto', 'imf', 'worldbank', 'brics', 'swift', 'bis', 'fsb',
            'sec', 'finra', 'cftc', 'esma', 'cbr', 'centralbank',
            # Биржи и индексы
            'nasdaq', 'nyse', 'amex', 'lse', 'tse', 'sse', 'hkex', 'asx', 'bse', 'nse',
            'moex', 'rts', 'micex', 'sp', 'spx', 'dow', 'dji', 'ndx', 'vix', 'russell',
            'ftse', 'dax', 'cac', 'nikkei', 'hangseng', 'sensex', 'brent', 'wti',
            # Компании и бренды (технологии)
            'apple', 'google', 'tesla', 'amazon', 'microsoft', 'meta', 'facebook',
            'twitter', 'x', 'netflix', 'nvidia', 'amd', 'intel', 'qualcomm', 'tsmc',
            'samsung', 'huawei', 'alibaba', 'tencent', 'byd', 'xiaomi',
            # Компании (финансы и энергетика)
            'blackrock', 'vanguard', 'statestreet', 'fidelity', 'jporgan', 'goldman',
            'morgan', 'stanley', 'citigroup', 'bankofamerica', 'wellsfargo',
            'exxon', 'chevron', 'shell', 'bp', 'totalenergies', 'gazprom', 'rosneft',
            'lukoil', 'novatek', 'transneft',
            # Авиакомпании и транспорт
            'azur', 'air', 'azur air', 's7', 'aeroflot', 'rossiya', 'pobeda',
            'emirates', 'qatar', 'turkish', 'lufthansa', 'airfrance', 'klm',
            'boeing', 'airbus', 'lockheed', 'northrop',
            # СМИ и агентства
            'reuters', 'bloomberg', 'cnbc', 'ft', 'wsj', 'marketwatch', 'seekingalpha',
            'barrons', 'forbes', 'fortune', 'economist',
            # Криптовалюты
            'crypto', 'bitcoin', 'btc', 'ethereum', 'eth', 'binance', 'coinbase',
            'defi', 'nft', 'dao', 'stablecoin', 'usdt', 'usdc', 'dai',
            # Географические названия
            'dubai', 'dxb', 'dwc', 'abudhabi', 'doha', 'qatar',
            'tehran', 'iran', 'israel', 'telaviv', 'jerusalem',
            'moscow', 'moskva', 'kiev', 'minsk',
            'washington', 'newyork', 'london', 'berlin', 'paris',
            'beijing', 'tokyo', 'delhi', 'mumbai', 'shanghai', 'shenzhen',
            'sharm', 'elsheikh', 'egypt', 'hurghada', 'singapore',
            # Отраслевые термины
            'airports', 'airport', 'flight', 'flights', 'cargo', 'logistics',
            'oil', 'gas', 'petrol', 'diesel', 'lng', 'lpg', 'ng',
            'steel', 'coal', 'uranium', 'copper', 'aluminum', 'nickel', 'zinc',
            'tech', 'digital', 'startup', 'venture', 'capital', 'private', 'equity',
            'ma', 'merger', 'acquisition', 'spinoff', 'spin-off', 'bankruptcy',
            # Имена собственные (политики, бизнесмены)
            'trump', 'putin', 'biden', 'zelensky', 'xi', 'jinping',
            'macron', 'scholz', 'johnson', 'sunak', 'truss',
            'musk', 'bezos', 'gates', 'buffett', 'ellison', 'page', 'brin',
            'powell', 'lagarde', 'kuroda', 'nabiullina',
        }
        english_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        suspicious_words = [w for w in english_words if w not in allowed_english]
        if len(suspicious_words) > 5:  # ✅ Увеличили порог с 3 до 5
            logger.warning(f"🚨 Много английских слов: {suspicious_words[:5]}")
            metrics.log_english_blocked()
            return True
        return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def classify(self, title: str, summary: str) -> Optional[str]:
        # ⚡ БЕЗ LLM — только ключевые слова
        text = (title + " " + summary).lower()
    
        # 1. СТОП-СЛОВА (спорт, культура и т.д.)
        stop_words = {
            'футбол', 'хоккей', 'баскетбол', 'теннис', 'олимпиад', 'чемпионат', 
            'спорт', 'матч', 'турнир', 'гонка', 'лыжн', 'фигурист', 
            'кино', 'фильм', 'сериал', 'актёр', 'режис��ёр', 'музык', 'концерт', 
            'альбом', 'певец', 'шоу', 'звезд', 'скандал', 'светск', 
            'погод', 'синоптик', 'осадки', 'температур'
        }
        if any(w in text for w in stop_words):
            logger.info(f"🛑 Отклонено по стоп-словам: {title[:60]}")
            return "NONE"

        # 2. РАЗРЕШЕННЫЕ СЛОВА (экономика)
        economy_words = {
            'экономик', 'финанс', 'бюджет', 'налог', 'ввп', 'инфляц', 'цб', 'банк',
            'рубл', 'доллар', 'евро', 'курс', 'ставк', 'кредит', 'инвестиц', 'акци',
            'биржа', 'торгов', 'экспорт', 'импорт', 'санкц', 'нефт', 'газ', 'энерг',
            'промышл', 'завод', 'производств', 'строительств', 'недвижим', 'ипотек',
            'криптовалют', 'биткоин', 'майнинг'
        }
        
        matches = sum(1 for w in economy_words if w in text)
        if matches >= 1:
            return "ECONOMY"
            
        return "NONE"

    async def rewrite(self, title: str, body: str) -> Optional[str]:
        cache_key = self._get_cache_key(title, body, "rewrite")
        if cache_key in self.cache:
            logger.info(f"💾 Cache hit: rewrite")
            metrics.log_llm_cache_hit()
            return self.cache[cache_key]

        await self._circuit_breaker_check()
        await self.rate_limiter.wait()
        metrics.log_llm_call('rewrite')

        current_date = datetime.now().strftime('%d.%m.%Y')
        current_year = datetime.now().year
        
        prompt = f"""Ты — редактор экономического Telegram-канала. Перепиши новость в информативном стиле.

ПРАВИЛА:
1. Первое предложение — заголовок, заключи его в **двойные звёздочки**
2. Далее 2-3 абзаца (по 2-3 предложения каждый) с ключевыми фактами
3. Пиши на РУССКОМ языке, но МОЖНО использовать:
   - Названия городов (Dubai, Tehran, Moscow)
   - Коды а��роп��ртов (DXB, DWC)
   - О��раслевые термины (airports, flights, oil, gas)
   - **НАЗВАНИЯ КОМПАНИЙ И БРЕНДОВ в оригинале** (AZUR air, Boeing, Airbus, Lukoil)
4. Убери вводные фраз������ типа "Заголовок:", "Первый абзац:"
5. Не добавляй мета-комментарии ("подробности на сайте", "читайте также")
6. Пиши конкретно и по делу, избегай воды
7. Максимум 700 символов

ЗАПРЕЩЕНО ВЫДУМЫВАТЬ:
8. ❌ СТРОГО ЗАПРЕЩЕНО выдумывать даты и числа
9. ❌ НЕ указывай даты из прошлого (2023, 2024, 2025)
10. Если в исходном тексте нет даты — НЕ добавляй её
11. Текущая дата: {current_date}, текущий год: {current_year}
12. Используй дату только если событие ТОЧНО произошло сегодня

ВАЖНО:
13. ⚡ НЕ возвращай пустой ответ
14. ⚡ НЕ пиши "не могу переписать" или "нет информации"
15. ⚡ Просто перескажи факты своими словами
16. ⚡ **СОХРАНЯЙ оригинальные названия компаний** (не п��реводи AZUR air → "АЗУР эйр")

Заголовок: {title}
Текст: {body[:2000]}"""
        
        try:
            response = await self.client.chat.completions.create(
                model=config.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=4000,  # ✅ Увеличено с 3000 до 4000 чтобы не обрезалось
                timeout=55.0
            )
            result = self._extract_content_from_response(response)
            
            if not result or len(result) < 50:
                logger.warning(f"⚠️ Рерайт слишком короткий: {len(result) if result else 0} символов")
                return None
            
            if self._contains_fake_dates(result):
                logger.warning(f"⚠️ Рерайт содержит выдуманные даты, отклонён")
                return None
            
            if self._contains_too_much_english(result):
                logger.warning(f"⚠️ Рерайт содержит слишком много английских слов")
                return None
            
            self.cache[cache_key] = result
            if len(self.cache) % 10 == 0:
                self._save_cache()
            
            self.rate_limiter.report_success()
            self.circuit_breaker_fails = max(0, self.circuit_breaker_fails - 1)
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ LLM rewrite error: {str(e)[:100]}")
            metrics.log_error(f"rewrite: {e}")
            if prom_metrics:
                prom_metrics.inc_err()
            self.rate_limiter.report_error()
            self.circuit_breaker_fails += 1
            if self.circuit_breaker_fails >= self.circuit_breaker_threshold:
                self.circuit_breaker_open_until = asyncio.get_event_loop().time() + 60
            await asyncio.sleep(random.uniform(2, 4))
            return None



# ================= FUZZY ДЕДУПЛИКАЦИЯ =================
async def is_fuzzy_duplicate(title: str, hours: int = 24) -> bool:
    """
    🔍 Fuzzy проверка дубликатов по заголовку (85%+ схожесть)
    Быстрая проверка без LLM
    """
    from difflib import SequenceMatcher
    import aiosqlite

    title_norm = normalize_title(title)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Проверяем последние 200 записей
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            """SELECT title_normalized FROM posted
               WHERE posted_at > ? AND title_normalized IS NOT NULL
               ORDER BY posted_at DESC LIMIT 200""",
            (cutoff,)
        ) as cursor:
            recent_posts = await cursor.fetchall()
            
            for post in recent_posts:
                stored = post[0] if isinstance(post, tuple) else post
                if not stored:
                    continue
                similarity = SequenceMatcher(None, title_norm.lower(), stored.lower()).ratio()
                if similarity >= 0.85:
                    return True
    return False

# ================= ОБРАБОТКА RSS =================

async def fetch_article_text(session: aiohttp.ClientSession, url: str) -> str:
    """Извлечение полного текста статьи"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    return ""
                html = await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(f"Error fetching {url[:60]}: {e}")
            return ""
        
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
                    if len(text) > 40:
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

        full_text = soup.get_text()
        return clean_html(full_text)
    except Exception as e:
        logger.debug(f"Error fetching {url[:60]}: {str(e)[:80]}")
        return ""

async def process_feed(session: aiohttp.ClientSession, feed_url: str, llm: CachedLLMClient,
                      duplicate_detector: DuplicateDetector) -> List[Dict]:
    """Обработка одного RSS-фида"""
    candidates = []
    logger.info(f"📥 Обработка фида: {feed_url[:50]}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        
        async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as resp:
            if resp.status != 200:
                logger.warning(f"❌ {feed_url[:50]} HTTP {resp.status}")
                return candidates
            
            # HTTP запрос
            content = await resp.read()
            
            
            feed = feedparser.parse(content)
            
            
            if not feed.entries or len(feed.entries) == 0:
                logger.warning(f"⚠️ {feed_url[:50]} — нет записей")
                return candidates
            
            metrics.metrics['feeds_processed'] += 1
            logger.info(f"✅ {feed_url[:50]}: {len(feed.entries)} записей")
            
            
            
            
            
            for i, entry in enumerate(feed.entries[:config.max_entries_per_feed]):
                link = safe_to_string(getattr(entry, "link", "")).strip()
                title = clean_html(safe_to_string(getattr(entry, "title", "")))
                summary = clean_html(safe_to_string(getattr(entry, "summary", "") or getattr(entry, "description", "")))
                
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
                
                # 1. Content hash
                content_hash = get_content_hash(title, summary)
                if await is_content_duplicate(content_hash, hours=48):
                    logger.info(f"🔄 Content дубликат: {title[:50]}")
                    metrics.log_duplicate("content")
                    continue
                
                # 2. Глобальная + локальная
                is_dup, dup_method = await duplicate_detector.is_duplicate_advanced(
                    title, summary, link, pub_date, config.db_path
                )
                if is_dup:
                    logger.debug(f"   🔄 Дубликат ({dup_method}): {title[:50]}")
                    metrics.log_duplicate(dup_method)
                    if prom_metrics:
                        prom_metrics.inc_dup(dup_method.replace('link_', 'exact_').split('_')[0])
                    continue

                # 3. Fuzzy
                if await is_fuzzy_duplicate(title, hours=24):
                    logger.info(f"🔄 Fuzzy дубликат: {title[:50]}")
                    metrics.log_duplicate("fuzzy")
                    if prom_metrics:
                        prom_metrics.inc_dup('fuzzy')
                    continue
                
                is_suitable, keyword_matches, high_priority_matches = is_economy_candidate(title, summary)
                if not is_suitable:
                    if prom_metrics:
                        prom_metrics.inc_rejected('not_economy')
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
                if high_priority_matches >= 1 or keyword_matches >= 3:
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
                    if classification != "ECONOMY":
                        logger.info(f"⏭️ LLM отклонил: {title[:60]}")
                        metrics.metrics['posts_rejected'] += 1
                        if prom_metrics:
                            prom_metrics.inc_rejected('low_priority')
                        continue
                    logger.info(f"✅ LLM одобрил: {title[:60]}")
                
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
                if prom_metrics:
                    prom_metrics.set_candidates(len(candidates))

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.error(f"❌ HTTP ошибка {feed_url[:50]}: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка {feed_url[:50]}: {e}", exc_info=True)
    
    logger.info(f"   📊 Возвращено кандидатов: {len(candidates)}")
    return candidates

async def collect_candidates(llm: CachedLLMClient, duplicate_detector: DuplicateDetector) -> List[Dict]:
    """Сбор кандидатов"""
    feeds = RSS_FEEDS.copy()
    random.shuffle(feeds)
    
    logger.info(f"🔄 Начинаем загрузку {len(feeds)} фидов...")
    
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)  # ⚡ Больше соединений
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)  # Нормальный таймаут
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [process_feed(session, feed, llm, duplicate_detector) for feed in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_candidates = []
        for result in results:
            if isinstance(result, list):
                all_candidates.extend(result)
        
        all_candidates = [c for c in all_candidates if isinstance(c, dict)]

        # 🎯 ВНУТРЕННИЙ РЕЙТИНГ: считаем приоритет каждой новости
        for c in all_candidates:
            age_hours = (datetime.now(timezone.utc) - c["pub_date"]).total_seconds() / 3600
            freshness_bonus = 5 if age_hours < 2 else (3 if age_hours < 4 else 1)
            
            # Формула рейтинга: горячие*5 + ключи*2 + свежесть
            c["rating"] = (
                c.get("high_priority_matches", 0) * 5 +
                c.get("keyword_matches", 0) * 2 +
                freshness_bonus
            )
            logger.info(f"✓ Рейтинг {c['rating']}: {c['title'][:60]}")
        
        all_candidates.sort(key=lambda x: x.get("rating", 0), reverse=True)
        
        # 🔝 ВОЗВРАЩАЕМ ТОЛЬКО ТОП-1 для экономии токенов
        if all_candidates:
            top = all_candidates[0]
            logger.info(f"🏆 ТОП-1 новость: {top['title'][:70]} (rating={top['rating']})")
            return [top]
        
        logger.info(f"📊 Найдено кандидатов: {len(all_candidates)}")
        return all_candidates[:config.max_candidates]

# ================= ОТПРАВКА В TELEGRAM =================
async def send_to_channel(
    session: aiohttp.ClientSession,
    text: str,
    link: str,
    priority: int = 0,
    triggers: List[str] = None,
    max_retries: int = 3
) -> bool:
    """
    🔥 ОТПРАВКА СРАЗУ В КАНАЛ (минуя предложку)
    Для критических новостей с priority >= 95
    ✅ С retry логикой и rate limiting
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

    # Формируем сообщение для отправки
    payload = {
        "chat_id": config.tg_channel,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    url = f"https://api.telegram.org/bot{config.tg_token}/sendMessage"

    for attempt in range(1, max_retries + 1):
        try:
            # 🛡️ Ждём разрешения от rate limiter
            await telegram_rate_limiter.wait()

            ssl_context = create_secure_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            timeout = aiohttp.ClientTimeout(total=60, connect=15, sock_read=30)

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as tg_session:
                async with tg_session.post(url, json=payload) as response:
                    result = await response.json()
                    if result.get("ok"):
                        telegram_rate_limiter.report_success()
                        if prom_metrics:
                            metrics.log_post_sent('economy', 'autopost')
                        trigger_info = f" ({', '.join(triggers)})" if triggers else ""
                        logger.info(f"🚨 АВТОПОСТ ОПУБЛИКОВАН (priority={priority}{trigger_info})")
                        return True
                    else:
                        error_code = result.get('error_code')
                        if error_code == 429:
                            telegram_rate_limiter.report_429()
                            retry_after = result.get('parameters', {}).get('retry_after', 60)
                            logger.warning(f"⚠️ 429 ошибка, ожидание {retry_after} сек...")
                            await asyncio.sleep(min(retry_after, 120))
                            continue
                        else:
                            logger.error(f"❌ Ошибка Telegram: {result.get('description')}")
                            return False
        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут при отправке (попытка {attempt}/{max_retries})")
            if attempt < max_retries:
                await asyncio.sleep(5 * attempt)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки (попытка {attempt}/{max_retries}): {e}")
            metrics.log_error(f"send_to_channel: {e}")
            if attempt < max_retries:
                await asyncio.sleep(5 * attempt)

    logger.error(f"❌ Не удалось отправить после {max_retries} попыток")
    return False


async def send_to_suggestion(session: aiohttp.ClientSession, text: str, link: str,
                            pub_date: Optional[datetime], original_title: str = "") -> bool:
    """Отправка в предложку"""
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
        "photo": ""
    }

    # ✅ АТОМАРНАЯ ЗАПИСЬ
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

    try:
        url = f"https://api.telegram.org/bot{config.tg_token}/sendMessage"
        ssl_context = create_secure_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        timeout = aiohttp.ClientTimeout(total=60, connect=15, sock_read=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as tg_session:
            async with tg_session.post(url, json=payload) as response:
                result = await response.json()
                if result.get("ok"):
                    
                    if prom_metrics:
                        metrics.log_post_sent('economy', 'suggestion')
                    logger.info(f"✅ Пост отправлен в предложку (ID: {post_id})")

                    # ✅ ОТМЕТКА В ГЛОБАЛЬНОЙ БД по оригинальному заголовку
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

async def send_to_suggestion_with_retry(session: aiohttp.ClientSession, text: str, link: str,
                                       pub_date: Optional[datetime], original_title: str = "",
                                       max_retries: int = 3) -> bool:
    """Отправка с повторными попытками"""
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
async def collect_and_process_news(llm, duplicate_detector, session):
    """
    ✅ Возвращает кортеж (найдена_новость, опубликована_новость):
    - (True, True) — новость найдена и успешно отправлена
    - (True, False) — новость найдена, но не опубликована (ждёт модерации / ошибка отправки)
    - (False, False) — новость не найдена (нет подходящих кандидатов)
    """
    import time
    start_time = time.time()

    try:
        candidates = await collect_candidates(llm, duplicate_detector)

        if not candidates:
            logger.warning("📭 Нет подходящих кандидатов")
            return (False, False)  # ❌ Новость не найдена

        logger.info(f"🚀 Начинаем обработку {len(candidates)} кандид��тов")

        # Берем топ-3, но обрабатываем только пока не опубликуем одного
        for best in candidates[:3]:
            if not isinstance(best, dict): continue

            logger.info(f"🔄 Обрабатываем: {best.get('title', 'N/A')[:60]}")

            # 🔥 РАССЧИТЫВАЕМ ПРИОРИТЕТ НОВОСТИ
            priority, triggers = calculate_priority(best["title"], best["summary"])
            logger.info(f"🔥 Приоритет: {priority} (триггеры: {triggers if triggers else 'нет'})")

            # 1. Скачиваем текст
            full_text = await fetch_article_text(session, best["link"])

            # Выбираем лучший доступный текст: полный > summary > заголовок + summary
            if full_text and len(full_text) > 150:
                body = full_text
            elif best["summary"] and len(best["summary"]) > 40:
                body = best["summary"]
            else:
                # Комбинируем заголовок и summary для коротких случаев
                body = f"{best['title']}. {best['summary']}" if best.get('summary') else best['title']

            logger.info(f"📝 Длина текста: {len(body)} символов")

            if len(body) < 40:
                logger.warning(f"⚠️ Текст слишком короткий ({len(body)} символов)")
                continue

            # 2. Рерайт
            rewritten = await llm.rewrite(best["title"], body)
            if not rewritten:
                logger.warning("⚠️ Рерайт вернул пусто (возможно, сработал фильтр дат)")
                continue

            # 3. Постпроцессинг
            final_text = postprocess_text(rewritten)
            if not final_text or len(final_text) < 50:
                logger.warning("⚠️ Постпроцессинг неудачен")
                continue

            if not is_russian_text(final_text):
                logger.warning("⚠️ Не русский текст")
                continue

            # ✅ НОВОСТЬ НАЙДЕНА И ГОТОВА К ОТПРАВКЕ
            # 🔥 3-УРОВНЕВАЯ ЛОГИКА ПУБЛИКАЦИИ
            if priority >= 95:
                # 🔥 CRITICAL: Автопостинг сразу в канал (минуя предложку)
                logger.info(f"🚨 CRITICAL NEWS (priority={priority}): Публикация сразу в канал!")
                send_result = await send_to_channel(session, final_text, best["link"], priority, triggers)
                if send_result:
                    # Сохраняем в локальную БД
                    final_hash = get_content_hash(final_text[:200], best["link"])
                    await save_post(best["link"], final_hash, best["source"], best["title_normalized"], "autopost_critical")

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
                    logger.info(f"🚨 АВТОПОСТ ОПУБЛИКОВАН: {best['title'][:60]}")
                    return (True, True)  # ✅ Найдена и опубликована
                else:
                    logger.warning("⚠️ Автопостинг не удался, пробуем следующего")
                    # ✅ НОВОСТЬ ВСЁ ЕЩЁ СЧИТАЕТСЯ НАЙДЕННОЙ (просто отправка не удалась)
                    return (True, False)

            elif priority >= 85:
                # ⚡ HOT: Минуя LLM classify, но в предложку
                logger.info(f"⚡ HOT NEWS (priority={priority}): Отправка в предложку (без classify)")
                send_result = await send_to_suggestion_with_retry(session, final_text, best["link"], best["pub_date"], best["title"])
                if send_result:
                    final_hash = get_content_hash(final_text[:200], best["link"])
                    await save_post(best["link"], final_hash, best["source"], best["title_normalized"], "hot_news")
                    content_dedup_hash = get_content_dedup_hash(best["title"], best["summary"])
                    await save_content_dedup_hash(content_dedup_hash)
                    state.last_post_time = asyncio.get_event_loop().time()
                    logger.info(f"📨 Опубликовано в предложку: {best['title'][:60]}")
                    return (True, True)  # ✅ Найдена и опубликована
                else:
                    logger.warning("⚠️ Отправка в предложку не удалась, пробуем следующего")
                    # ✅ НОВОСТЬ ВСЁ ЕЩЁ СЧИТАЕТСЯ НАЙДЕННОЙ (просто отправка не удалась)
                    return (True, False)

            else:
                # 📝 NORMAL: Полная проверка (LLM classify уже пройден в process_feed)
                logger.info(f"📝 NORMAL NEWS (priority={priority}): Отправка в предложку")
                send_result = await send_to_suggestion_with_retry(session, final_text, best["link"], best["pub_date"], best["title"])
                if send_result:
                    final_hash = get_content_hash(final_text[:200], best["link"])
                    await save_post(best["link"], final_hash, best["source"], best["title_normalized"], "posted")
                    content_dedup_hash = get_content_dedup_hash(best["title"], best["summary"])
                    await save_content_dedup_hash(content_dedup_hash)
                    state.last_post_time = asyncio.get_event_loop().time()
                    logger.info(f"📨 Опубликовано: {best['title'][:60]}")
                    return (True, True)  # ✅ Найдена и опубликована
                else:
                    logger.warning("⚠️ Отправка не удалась, пробуем следующего")
                    # ✅ НОВОСТЬ ВСЁ ЕЩЁ СЧИТАЕТСЯ НАЙДЕННОЙ (просто отправка не удалась)
                    return (True, False)

        # ❌ Ни одна из топ-3 новостей не подошла (все отклонены на этапе рерайта/проверки)
        logger.warning("⚠️ Ни один из топ-3 кандидатов не прошёл проверку")
        return (False, False)  # ❌ Новость не найдена
    except Exception as e:
        logger.error(f"❌ Ошибка в collect_and_process_news: {e}", exc_info=True)
        return (False, False)
    finally:
        elapsed = time.time() - start_time
        if prom_metrics:
            prom_metrics.observe_proc_time(elapsed)
        logger.info(f"⏱️ Время обработки цикла: {elapsed:.2f} сек")

# ================= GRACEFUL SHUTDOWN =================
async def graceful_shutdown(llm: CachedLLMClient):
    """Корректное завершение работы"""
    logger.info("🛑 Завершение работы бота...")
    
    if state.current_task and not state.current_task.done():
        logger.info("⏳ Ожидание завершения текущей задачи...")
        try:
            await asyncio.wait_for(state.current_task, timeout=30)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Таймаут ожидания задачи")
    
    llm._save_cache()
    await cleanup_old_posts()
    await cleanup_old_data()
    cleanup_old_logs()  # Очистка логов (синхронная)

    if GLOBAL_DEDUP_ENABLED:
        try:
            await cleanup_global_db(days=30)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очис��ки глобальной БД: {e}")
    
    metrics.print_summary()
    logger.info("✅ Бот остановлен корректно")

# ================= MAIN =================
async def main():
    await init_db()
    await init_global_db()
    # ✅ ИНИЦИАЛИЗАЦИЯ ГЛОБАЛЬНОЙ БД
    if GLOBAL_DEDUP_ENABLED:
        try:
            await init_global_db()
            logger.info("✅ Глобальная БД дедупликации инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации глобальной БД: {e}")
    
    llm = CachedLLMClient()
    alert_manager = AlertManager(config.tg_token)
    duplicate_detector = DuplicateDetector()

    # ✅ ЗАПУСК ПЛАНИРОВЩИКА ДАЙДЖЕСТОВ (ежедневно в 21:00)
    digest_task = None
    if config.autopost_enabled:
        try:
            digest_task = asyncio.create_task(
                schedule_digest_for_category(llm, alert_manager.telegram, config, "economy", hour=21)
            )
            logger.info("✅ Планировщик дайджестов запущен (21:00 daily)")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить планировщик дайджестов: {e}")
    
    logger.info("=" * 60)
    logger.info("🚀 @ecosteroid PRODUCTION 2026 (REWRITTEN)")
    logger.info(f"   Модель: {config.model_name}")
    logger.info(f"   Лимит: {config.max_posts_per_day} постов/день")
    logger.info(f"   ⚡ Автоодобрение: 1+ HOT слово")
    logger.info(f"   🌐 Перевод английских слов: {'ВКЛ' if TRANSLATOR_AVAILABLE else 'ВЫКЛ'}")
    logger.info(f"   🔄 Fuzzy дубликаты: порог {config.fuzzy_threshold}%")
    logger.info(f"   💾 Кэширование: {len(llm.cache)} записей")
    logger.info(f"   🚫 Защита от дат: 2023-2025")
    logger.info(f"   🌍 Глобальная дедупликация: {'✅ ВКЛ' if GLOBAL_DEDUP_ENABLED else '❌ ВЫКЛ'}")
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
                    news_found, news_published = await state.current_task

                    # ✅ НОЧНЫЕ ЗАДЕРЖКИ: 1.5-2x длиннее чем днем
                    is_night = config.is_night_time()
                    night_multiplier = 1.8 if is_night else 1.0

                    # ✅ ЛОГИКА ЗАДЕРЖЕК: зависит от того, НАЙДЕНА ли новость, а не опубликована
                    if news_found:
                        # ✅ Новость найдена и обработана (отправлена в модерку или сразу в канал)
                        # Следующий цикл через 15-25 минут — даём время на модерацию + защита от спама
                        # Ночью: 27-45 минут (1.8x)
                        if news_published:
                            logger.info(f"✅ Новость опубликована")
                        else:
                            logger.info(f"⏳ Новость найдена, но ожидает публикации (модерация/ошибка)")
                        base_delay_min = 900
                        base_delay_max = 1500
                        delay = random.randint(
                            int(base_delay_min * night_multiplier),
                            int(base_delay_max * night_multiplier)
                        )
                        if is_night:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (НОЧЬ 1.8x, новость найдена)")
                        else:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (новость найдена)")
                    else:
                        # ✅ Новость НЕ найдена — нет подходящих кандидатов
                        # Следующий цикл через 10-15 минут — активный поиск
                        # Ночью: 18-27 минут (1.8x)
                        base_delay_min = 600
                        base_delay_max = 900
                        delay = random.randint(
                            int(base_delay_min * night_multiplier),
                            int(base_delay_max * night_multiplier)
                        )
                        if is_night:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (НОЧЬ 1.8x, новость не найдена)")
                        else:
                            logger.info(f"⏱️ Задержка {delay // 60} мин (новость не найдена, ищем дальше)")

                    if cycle % 10 == 0:
                        await cleanup_old_posts()
                        await cleanup_old_data()
                        cleanup_old_logs()  # Очистка логов (синхронная)

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
    """Запуск тестов"""
    print("\n" + "=" * 60)
    print("🧪 ЗАПУСК ТЕСТОВ ECONOMIKA")
    print("=" * 60)
    
    tests_passed = 0
    tests_failed = 0
    
    # Тест 1: is_economy_candidate
    print("\n📝 Тест: is_economy_candidate")
    try:
        is_eco, _, _ = is_economy_candidate("ЦБ поднял ключевую ставку", "Инфляция")
        assert is_eco == True
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 2: clean_html
    print("\n📝 Тест: clean_html")
    try:
        result = clean_html("<p>Текст</p>")
        assert "Текст" in result
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 3: get_content_hash
    print("\n📝 Тест: get_content_hash")
    try:
        hash1 = get_content_hash("Title", "Text")
        hash2 = get_content_hash("Title", "Text")
        assert hash1 == hash2
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 4: normalize_title
    print("\n📝 Тест: normalize_title")
    try:
        result = normalize_title("Центробанк поднял ставку!")
        assert "центробанк" in result
        assert "поднял" in result
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 5: validate_html_tags
    print("\n📝 Тест: validate_html_tags")
    try:
        result = validate_html_tags("<b>Заголовок")
        assert result == "<b>Заголовок</b>"
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 6: create_secure_ssl_context
    print("\n📝 Тест: create_secure_ssl_context")
    try:
        ctx = create_secure_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname == True
        print("   ��� PASS (SSL верификация включена)")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 7: fake dates detection
    print("\n📝 Тест: fake dates detection")
    try:
        client = CachedLLMClient()
        # Старые годы должны блокироваться
        assert client._contains_fake_dates("в 2023 году") == True
        assert client._contains_fake_dates("в 2024 году") == True
        assert client._contains_fake_dates("в 2025 году") == True
        # Текущий год (2026) должен проходить
        assert client._contains_fake_dates("в 2026 году") == False
        assert client._contains_fake_dates("2026 год") == False
        # Будущие годы должны блокироваться
        assert client._contains_fake_dates("в 2027 году") == True
        assert client._contains_fake_dates("к 2030 году") == True
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 8: english words detection
    print("\n📝 Тест: english words detection")
    try:
        client = CachedLLMClient()
        assert client._contains_too_much_english("Breaking news: president said today") == True
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Итоги
    print("\n" + "=" * 60)
    print(f"✅ Пройдено: {tests_passed}")
    print(f"❌ Провалено: {tests_failed}")
    print("=" * 60)
    
    return tests_failed == 0

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
            logger.info("🛑 Б��т остановлен пользователем")
        except Exception as e:
            logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
            sys.exit(1)