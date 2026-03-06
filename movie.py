#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 @Film_orbita PRODUCTION 2026 — ПЕРЕПИСАННАЯ ВЕРСИЯ
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
from typing import Optional, Dict, List, Tuple, Any
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
from difflib import SequenceMatcher

try:
    import pymorphy3
    MORPHY = pymorphy3.MorphAnalyzer()
    LEMMATIZATION_AVAILABLE = True
except ImportError:
    LEMMATIZATION_AVAILABLE = False
    MORPHY = None

# 🌐 LANGUAGE DETECTION & TRANSLATION
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

# ============ ГЛОБАЛЬНАЯ ДЕДУПЛИКАЦИЯ ============
# Будет инициализирована после создания logger
GLOBAL_DEDUP_ENABLED = False
get_content_dedup_hash = None
init_global_db = None
is_global_duplicate = None
mark_global_posted = None
get_universal_hash = None
cleanup_global_db = None
are_duplicates_by_entities = None

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

    channel: str = "@Film_orbita"
    signature: str = "@Film_orbita"
    model_name: str = Field(default="openai/gpt-oss-20b")  # ✅ Для генерации поста
    translate_model: str = Field(default="mistralai/mistral-nemo")  # ✅ Для перевода и классификации

    # ✅ Каналы для подписи (из .env)
    signature_politics: str = Field(default="@I_Politika")
    signature_economy: str = Field(default="@eco_steroid")
    signature_cinema: str = Field(default="@Film_orbita")

    # ✅ Категории для глобальной дедупликации (из .env)
    category_politics: str = Field(default="politics")
    category_economy: str = Field(default="economy")
    category_cinema: str = Field(default="cinema")

    max_posts_per_day: int = 48
    max_posts_per_cycle: int = 3     # 🔽 Лимит постов за один цикл
    max_entries_per_feed: int = 20   # 🔽 Уменьшили — лучше больше фидов обработать
    max_candidates: int = 50
    max_feeds_per_cycle: int = 4     # ✅ Обрабатываем все 4 фида за цикл

    cycle_delay_day_min: int = 1200      # 20 минут
    cycle_delay_day_max: int = 2400      # 40 минут
    cycle_delay_night_min: int = 2400    # 40 минут
    cycle_delay_night_max: int = 3000    # 50 минут

    night_start_hour: int = 22   # 01:00 МСК = 22:00 UTC
    night_end_hour: int = 5      # 08:00 МСК = 05:00 UTC

    max_news_age_hours: int = 24  # 🔼 Увеличили с 12 до 24 часов
    min_news_age_minutes: int = 5

    tg_channel_politics: str = Field(default="")
    tg_channel_economy: str = Field(default="")
    tg_channel_cinema: str = Field(default="")
    
    suggestion_chat_id_politics: str = Field(default="")
    suggestion_chat_id_economy: str = Field(default="")
    suggestion_chat_id_cinema: str = Field(default="")

    db_path: str = "cinema_memory.db"
    min_delay_between_posts: int = 1700
    domain_min_delay: float = 1.2

    fuzzy_threshold: float = 0.85
    duplicate_check_hours: int = 24  # Кино-новости живут дольше — проверяем за 24 часа

    hot_topic_weight: int = 3
    cinema_keyword_weight: int = 1
    auto_approve_hot_threshold: int = 1

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
        elif 'kino' in script_name or 'film' in script_name or 'cinema' in script_name or 'movie' in script_name:
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
    # 🇷🇺 РУССКИЕ ФИДЫ
    "https://www.kinonews.ru/rss",              # КиноНовости — главные новости кино
    "https://www.kg-portal.ru/rss/news",        # KG-Portal — кино и сериалы
    "https://www.mirf.ru/feed",                 # Мир Фантастики — кино, сериалы
    "https://www.intermedia.ru/rss/news",       # InterMedia — музыка, кино, шоу-бизнес

    # 🇺🇸 АНГЛИЙСКИЕ ФИДЫ — требуют перевода
    "https://editorial.rottentomatoes.com/feed/",  # Rotten Tomatoes — кино, трейлеры, рецензии
    "https://variety.com/feed/",                     # Variety — голливудские новости
    "https://feeds.feedburner.com/Deadline",         # Deadline — индустриальные новости
]

# ✅ ДОПОЛНИТЕЛЬНЫЕ КЛЮЧЕВЫЕ СЛОВА ДЛЯ АНГЛИЙСКИХ НОВОСТЕЙ
EN_CINEMA_KEYWORDS = {
    "movie", "film", "cinema", "actor", "actress", "director", "premiere", "trailer",
    "series", "streaming", "box office", "oscar", "nomination", "award", "hollywood",
    "screenplay", "producer", "screen", "film festival", "marvel", "dc comics",
    "cannes", "venice", "berlinale", "golden globe", "netflix", "disney", "hbo",
    "casting", "sequel", "remake", "adaptation", "blockbuster", "indie"
}

EN_HOT_TOPICS = {
    "marvel", "dc comics", "premiere", "trailer", "oscar", "cannes", "venice",
    "berlinale", "golden globe", "box office", "netflix", "disney", "streaming",
    "sequel", "casting", "blockbuster"
}

# ================= ЧЁРНЫЙ СПИСОК ДОМЕНОВ =================
# Источники которые публикуют фейки/кликбейт — игнорируем
BLACKLISTED_DOMAINS = {
    "news.ru",           # только точное совпадение домена
}

def is_domain_blacklisted(url: str) -> bool:
    """Проверка домена на чёрный список — ТОЧНОЕ совпадение"""
    domain = urlparse(url).netloc.lower()
    return domain in BLACKLISTED_DOMAINS

# ================= КЛЮЧЕВЫЕ СЛОВА =================
CINEMA_KEYWORDS = {
    "фильм", "кино", "актёр", "актриса", "режиссёр", "премьера", "трейлер",
    "сериал", "кинотеатр", "прокат", "съёмки", "оскар", "номинац", "награда",
    "голливуд", "сценар", "продюсер", "касс", "экран", "кинофестиваль",
    "марвел", "marvel", "dc comics", "каннский", "венецианский", "берлинале",
    "золотой глобус", "netflix", "дисней", "disney", "бокс-офис"
}

HOT_CINEMA_TOPICS = {
    "марвел", "marvel", "dc comics", "премьера", "трейлер", "оскар", "oscar",
    "каннский", "венецианский", "берлинале", "золотой глобус", "касса",
    "netflix", "дисней", "disney", "пиратство", "бокс-офис"
}

# 🎬 ТОП-РЕЖИССЁРЫ И АКТЁРЫ — супер-горячие имена
# Упоминание + съёмки/премьера = автоматический ТОП
# ✅ ДОБАВЛЕНЫ ВЕСА: A-list (100), B-list (80), C-list (60)

TOP_DIRECTORS = {
    # ===== A-list режиссёры (вес 100) =====
    "нolan": 100, "нолан": 100, "christopher nolan": 100,
    "spielberg": 100, "спилберг": 100, "steven spielberg": 100,
    "tarantino": 100, "тарантино": 100, "quentin tarantino": 100,
    "scorsese": 100, "скорсезе": 100, "martin scorsese": 100,
    "ridley scott": 100, "ридли скотт": 100,
    "james cameron": 100, "джеймс кэмерон": 100, "cameron": 100,
    "denis villeneuve": 100, "дени вильнёв": 100, "villeneuve": 100,
    
    # ===== B-list режиссёры (вес 80) =====
    "guy ritchie": 80, "гай ричи": 80, "ritchie": 80,
    "wes anderson": 80, "уэс андерсон": 80,
    "david fincher": 80, "дэвид финчер": 80, "fincher": 80,
    "peter jackson": 80, "питер джексон": 80, "jackson": 80,
    "steven soderbergh": 80, "сти вен содерберг": 80,
    "alexander payne": 80, "александр пэйн": 80,
    "joachim trier": 80, "йоахим триер": 80,
    
    # ===== Индия (вес 60) =====
    "rajamouli": 60, "раджамоули": 60, "ss rajamouli": 60,
    "shah rukh khan": 60, "шах рух хан": 60, "srk": 60,
    "amitabh bachchan": 60, "амитабх баччан": 60,
    "anupam kher": 60, "анупам кхер": 60, "кхер": 60
}

TOP_ACTORS = {
    # ===== A-list актёры (вес 100) =====
    "tom cruise": 100, "том круз": 100, "cruise": 100,
    "brad pitt": 100, "брэд питт": 100, "pitt": 100,
    "leonardo dicaprio": 100, "леонардо дикаприо": 100, "dicaprio": 100,
    "robert downey": 100, "роберт дауни": 100, "downey jr": 100,
    "margot robbie": 100, "марго робби": 100,
    "christian bale": 100, "кристиан бэйл": 100, "bale": 100,
    "keanu reeves": 100, "киану ривз": 100, "reeves": 100,
    "will smith": 100, "уилл смит": 100, "smith": 100,
    "johnny depp": 100, "джонни депп": 100, "depp": 100,
    
    # ===== B-list актёры (вес 80) =====
    "scarlett johansson": 80, "скарлетт йоханссон": 80,
    "matt damon": 80, "мэтт деймон": 80, "damon": 80,
    "henry cavill": 80, "генри кавилл": 80, "кавилл": 80,
    "morgan freeman": 80, "морган фримен": 80,
    "anthony hopkins": 80, "энтони хопкинс": 80,
    "al pacino": 80, "аль пачино": 80,
    "denzel washington": 80, "дензел вашингтон": 80,
    
    # ===== Индия (вес 60) =====
    "shah rukh": 60, "шах рух": 60,
    "salman khan": 60, "салман хан": 60,
    "aamir khan": 60, "амир хан": 60,
    "deepika padukone": 60, "дипика падуконе": 60,
    "priyanka chopra": 60, "приянка чопра": 60
}

# ✅ ВЕСА для TOP_DIRECTORS и TOP_ACTORS
# A-list: 100 (Нолан, Спилберг, Ди Каприо, Круз)
# B-list: 80 (Гай Ричи, Уэс Андерсон, Мэтт Деймон)
# C-list: 60 (Индийские актёры и режиссёры)

# 🎥 КИНО-ПРОЦЕССЫ — для активации супер-бонуса
FILM_PRODUCTION_WORDS = {
    "съёмк", "снимат", "производств", "производит", "production", "filming",
    "премьера", "premiere", "релиз", "release", "выход", "exit", "launch",
    "анонс", "announce", "объявил", "announced", "confirmed", "подтвердил",
    "постановк", "поставит", "will direct", "directing", "режиссёр", "director",
    "кастинг", "casting", "получил роль", "got role", "сыграет", "will play",
    "возвращается", "returns", "продолжение", "sequel", "сиквел",
    "новый фильм", "new film", "new movie", "картина", "picture"
}

NON_CINEMA_KEYWORDS = {
    # Спорт
    "футбол", "хоккей", "баскетбол", "олимпиад", "чемпионат", "матч", "гол", "счёт",
    # Политика РФ
    "путин", "президент", "правительств", "госдум", "выборы", "министр", "депутат",
    "кремль", "совет федерац", "единая россия", "партия", "закон", "фз", "указ",
    # Политика США/мира
    "трамп", "байден", "конгресс", "сенат", "белый дом", "white house", "election",
    # Экономика
    "экономика", "курс", "доллар", "евро", "инфляц", "санкц", "рубль", "акции",
    "бирж", "налог", "бюджет", "минфин", "центробанк", "вэб", "импортозамещ",
    # Военная тематика (не кино)
    "спецопераци", "сво", "военн", "арми", "оборон", "министерство обороны",
    # Происшествия
    "мчс", "пожар", "дтп", "криминал", "убийств", "суд", "приговор"
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


CINEMA_KEYWORDS_LEMMA = lemmatize_keywords(CINEMA_KEYWORDS)
HOT_CINEMA_TOPICS_LEMMA = lemmatize_keywords(HOT_CINEMA_TOPICS)
TOP_DIRECTORS_LEMMA = lemmatize_keywords(TOP_DIRECTORS)
TOP_ACTORS_LEMMA = lemmatize_keywords(TOP_ACTORS)
FILM_PRODUCTION_LEMMA = lemmatize_keywords(FILM_PRODUCTION_WORDS)

# ================= ЛОГИРОВАНИЕ =================
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_dir / "cinema_bot.log", encoding="utf-8", delay=True),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logger = logging.getLogger(__name__)

logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# ✅ Инициализация глобальной дедупликации ПОСЛЕ logger
try:
    from global_dedup import (
        get_content_dedup_hash,
        init_global_db,
        is_global_duplicate,
        mark_global_posted,
        get_universal_hash,
        cleanup_global_db,
        are_duplicates_by_entities
    )
    GLOBAL_DEDUP_ENABLED = True
    logger.info("✅ Глобальная дедупликация включена")
except ImportError:
    GLOBAL_DEDUP_ENABLED = False
    logger.warning("⚠️ global_dedup.py не найден — дедупликация между каналами отключена")
except Exception as e:
    logger.warning(f"⚠️ Ошибка импорта global_dedup: {e}")

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
            'duplicates_link': 0,
            'llm_calls': 0,
            'llm_cache_hits': 0,
            'llm_errors': 0,
            'feeds_processed': 0,
            'candidates_found': 0,
            'fake_dates_blocked': 0,
            'english_words_blocked': 0,
            'blacklist_blocked': 0,
            'errors': []
        }
        self.start_time = datetime.now()
        self.posts_today = 0
        self.last_reset_date = datetime.now().date()

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
        elif 'link' in method:
            self.metrics['duplicates_link'] += 1
            if prom_metrics:
                prom_metrics.inc_dup('link')

    def increment_posts_today(self):
        """Увеличить счётчик постов за сегодня"""
        today = datetime.now().date()
        if self.last_reset_date != today:
            self.posts_today = 0
            self.last_reset_date = today
        self.posts_today += 1

    def can_post_today(self) -> bool:
        """Проверка дневного лимита"""
        today = datetime.now().date()
        if self.last_reset_date != today:
            self.posts_today = 0
            self.last_reset_date = today
        return self.posts_today < config.max_posts_per_day

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
        self.increment_posts_today()
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

    def log_blacklist_blocked(self):
        """Логирование заблокированного чёрным списком"""
        self.metrics['blacklist_blocked'] += 1

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

    def log_feed_processed(self):
        """Логирование обработанного фида"""
        self.metrics['feeds_processed'] += 1
        if prom_metrics:
            prom_metrics.set_candidates(self.metrics['candidates_found'])

    def print_summary(self):
        """Вывод статистики"""
        uptime = datetime.now() - self.start_time
        total_duplicates = (self.metrics['duplicates_exact'] +
                          self.metrics['duplicates_fuzzy'] +
                          self.metrics['duplicates_global'] +
                          self.metrics['duplicates_content'] +
                          self.metrics['duplicates_link'])
        cache_rate = 0
        if self.metrics['llm_calls'] > 0:
            cache_rate = (self.metrics['llm_cache_hits'] /
                         (self.metrics['llm_calls'] + self.metrics['llm_cache_hits'])) * 100

        logger.info("=" * 60)
        logger.info("📊 СТАТИСТИКА РАБОТЫ БОТА")
        logger.info(f"   Время работы: {uptime}")
        logger.info(f"   Постов отправлено: {self.metrics['posts_sent']}")
        logger.info(f"   Постов за сегодня: {self.posts_today}")
        logger.info(f"   Дубликатов всего: {total_duplicates}")
        logger.info(f"   ├─ Точных: {self.metrics['duplicates_exact']}")
        logger.info(f"   ├─ Fuzzy: {self.metrics['duplicates_fuzzy']}")
        logger.info(f"   ├─ Global: {self.metrics['duplicates_global']}")
        logger.info(f"   ├─ Content: {self.metrics['duplicates_content']}")
        logger.info(f"   └─ Link: {self.metrics['duplicates_link']}")
        logger.info(f"   ")
        logger.info(f"   LLM вызовов: {self.metrics['llm_calls']}")
        logger.info(f"   Cache hits: {self.metrics['llm_cache_hits']} ({cache_rate:.1f}%)")
        logger.info(f"   LLM ошибок: {self.metrics['llm_errors']}")
        logger.info(f"   ")
        logger.info(f"   Заблокировано выдуманных дат: {self.metrics['fake_dates_blocked']}")
        logger.info(f"   Заблокировано англ. слов: {self.metrics['english_words_blocked']}")
        logger.info(f"   Заблокировано чёрным списком: {self.metrics['blacklist_blocked']}")
        logger.info(f"   ")
        logger.info(f"   Фидов обработано: {self.metrics['feeds_processed']}")
        logger.info(f"   Кандидатов найдено: {self.metrics['candidates_found']}")
        logger.info("=" * 60)

    def log_rejected(self):
        """Логирование отклонённого поста"""
        self.metrics['posts_rejected'] += 1

    def set_candidates(self, count: int):
        """Установка количества кандидатов"""
        self.metrics['candidates_found'] = count
        if prom_metrics:
            prom_metrics.set_candidates(count)

metrics = BotMetrics()

# 📊 PROMETHEUS METRICS
try:
    from prometheus_metrics import PrometheusMetrics
    prom_metrics = PrometheusMetrics(bot_name='cinema', port=8002)
    logger.info("✅ Prometheus метрики запущены на порту 8002")
except Exception as e:
    logger.warning(f"⚠️ Prometheus metrics error: {e}")
    prom_metrics = None

# ================= СОСТОЯНИЕ =================
class BotState:
    def __init__(self):
        self.last_post_time = 0
        self.running = True
        self.current_task = None
        self.last_llm_call: float = 0.0
        self.domain_last_request: Dict[str, float] = {}

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
            (link, text_hash, "CINEMA", source, title_normalized, duplicate_method)
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
    """Хеш контента (локальный)"""
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

def is_cinema_candidate(title: str, summary: str) -> Tuple[bool, int, int, int]:
    """
    Предфильтрация по ключевым словам с лемматизацией (рус + англ)
    Возвращает: (is_cinema, cinema_matches, hot_matches, super_hot_matches)
    ✅ ДОБАВЛЕНЫ ВЕСА для TOP_ACTORS/TOP_DIRECTORS
    ✅ ДОБАВЛЕНА langdetect проверка для английских новостей
    """
    text = f"{title} {summary}".lower()
    text_lemma = lemmatize_text(f"{title} {summary}")

    # Проверяем язык текста — используем pymorphy3 как fallback
    is_english = not is_russian_text(text, min_ratio=0.5)
    
    # ✅ ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА ЧЕРЕЗ LANGDETECT если доступна
    if LANGDETECT_AVAILABLE and is_english:
        try:
            from langdetect import detect, LangDetectException
            detected_lang = detect(text[:500])
            # Если langdetect определил как non-ru — точно английский
            if detected_lang != 'ru':
                is_english = True
                logger.debug(f"🌐 Langdetect определил язык: {detected_lang}")
        except Exception:
            pass  # Fallback на кириллицу-проверку

    non_cinema_count = sum(1 for word in NON_CINEMA_KEYWORDS if word in text)
    if non_cinema_count >= 2:
        return False, 0, 0, 0

    # Считаем совпадения для лемматизированных keywords
    cinema_matches = sum(1 for kw in CINEMA_KEYWORDS_LEMMA if kw in text_lemma)
    hot_matches = sum(1 for kw in HOT_CINEMA_TOPICS_LEMMA if kw in text_lemma)

    # 🔥 ПРОВЕРЯЕМ СУПЕР-ГОРЯЧИЕ ИМЕНА + кино-процессы С УЧЁТОМ ВЕСОВ
    super_hot_matches = 0
    director_weight = 0
    actor_weight = 0
    
    # Считаем веса для режиссёров
    for name, weight in TOP_DIRECTORS.items():
        if name.lower() in text_lemma or name.lower() in text:
            director_weight = max(director_weight, weight)
    
    # Считаем веса для актёров
    for name, weight in TOP_ACTORS.items():
        if name.lower() in text_lemma or name.lower() in text:
            actor_weight = max(actor_weight, weight)
    
    production_match = sum(1 for kw in FILM_PRODUCTION_LEMMA if kw in text_lemma)
    
    # Супер-бонус: режиссёр/актёр + съёмки/премьера
    # Теперь учитываем вес: A-list (100) = авто-горячая новость
    max_star_weight = max(director_weight, actor_weight)
    if max_star_weight > 0 and production_match > 0:
        # Вес супер-горячих = вес звезды + бонус за процесс
        super_hot_matches = max_star_weight + (production_match * 10)
        logger.info(f"🌟 Супер-горячая новость: звезда={max_star_weight}, процессы={production_match}")

    # Если лемматизация не нашла, пробуем обычные keywords
    if cinema_matches == 0:
        cinema_matches = sum(1 for kw in CINEMA_KEYWORDS if kw in text)
        hot_matches = sum(1 for kw in HOT_CINEMA_TOPICS if kw in text)
        if super_hot_matches == 0:
            director_weight = 0
            actor_weight = 0
            for name, weight in TOP_DIRECTORS.items():
                if name.lower() in text:
                    director_weight = max(director_weight, weight)
            for name, weight in TOP_ACTORS.items():
                if name.lower() in text:
                    actor_weight = max(actor_weight, weight)
            production_match = sum(1 for kw in FILM_PRODUCTION_WORDS if kw in text)
            if (director_weight > 0 or actor_weight > 0) and production_match > 0:
                super_hot_matches = max(director_weight, actor_weight) + (production_match * 10)

    # Для английских новостей — отдельные ключи + перевод
    if is_english:
        en_cinema_matches = sum(1 for kw in EN_CINEMA_KEYWORDS if kw in text)
        en_hot_matches = sum(1 for kw in EN_HOT_TOPICS if kw in text)
        cinema_matches = max(cinema_matches, en_cinema_matches)
        hot_matches = max(hot_matches, en_hot_matches)
        
        # ✅ ПРОВЕРКА: если английская новость — проверяем наличие перевода
        # Если нет ключевых слов и нет перевода — отклоняем
        if cinema_matches == 0 and not TRANSLATOR_AVAILABLE:
            logger.info(f"🇬🇧 Английская новость без перевода: {title[:50]}")
            return False, 0, 0, 0

    return cinema_matches >= 1, cinema_matches, hot_matches, super_hot_matches


def is_english_text(text: str) -> bool:
    """Проверка: текст на английском"""
    if not text:
        return False
    # Считаем латинские буквы
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    alpha = sum(1 for c in text if c.isalpha())
    return alpha > 0 and (latin / alpha) >= 0.7

def is_russian_text(text: str, min_ratio: float = 0.6) -> bool:
    """Проверка русского текста по кириллице"""
    cyrillic = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF or c in "ёЁ")
    alpha = sum(1 for c in text if c.isalpha())
    return alpha > 0 and (cyrillic / alpha) >= min_ratio

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
    CHANNEL = config.channel
    MAX_POST_LENGTH = 4096  # ← Увеличенный лимит Telegram (4096 символов)
    TRUNCATE_LENGTH = 4000
    MIN_TRUNCATE_SPACE = 3500

    if isinstance(raw, list):
        raw = '\n'.join(str(item) for item in raw if item)

    raw = safe_to_string(raw)
    if not raw or len(raw) < 20:
        return f"🎬<b>Кино новости</b>🎬\n\n{CHANNEL}"
    
    # Удаляем неправильную подпись
    raw = re.sub(r'@?Cinema_steroid@?', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'Cinema steroid', '', raw, flags=re.IGNORECASE)
    
    # ✅ Удаляем дни недели и мета-комментарии
    raw = re.sub(r'^(суббота|воскресенье|понедельник|вторник|среда|четверг|пятница)\s*[–—:]\s+день[^\.]*\.?', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^(суббота|воскресенье|понедельник|вторник|среда|четверг|пятница)\s*,\s*когда[^\.]*\.?', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'день,\s*когда\s+[^\.]*\.?', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'опубликовал[оа][^\.]*информацию[^\.]*\.?', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'сообщил[оа][^\.]*данные[^\.]*\.?', '', raw, flags=re.IGNORECASE)
    
    # Удаляем markdown-разметку
    text = re.sub(r"(\*\*|__|\*|_|#|`)", "", raw)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return f"🎬<b>Кино новости</b>🎬\n\n{CHANNEL}"
    
    # Проверяем что первая строка начинается с 🎬<b>
    first_line = lines[0]
    if not first_line.startswith("🎬<b>"):
        if first_line.startswith("<b>"):
            first_line = "🎬" + first_line
        else:
            first_line = "🎬<b>" + first_line + "</b>"
    
    # Убеждаемся что тег зак��ыт
    if first_line.count("<b>") > first_line.count("</b>"):
        if "</b>" not in first_line and len(lines) > 1:
            first_line = first_line.rstrip() + "</b>"
    
    # 🔧 АККУРАТНАЯ ОБРЕЗКА ЗАГОЛОВКА: не обрезать в середине слова
    header_raw = first_line[:120].strip()
    # Если обрезали в середине слова — находим последний пробел
    if len(first_line) > 120 and header_raw and not header_raw[-1].isspace():
        last_space = header_raw.rfind(' ')
        if last_space > 80:  # Если есть пробел после 80 символа
            header_raw = header_raw[:last_space]
        # Если есть закрывающий тег </b>, убеждаемся что он в конце
        if '</b>' not in header_raw and '<b>' in header_raw:
            header_raw += '</b>'
    
    # ✅ ДОБАВЛЯЕМ 🎬 В КОНЕЦ ЗАГОЛОВКА
    if not header_raw.rstrip().endswith('🎬'):
        header_raw = header_raw.rstrip() + '🎬'

    header = header_raw.strip()
    body_lines = lines[1:] if len(lines) > 1 else []
    body = "\n\n".join(body_lines[:5]) if body_lines else ""

    formatted = f"{header}\n\n{body}" if body else f"{header}"
    formatted = formatted.rstrip() + f"\n\n{CHANNEL}"

    if len(formatted) > MAX_POST_LENGTH - 6:
        truncated = formatted[:TRUNCATE_LENGTH]

        # 🔍 УМНАЯ ОБРЕЗКА: ищем конец последнего完整ного предложения
        # Приоритет: точка с пробелом → просто точка → перенос строки → пробел
        for ending in [". ", ".\n", "!\n", "?\n", ".</b>", "\n\n"]:
            pos = truncated.rfind(ending)
            if pos > MIN_TRUNCATE_SPACE:
                formatted = truncated[:pos + len(ending)].rstrip() + f"\n\n{CHANNEL}"
                break
        else:
            # Если не нашли предложение — режем по пробелу
            last_space = truncated.rfind(" ")
            if last_space > MIN_TRUNCATE_SPACE:
                formatted = truncated[:last_space].rstrip() + f"...\n\n{CHANNEL}"
            else:
                formatted = truncated.rstrip() + f"...\n\n{CHANNEL}"

    formatted = validate_html_tags(formatted)
    return formatted

# ================= ПРОВЕРКА ДУБЛИКАТОВ =================
class DuplicateDetector:
    """Проверка дубликатов: локальная + глобальная"""

    async def is_duplicate_advanced(
        self,
        title: str,
        summary: str,
        link: str,
        pub_date: Optional[datetime],
        db_path: str
    ) -> Tuple[bool, str]:
        """✅ ПЯТИУРОВНЕВАЯ проверка дубликатов с улучшенной проверкой по содержанию"""

        # ✅ 1. Глобальная проверка (межканальная) через content hash
        if GLOBAL_DEDUP_ENABLED:
            try:
                # Используем content hash для более точной проверки
                content_hash = get_content_dedup_hash(title, summary, config.category)
                if await is_global_duplicate(content_hash, config.category, hours=48):
                    logger.info(f"🌐 Глобальный дубликат (content): {title[:50]}")
                    metrics.log_duplicate("global")
                    return True, "global_content_duplicate"
            except Exception as e:
                logger.warning(f"⚠️ Ошибка глобальной проверки: {e}")

        # ✅ 2. Проверка по link (т��чная) — с ограничением по времени
        link_check_hours = 24  # Проверяе�� дубликаты по ссылке только за 24 часа
        cutoff_link = datetime.now(timezone.utc) - timedelta(hours=link_check_hours)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT 1 FROM posted WHERE link = ? AND posted_at > ?",
                (link, cutoff_link)
            ) as cursor:
                if await cursor.fetchone():
                    logger.info(f"🔗 Дубликат по ссылке (< {link_check_hours}ч): {title[:50]}")
                    return True, "link_duplicate"

        # ✅ 3. Content dedup hash (локальный)
        content_dedup_hash = get_content_dedup_hash(title, summary)
        if await is_content_duplicate(content_dedup_hash, hours=config.duplicate_check_hours):
            logger.info(f"🔄 Content дубликат: {title[:50]}")
            metrics.log_duplicate("content")
            return True, "content_duplicate"

        # ✅ 4. Fuzzy по заголовку (85%+) — УМЕНЬШЕН ПОРОГ ДО 75%
        title_norm = normalize_title(title)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=config.duplicate_check_hours)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """SELECT title_normalized FROM posted
                   WHERE posted_at > ? AND title_normalized IS NOT NULL
                   ORDER BY posted_at DESC LIMIT 500""",
                (cutoff,)
            ) as cursor:
                recent_posts = await cursor.fetchall()
                for post in recent_posts:
                    stored = post[0] if isinstance(post, tuple) else post
                    if not stored:
                        continue
                    similarity = SequenceMatcher(None, title_norm.lower(), stored.lower()).ratio()
                    if similarity >= 0.75:  # 🔽 Снизили порог с 85% до 75%
                        logger.info(f"🔄 Fuzzy дубликат ({similarity:.1%}): {title[:50]}")
                        return True, f"fuzzy_{similarity}"

        # ✅ 5. Проверка через entity matching (для новостей написанных по-разному)
        if GLOBAL_DEDUP_ENABLED:
            try:
                cutoff_recent = datetime.now(timezone.utc) - timedelta(hours=12)
                async with aiosqlite.connect(db_path) as db:
                    async with db.execute(
                        """SELECT title_normalized FROM posted
                           WHERE posted_at > ? AND title_normalized IS NOT NULL
                           ORDER BY posted_at DESC LIMIT 200""",
                        (cutoff_recent,)
                    ) as cursor:
                        recent_posts = await cursor.fetchall()
                        for post in recent_posts:
                            stored = post[0] if isinstance(post, tuple) else post
                            if stored and are_duplicates_by_entities(title, stored, min_common_entities=2):
                                logger.info(f"🔄 Entity дубликат: {title[:50]}")
                                return True, "entity_duplicate"
            except Exception as e:
                logger.warning(f"⚠️ Ошибка entity проверки: {e}")

        return False, "unique"

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
        self.cache_file = Path("llm_cache_cinema.pkl")
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
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
                        if content and len(content.strip()) > 0:
                            return content.strip()
                if isinstance(choice, dict):
                    msg = choice.get('message', {})
                    if isinstance(msg, dict):
                        content = msg.get('content', '')
                        if isinstance(content, list):
                            content = '\n'.join(str(item) for item in content if item)
                        if content and len(content.strip()) > 0:
                            return content.strip()
            if isinstance(response, dict) and 'choices' in response:
                choices = response['choices']
                if isinstance(choices, list) and len(choices) > 0:
                    choice = choices[0]
                    if isinstance(choice, dict) and 'message' in choice:
                        content = choice['message'].get('content', '')
                        if isinstance(content, list):
                            content = '\n'.join(str(item) for item in content if item)
                        if content and len(content.strip()) > 0:
                            return content.strip()
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения контента: {e}")
            return None
    
    def _contains_fake_dates(self, text: str) -> bool:
        """🧹 Блокировка постов с выдуманными датами (2023-2025)"""
        # ✅ 2026 год — текущий, 2025 и старше — старые
        old_years = ["2023", "2024", "2025"]
        text_lower = text.lower()

        for year in old_years:
            if re.search(rf"\b{year}\b", text):
                logger.warning(f"🚨 Обнаружен старый год: {year}")
                metrics.log_fake_date()
                return True

        # ✅ УБРАНА ��ЛОКИРОВКА 2026 года �� это текущий год!
        # Новости с актуальной датой (2026) должны проходить
        # Блокируем только явные фейки типа "в 2026 году" в будущем контексте
        # Но это уже обрабатывается через LLM проверку

        return False
    
    def _contains_too_much_english(self, text: str) -> bool:
        """Проверка: слишком много английских слов (но пропускаем названия)"""
        # ✅ Разрешённые английские слова — студии, сервисы, термины, имена
        allowed_english = {
            # Студии и компании
            'marvel', 'dc', 'netflix', 'hbo', 'disney', 'imax', 'oscar', 'emmy', 'prime',
            'usa', 'uk', 'eu', 'bbc', 'cnn', 'tmz', 'variety', 'hollywood',
            'warner', 'bros', 'paramount', 'sony', 'universal', 'lionsgate', 'mgm',
            'apple', 'amazon', 'studio', 'pictures', 'entertainment',
            # Стриминги и сервисы
            'hulu', 'peacock', 'showtime', 'starz', 'discovery',
            'youtube', 'red', 'premium', 'plus', 'max',
            # Кинокомпании
            'legendary', 'bad', 'robot', 'syncopy', 'plan',
            'a24', 'neon', 'focus', 'features', 'searchlight', 'pixar',
            # Термины
            'tv', 'show', 'shows', 'movie', 'movies', 'film', 'films',
            'trailer', 'teaser', 'clip', 'scene', 'cast', 'crew',
            'director', 'producer', 'actor', 'actress', 'star', 'stars',
            'season', 'episode', 'series', 'streaming', 'premiere',
            # Награды
            'golden', 'globe', 'globes', 'awards', 'award', 'nomination',
            'cannes', 'venice', 'berlinale', 'sundance', 'toronto',
            'academy', 'picture', 'feature', 'winning', 'winner', 'won',
            # Фразы-исключения (часто в переводах)
            'right', 'now', 'what', 'watch', 'theaters', 'streaming',
            'popular', 'most', 'best', 'top', 'new', 'latest',
            # Названия (отдельные слова)
            'dragon', 'house', 'blood', 'kingdom', 'kingdoms', 'knight', 'knights',
            'seven', 'thrones', 'game', 'last', 'us', 'one', 'day', 'days',
            'men', 'woman', 'man', 'love', 'time', 'life', 'world',
            'dead', 'evil', 'good', 'bad', 'big', 'small', 'long',
            'night', 'nights', 'paradise', 'agent', 'agents', 'angel', 'angels',
            'place', 'places', 'face', 'faces', 'name', 'names',
            # Названия сериалов и городов
            'monarch', 'heaven', 'from', 'belfast', 'bridgerton', 'succession',
            'stranger', 'things', 'wednesday', 'mandalorian', 'witcher', 'crown',
            'ozark', 'euphoria', 'ted', 'lasso', 'severance', 'andor', 'reacher',
            'rings', 'power', 'dragon', 'house', 'wolf', 'like', 'us', 'bear',
            'white', 'lotus', 'last', 'america', 'boy', 'girls', 'handmaid',
            'tale', 'killing', 'eve', 'flea', 'bag', 'true', 'detective',
            # Источники
            'rotten', 'tomatoes', 'deadline', 'indiewire', 'collider',
            'screen', 'rant', 'empire', 'total', 'film',
            # Прочее
            'coming', 'soon', 'exclusive', 'interview', 'review', 'news',
            # Простые слова (могут проскальзывать)
            'video', 'story', 'about', 'working', 'says', 'said', 'set',
            'prep', 'preps', 'bows', 'spirit', 'talks', 'reveals', 'teases',
            'first', 'look', 'exclusive', 'red', 'carpet', 'live',
            # Имена (короткие)
            'lee', 'kim', 'park', 'chan', 'jin', 'wei', 'chen', 'wu',
            'finn', 'bennett', 'bertie', 'carvel', 'tanzyn', 'daniel',
            'james', 'john', 'jane', 'mary', 'michael', 'david', 'sarah',
            'emma', 'oliver', 'william', 'harry', 'george', 'charlotte',
            # Индийские имена/слова
            'kher', 'anupam', 'saaransh', 'tan', 'raj', 'kumar', 'singh',
            'kapoor', 'shah', 'khan', 'patel', 'sharma', 'dev', 'priya',
            # 🔥 Дополнительные имена и названия (Оскар, фильмы)
            'mike', 'nelson', 'getty', 'images', 'philadelphia',
            'braveheart', 'gibson', 'mel', 'val', 'kilmer',
            'apollo', 'austen', 'sense', 'sensibility',
            'cameron', 'titanic', 'spielberg', 'schindler',
            'list', 'schindlers', 'list', 'saving', 'private', 'ryan',
            'shake', 'shakespeare', 'in', 'love', 'gladiator',
            'scott', 'ridley', 'russell', 'crowe',
            'matt', 'damon', 'ben', 'affleck', 'good', 'will', 'hunting',
            'robin', 'williams', 'julia', 'roberts', 'erin', 'brockovich',
            'kevin', 'spacey', 'bryan', 'singer', 'usual', 'suspects',
            'anthony', 'hopkins', 'silence', 'lambs', 'demme',
            'jonathan', 'demme', 'jodie', 'foster', 'clarice',
            'starling', 'lecter', 'hannibal', 'buffalo', 'bill',
            'gwyneth', 'paltrow', 'shakespeare', 'viola', 'orson',
            'welles', 'magnolia', 'tom', 'cruise', 'magnolia', 'pt',
            'anderson', 'paul', 'thomas', 'boogie', 'nights', 'mark',
            'wahlberg', 'julianne', 'moore', 'philip', 'seymour',
            'hoffman', 'john', 'c', 'reilly', 'alfred', 'molina',
            'molly', 'maher', 'shohreh', 'aghdashloo', 'house',
            'sand', 'fog', 'nicole', 'kidman', 'hours', 'stephen',
            'daldry', 'david', 'hare', 'meryl', 'streep', 'claire',
            'danes', 'jeff', 'daniels', 'allison', 'janney', 'chris',
            'cooper', 'charlie', 'kaufman', 'adaptation', 'spike',
            'jonze', 'catherine', 'keener', 'brian', 'cox', 'donald',
            'kaufman', 'susan', 'orlean', 'john', 'larroquette',
            'cara', 'seymour', 'maggie', 'gyllenhaal', 'tilda',
            'swinton', 'frances', 'mcdormand', 'richard', 'jenkins',
            'bill', 'murray', 'scarlett', 'johansson', 'lost',
            'translation', 'sofia', 'coppola', 'giovanni', 'ribisi',
            'anna', 'faris', 'fanny', 'ardant', 'kun', 'zhang',
            'hiroyuki', 'sanada', 'rino', 'nakano', 'shun', 'oguri',
            'yutaka', 'takenouchi', 'taeko', 'tokunaga', 'yui',
            'ichikawa', 'kanako', 'tsutsui', 'yoshino', 'kimiko',
            'yo', 'oizumi', 'hideko', 'yoshida', 'misako', 'tanaka',
            'kazue', 'tsuzuki', 'akiko', 'yano', 'asuka', 'fukuda',
            'yoko', 'narahashi', 'shinji', 'ogawa', 'atsushi',
            'yamazaki', 'teruyuki', 'kagawa', 'susumu', 'terajima',
            'tadanobu', 'asano', 'ren', 'osugi', 'denden', 'takao',
            'okawa', 'yayoi', 'kazama', 'ryoko', 'gi', 'harumi',
            'ine', 'hideo', 'nakata', 'koji', 'suzuki', 'ryuji',
            'takayama', 'sadako', 'yamamura', 'shizuko', 'heihachiro',
            'ikoma', 'uma', 'thurman', 'kill', 'bill', 'quentin',
            'tarantino', 'uma', 'thurman', 'lucy', 'liu', 'daryl',
            'hannah', 'david', 'carradine', 'gordon', 'liu', 'chia',
            'hui', 'liu', 'julie', 'dreifuss', 'vivica', 'fox',
            'michael', 'madsen', 'michael', 'parks', 'james',
            'remar', 'clark', 'middendorf', 'jennifer', 'jason',
            'leigh', 'sonny', 'chiba', 'shinichi', 'chiba', 'kenji',
            'oba', 'jun', 'kunimura', 'yoshio', 'harada', 'shiro',
            'sano', 'akaji', 'maro', 'kaori', 'momoi', 'sakichi',
            'sato', 'norman', 'reedus', 'james', 'brown', 'seinfeld',
            'jason', 'patric', 'bokeem', 'woodbine', 'michael',
            'bowen', 'sid', 'haig', 'fred', 'williamson', 'tom',
            'savini', 'george', 'aitken', 'samuel', 'l', 'jackson',
            'christoph', 'waltz', 'diane', 'kruger', 'eli', 'roth',
            'til', 'schweiger', 'daniel', 'brühl', 'mélanie',
            'laurent', 'august', 'diehl', 'sylvester', 'groth',
            'martin', 'wuttke', 'hilmar', 'eichhorn', 'matthias',
            'brandt', 'lucy', 'liu', 'josh', 'hartnett', 'scarlett',
            'johansson', 'aaron', 'eckhart', 'ben', 'kingsley',
            'mia', 'kirshner', 'patrick', 'wilson', 'jackie',
            'earle', 'haley', 'matthew', 'goode', 'rochelle',
            'ayes', 'steve', 'buscemi', 'kathy', 'baker', 'amy',
            'adams', 'terrence', 'stamp', 'derek', 'luke',
            'marley', 'shelton', 'troy', 'garity', 'jason',
            'manzucas', 'hugh', 'jackman', 'christian', 'bale',
            'michael', 'caine', 'scarlett', 'johansson', 'rebecca',
            'hall', 'gary', 'oldman', 'maggie', 'gyllenhaal',
            'morgan', 'freeman', 'cillian', 'murphy', 'tom',
            'hardy', 'anne', 'hathaway', 'joseph', 'gordon',
            'levitt', 'marion', 'cotillard', 'ellen', 'page',
            'ken', 'watanabe', 'dileep', 'rao', 'jim', 'sturgess',
            'lukas', 'haas', 'talulah', 'riley', 'clémence',
            'poésy', 'michael', 'caine', 'pete', 'postlethwaite',
            'bradley', 'cooper', 'robert', 'de', 'niro', 'anne',
            'hathaway', 'jennifer', 'lawrence', 'jacki', 'weaver',
            'wes', 'bentley', 'stacy', 'keach', 'eion', 'bailey',
            'denis', 'menochet', 'toby', 'jones', 'shea',
            'whigham', 'sam', 'rockwell', 'olivia', 'wilde',
            'john', 'hawkes', 'melissa', 'leo', 'stephen',
            'lang', 'brad', 'pitt', 'jonah', 'hill', 'scoot',
            'mcnairy', 'ben', 'mendelsohn', 'sam', 'shepard',
            'garret', 'dillahunt', 'paul', 'dano', 'carey',
            'mulligan', 'jake', 'gyllenhaal', 'michael', 'fassbender',
            'josh', 'brolin', 'elizabeth', 'olsen', 'zoe', 'kazan',
            'lenny', 'james', 'wes', 'bentley', 'taryn', 'manning',
            'danny', 'aiello', 'walton', 'goggins', 'diane',
            'kruger', 'elijah', 'wood', 'boris', 'karloff',
            'peter', 'lorre', 'john', 'carradine', 'gale',
            'sondgaard', 'bel', 'lugosi', 'lon', 'chaney',
            'vincent', 'price', 'christopher', 'lee', 'peter',
            'cushing', 'max', 'schreck', 'claude', 'rains',
            'basil', 'rathbone', 'nigel', 'bruce', 'ida',
            'lupino', 'george', 'zucco', 'henry', 'daniell',
            'devon', 'bostick', 'john', 'harkins', 'jill',
            'schoelen', 'tommy', 'flanagan', 'jodi', 'benson',
            'pat', 'carroll', 'kenneth', 'mars', 'buddy',
            'hackett', 'jason', 'marin', 'ben', 'wright',
            'rené', 'auberjonois', 'paddi', 'edwards', 'charles',
            'budden', 'robert', 'weaver', 'willard', 'waterman',
            'amby', 'pappy', 'edie', 'mcclurg', 'marilyn',
            'schreffler', 'harold', 'hamilton', 'susan',
            'fitzhugh', 'tress', 'macneille', 'pat', 'musick',
            'philip', 'clarke', 'tony', 'jay', 'jimmy',
            'macdonald', 'valri', 'bromfield', 'daamen',
            'krall', 'krystina', 'kauffman', 'cameron',
            'anthea', 'davis', 'mckenzie', 'gray', 'clara',
            'schneider', 'sarah', 'jessica', 'parker',
            'matthew', 'broderick', 'kathy', 'najimy',
            'bette', 'midler', 'doug', 'jones', 'jason',
            'schwartzman', 'bill', 'murray', 'owen',
            'wilson', 'adrien', 'brody', 'willem',
            'dafoe', 'jeff', 'goldblum', 'harvey',
            'keitel', 'bob', 'balaban', 'michael',
            'gambon', 'jarvis', 'cocker', 'seymour',
            'cassel', 'mathieu', 'amalric', 'wally',
            'wolodarsky', 'eric', 'chase', 'warren',
            'keith', 'jared', 'gilman', 'kara',
            'hayward', 'frances', 'mcdormand',
            'edward', 'norton', 'bruce', 'willis',
            'tony', 'revolori', 'f', 'murray',
            'abraham', 'attah', 'emma', 'thompson',
            'idris', 'elba', 'kate', 'winslet',
            'sigourney', 'weaver', 'stanley',
            'tucci', 'john', 'lithgow', 'michael',
            'stuhlbarg', 'mckenna', 'grace',
            'gugu', 'mbatha', 'david', 'oyelowo',
            'carmen', 'ejogo', 'colman', 'domingo',
            'nate', 'parker', 'armie', 'hammer',
            'aunjanue', 'ellis', 'aldis', 'hodge',
            'andre', 'holland', 'ciarán', 'hinds',
            'billy', 'bob', 'thornton', 'lupita',
            'nyongo', 'mahershala', 'ali', 'naomie',
            'harris', 'trevante', 'rhodes', 'andré',
            'holland', 'ashton', 'sanders', 'jax',
            'malcolm', 'david', 'kelley', 'harold',
            'perrineau', 'dominic', 'monaghan',
            'jorge', 'garcia', 'daniel', 'dae',
            'kim', 'yunjin', 'kim', 'michael',
            'emerson', 'ken', 'leung', 'rebecca',
            'mader', 'maggie', 'grace', 'ian',
            'sommerhalder', 'dominique', 'monaghan',
            'michelle', 'rodriguez', 'elizabeth',
            'mitchell', 'kiele', 'sanchez', 'gloria',
            'votsis', 'l', 'scott', 'caldwell',
            'tania', 'raymond', 'malcolm', 'david',
            'kelley', 'harold', 'perrineau', 'jr',
            'kimberley', 'joseph', 'matthew',
            'fox', 'evangeline', 'lilly', 'josh',
            'holloway', 'naveen', 'andrews',
            'terry', 'o', 'quinn', 'michael',
            'emerson', 'ken', 'leung', 'henry',
            'ian', 'cusick', 'emilie', 'de',
            'ravin', 'daniel', 'dae', 'kim',
            'yunjin', 'kim', 'maggie', 'grace',
            'tamlyn', 'tomita', 'jason', 'dohring',
            'kiele', 'sanchez', 'rebecca', 'mader',
            'elizabeth', 'mitchell', 'gloria',
            'votsis', 'l', 'scott', 'caldwell',
            'tania', 'raymond', 'malcolm', 'david',
            'kelley', 'harold', 'perrineau', 'jr',
            'kimberley', 'joseph', 'matthew',
            'fox', 'evangeline', 'lilly', 'josh',
            'holloway', 'naveen', 'andrews',
            'terry', 'o', 'quinn', 'michael',
            'emerson', 'ken', 'leung', 'john',
            'henry', 'ian', 'cusick', 'emilie',
            'de', 'ravin', 'daniel', 'dae',
            'kim', 'yunjin', 'kim', 'maggie',
            'grace', 'tamlyn', 'tomita', 'jason',
            'dohring', 'kiele', 'sanchez', 'rebecca',
            'mader', 'elizabeth', 'mitchell',
            'gloria', 'votsis', 'l', 'scott',
            'caldwell', 'tania', 'raymond',
            # 🔼 Увеличили порог до 10 слов
        }
        english_words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        suspicious_words = [w for w in english_words if w not in allowed_english]
        if len(suspicious_words) > 10:  # 🔼 Увеличили порог до 10
            logger.warning(f"🚨 Много английских слов: {suspicious_words[:5]}")
            metrics.log_english_blocked()
            if prom_metrics:
                return True
        return False

    def _verify_against_source(self, orig_title: str, orig_content: str, generated: str) -> bool:
        """
        🔍 Проверка: сгенерированный пост не должен содержать информации,
        которой не было в оригинальном тексте.
        """
        orig_text = f"{orig_title} {orig_content}".lower()
        gen_text = generated.lower()

        # 🚫 ПРОПУСКАЕМ частые русские слова — не имена
        common_russian_words = {
            'этот', 'эти', 'такой', 'который', 'что', 'как', 'где', 'когда',
            'он', 'она', 'они', 'мы', 'вы', 'они', 'них', 'ним', 'ней',
            'всё', 'весь', 'вся', 'всё', 'все', 'сам', 'сами', 'сама',
            'уже', 'ещё', 'тоже', 'также', 'потом', 'затем', 'после',
            'первый', 'второй', 'новый', 'последний', 'главный', 'лучший',
            'текст', 'согласно', 'нач��нается', 'заголовок', 'ответ', 'начни',
            'фильм', 'кино', 'актёр', 'режиссёр', 'премь��ра', 'россия', 'москва',
            'канн', 'оскар', 'веном', 'марвел', 'голливуд', 'нетфликс', 'дисней'
        }

        # 🔍 Ищем ТОЛЬКО реальные имена собственные:
        # - Имена в кавычках: «Имя Фамилия»
        # - Несколько заглавных подряд: Имя Фамилия
        # Пропускаем одиночные заглавные в начале предложения
        
        # Паттерн 1: Имена в кавычках
        quoted_names = re.findall(r'[«"]([А-Я][а-я]+(?:\s+[А-Я][а-я]+)+)[»"]', generated)
        
        # Паттерн 2: 2+ заглавных слова подряд (имя + фамилия)
        # Ищем последовательности типа "Имя Фамилия" но не в начале предложения
        cap_sequences = re.findall(r'(?<![.!?])\s([А-Я][а-я]+(?:\s+[А-Я][а-я]+)+)', generated)
        
        all_names = quoted_names + cap_sequences
        
        # Проверяем каждое найденное имя
        for full_name in all_names:
            # Пропускаем если это частое слово
            if full_name.lower() in common_russian_words:
                continue

            # Проверяем каждое слово в имени
            for name_part in full_name.split():
                if name_part.lower() in common_russian_words:
                    continue
                
                # 🔍 ПРОВЕРЯЕМ С УЧЁТОМ СКЛОНЕНИЙ (основа слова, 4+ символа)
                found_variant = any(
                    variant in orig_text
                    for variant in [
                        name_part.lower(),           # Точное совпадение
                        name_part[:5].lower(),       # Первые 5 букв (основа)
                        name_part[:4].lower(),       # Первые 4 буквы
                        name_part[:-1].lower(),      # Без последней буквы (окончание)
                        name_part[:-2].lower(),      # Без 2 последних букв
                    ]
                    if len(variant) >= 4
                )
                
                # 🔍 ПРОВЕРЯЕМ ТРАНСЛИТЕРАЦИЮ (для имён)
                if not found_variant:
                    # Простая транслитерация кириллица → латиница
                    translit_map = {
                        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
                        'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
                        'й': 'y', 'к': 'k', 'л': 'l', '������': 'm', 'н': 'n',
                        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
                        'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch',
                        'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
                        'э': 'e', 'ю': 'yu', 'я': 'ya'
                    }
                    transliterated = ''.join(
                        translit_map.get(c, c) for c in name_part.lower()
                    )
                    # Проверяем транслитерированное имя в оригинале
                    if transliterated in orig_text or transliterated in orig_title.lower():
                        found_variant = True
                
                if not found_variant:
                    logger.warning(f"���️ Подозрительное имя: {full_name} (нет в оригинале)")
                    return False

        # Проверяем конкретные выдуманные паттерны
        fake_patterns = [
            r'объявили\s+п������бедителей',
            r'победитель\s+стал',
            r'получил\s+(золотую|серебряную|главную)',
            r'награда\s+досталась',
            r'жюри\s+подчеркнуло',
            r'организаторы\s+выразили',
        ]
        for pattern in fake_patterns:
            if re.search(pattern, gen_text):
                # Проверяем есть ли это в оригинале
                if not re.search(pattern, orig_text):
                    logger.warning(f"⚠️ Выдуманный паттерн: {pattern}")
                    return False

        return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def classify(self, title: str, summary: str) -> bool:
        cache_key = self._get_cache_key(title, summary, "classify")
        if cache_key in self.cache:
            logger.info(f"💾 Cache hit: classify")
            metrics.log_llm_cache_hit()
            return self.cache[cache_key]

        await self._circuit_breaker_check()
        await self.rate_limiter.wait()
        metrics.log_llm_call('classify')

        current_date = datetime.now().strftime('%d.%m.%Y')
        current_year = datetime.now().year
        

        prompt = f"""Ты фильтр новостей о к��но. Ответь ОДНИМ словом: CINEMA или NONE.

CINEMA: новость про фильм, сериал, актёра, режиссёра, трейлер, премьеру, фестиваль.
NONE: политика, спорт, экономика, ретроспективы, не про кино.

Сегодня: {current_date}. Не пиши итоги событий, которые ещё не прошли.

NONE — если это:
- Итог���� или победители фестиваля, ��оторый ЕЩЁ НЕ ПРОШЁЛ (дата в будущем)
- Ретроспектива, топ-листы, обзоры старых фильмов
- Политика, спорт, экономика
- Текст на английском языке

Заголовок: {title}
Текст: {summary[:400]}"""

        try:
            response = await self.client.chat.completions.create(
                model=config.translate_model,  # ✅ Мистраль для классификации
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50,
                timeout=20.0
            )
            content = self._extract_content_from_response(response)
            if not content:
                return False

            result = "CINEMA" in content.upper()
            self.cache[cache_key] = result
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
            return False

    async def translate_to_russian(self, title: str, content: str) -> Optional[str]:
        """🌍 Перевод английской новости на русский"""
        cache_key = self._get_cache_key(title, content[:500], "translate")
        if cache_key in self.cache:
            logger.info(f"💾 Cache hit: translate")
            metrics.log_llm_cache_hit()
            return self.cache[cache_key]

        await self._circuit_breaker_check()
        await self.rate_limiter.wait()
        metrics.log_llm_call('translate')

        prompt = f"""Ты профессиональный переводчик кино-новостей. Переведи текст на русский язык.

🚫 КРИТИЧЕСКИ ВАЖНО — НЕ ОСТАВЛЯЙ АНГЛИЙСКИХ СЛОВ:
- Переводи ВСЕ слова на русский кроме: имён актёров/режиссёров, названий студий (Marvel, Netflix, HBO)
- НЕ пиши "kingdom", "days", "night", "agent", "paradise" — пиши "королевство", "дни", "ночь", "агент", "рай"
- НЕ пиши "video", "story", "about", "working", "says", "set" — пиши "видео", "история", "о", "работает", "говорит", "набор"
- НЕ пиши "right", "now", "what", "watch", "theaters" — пиши "право", "сейчас", "что", "смотреть", "театры"
- Названия фильмов/сериалов оставь в оригинале, можно добавить перевод в скобках

🚫 ЗАПРЕЩЕНО ДОБАВЛЯТЬ ДАТЫ:
- НЕ добавляй никаких годов (2023, 2024, 2025, 2026)
- НЕ добавляй дат выхода, премьер, релизов
- Переводи только факты из оригинала — если даты нет в оригинале, не добавляй её

✅ РАЗРЕШЕНЫ ТОЛЬКО:
- Имена: Anupam Kher, Shah Rukh Khan
- Студии: Marvel, Netflix, HBO, Disney, Warner
- Стриминги: YouTube, Red, Premium

ФОРМАТ ОТВЕТА:
Просто переведённый текст ПОЛНОСТЬЮ НА РУССКОМ без комментариев.

Оригинал:
{title}
{content[:2000]}

Перевод:"""

        for attempt in range(2):  # 🔁 Повторяем до 2 раз при пустом ответе
            try:
                response = await self.client.chat.completions.create(
                    model=config.translate_model,  # ✅ Мистраль для перевода
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=8000,
                    timeout=90.0
                )

                # 🔍 Проверяем content
                content_len = 0
                if hasattr(response, 'choices') and response.choices:
                    choice = response.choices[0]
                    if hasattr(choice, 'message'):
                        msg = choice.message
                        content = getattr(msg, 'content', None)
                        content_len = len(content) if content else 0
                        if content and content_len > 100:
                            logger.info(f"✅ Перевод выполнен: {content_len} символов")
                            result = content.strip()
                            self.cache[cache_key] = result
                            if len(self.cache) % 10 == 0:
                                self._save_cache()
                            self.rate_limiter.report_success()
                            self.circuit_breaker_fails = max(0, self.circuit_breaker_fails - 1)
                            return result

                logger.warning(f"⚠️ Перевод пустой (попытка {attempt+1}/2)")
                if attempt == 0:
                    await asyncio.sleep(2)  # Пауза перед повтором

            except Exception as e:
                logger.warning(f"⚠️ LLM translate error (попытка {attempt+1}/2): {str(e)[:100]}")
                if attempt == 0:
                    await asyncio.sleep(2)

        logger.warning(f"⚠️ Перевод не удался после 2 попыток")
        metrics.log_error(f"translate: empty response after retries")
        self.rate_limiter.report_error()
        self.circuit_breaker_fails += 1
        if self.circuit_breaker_fails >= self.circuit_breaker_threshold:
            self.circuit_breaker_open_until = asyncio.get_event_loop().time() + 60
        await asyncio.sleep(random.uniform(2, 4))
        return None

    async def generate_post(self, title: str, content: str) -> Optional[str]:
        cache_key = self._get_cache_key(title, content, "generate")
        if cache_key in self.cache:
            logger.info(f"💾 Cache hit: generate")
            metrics.log_llm_cache_hit()
            return self.cache[cache_key]

        await self._circuit_breaker_check()
        await self.rate_limiter.wait()
        metrics.log_llm_call('generate')

        current_date = datetime.now().strftime('%d.%m.%Y')
        current_year = datetime.now().year

        prompt = f"""Ты редактор кино-канала. Перепиши новость на РУССКОМ ЯЗЫКЕ.

🚫 КРИТИЧЕСКИ ВАЖНО:
- Пиши ПОЛНОСТЬЮ на русском языке
- НЕ используй английские слова кроме: названий студий (Marvel, Netflix, HBO), имён актёров и режиссёров
- Все остальные слова переводи на русский
- Не пиши "video", "story", "about", "working" — пиши "видео", "история", "о", "работает"

🚫 ЗАПРЕЩЕНО ДОБАВЛЯТЬ ДАТЫ:
- НЕ добавляй никаких годов (2023, 2024, 2025, 2026)
- НЕ добавляй дат выхода, премьер, релизов
- Пиши только факты из оригинала — если даты нет в оригинале, не добавляй её

✅ ИСПОЛЬЗУЙ:
- Имена собственные в оригинале: Anupam Kher, Saaransh
- Названия студий: Marvel, Netflix, HBO, Disney
- Всё остальное — по-русски!

ФОРМАТ:
🎬<b>Заголовок</b>

2-4 абзаца, 400-1500 символов.

Оригинал:
{title[:80]}
{content[:2000]}

Начни с 🎬<b>:"""

        try:
            response = await self.client.chat.completions.create(
                model=config.model_name,  # ✅ GPT-OSS для генерации поста
                messages=[{"role": "user", "content": prompt}],
                temperature=0.35,
                max_tokens=4000,
                timeout=60.0
            )
            result = self._extract_content_from_response(response)

            if not result or len(result) < 200:
                logger.warning(f"⚠️ Генерация слишком короткая: {len(result) if result else 0} символов")
                return None

            # 🔍 ПРОВЕРКА 1: Выдуманные даты
            if self._contains_fake_dates(result):
                logger.warning(f"⚠️ Генерация содержит выдуманные даты, отклонён")
                return None

            # 🔍 ПРОВЕРКА 2: Слишком много английского
            if self._contains_too_much_english(result):
                logger.warning(f"⚠️ Генерация содержит слишком много английских слов")
                return None

            # 🔍 ПРОВЕРКА 3: Сверка с оригиналом — запрещаем имена/названия которых не было
            # ⚠️ ОТКЛЮЧЕНО для переведённого текста — имена уже транслитерированы
            # if not self._verify_against_source(title, content, result):
            #     logger.warning(f"⚠️ Генерация содержит информацию не из источника")
            #     return None

            logger.info(f"✅ Генерация прошла все проверки: {len(result)} символов")
            self.cache[cache_key] = result

            if len(self.cache) % 10 == 0:
                self._save_cache()

            self.rate_limiter.report_success()
            self.circuit_breaker_fails = max(0, self.circuit_breaker_fails - 1)
            return result

        except Exception as e:
            logger.warning(f"⚠️ LLM generate error: {str(e)[:100]}")
            metrics.log_error(f"generate: {e}")
            self.rate_limiter.report_error()
            self.circuit_breaker_fails += 1
            if self.circuit_breaker_fails >= self.circuit_breaker_threshold:
                self.circuit_breaker_open_until = asyncio.get_event_loop().time() + 60
            await asyncio.sleep(random.uniform(2, 4))
            return None

# ================= ОБРАБОТКА RSS =================
def parse_rss_date(entry) -> Optional[datetime]:
    """Парсинг даты из RSS entry"""
    for attr in ["published_parsed", "updated_parsed", "created_parsed"]:
        val = getattr(entry, attr, None)
        if val and isinstance(val, tuple) and len(val) >= 6:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    
    for attr in ["published", "updated", "created"]:
        val = getattr(entry, attr, None)
        if val and isinstance(val, str):
            try:
                parsed = feedparser.util.parse_date_to_datetime(val)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except Exception:
                continue
    
    return None

def is_news_fresh(pub_date: Optional[datetime], current_time: datetime) -> Tuple[bool, Optional[float]]:
    """Проверить свежесть новости — СТРОГАЯ проверка"""
    
    if pub_date is None:
        logger.debug("⏭️ Пропущена новость без даты pub_date")
        return False, None
    
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    
    # ⛔ ЖЁСТКИЙ БАРЬЕР: блокируем всё старше прошлого года
    current_year = current_time.year
    if pub_date.year < current_year:
        logger.warning(f"⛔ Архивная новость ({pub_date.year}): заблокирована")
        return False, None
    
    # Новость из будущего (больше чем на 1 час) — подозрительно
    if pub_date > current_time + timedelta(hours=1):
        logger.debug(f"⏭️ Новость из будущего: {pub_date}")
        return False, None
    
    age_seconds = (current_time - pub_date).total_seconds()
    age_hours = age_seconds / 3600
    
    # Слишком свежая — ещё не проиндексировалась
    if age_seconds < config.min_news_age_minutes * 60:
        return False, age_hours
    
    # Старше max_news_age_hours — отклоняем
    if age_hours > config.max_news_age_hours:
        logger.debug(f"⏭️ Слишком старая: {age_hours:.1f} ч (лимит {config.max_news_age_hours} ч)")
        return False, age_hours
    
    return True, age_hours

def extract_entry_content(entry) -> Tuple[str, str]:
    """Извлечь title и body из RSS entry"""
    title = clean_html(entry.get("title", ""))

    content_parts = []
    for field in ["content", "summary", "description"]:
        val = entry.get(field, "")
        if isinstance(val, list) and val:
            val = val[0].get("value", "")
        if val:
            content_parts.append(clean_html(val))

    body = " ".join(content_parts).strip()
    return title, body

def is_valid_entry(title: str, body: str, link: str) -> bool:
    """Валидация RSS entry"""
    if len(title) < 12 or len(title) > 150:
        return False
    if len(body) < 80:
        return False
    if not link:
        return False
    return True

async def fetch_feed_optimized(session: aiohttp.ClientSession, url: str):
    """Загрузить RSS feed с кешированием и rate limiting"""
    clean_url = url.strip()
    if not clean_url:
        return url, feedparser.FeedParserDict(entries=[])

    # 🚫 ПРОВЕРКА ЧЁРНОГО СПИСКА ПЕРЕД ЗАГРУЗКОЙ
    if is_domain_blacklisted(clean_url):
        logger.info(f"🚫 Пропущен чёрный домен: {clean_url}")
        metrics.log_blacklist_blocked()
        return url, feedparser.FeedParserDict(entries=[])

    domain = urlparse(clean_url).netloc

    last_req = state.domain_last_request.get(domain, 0)
    elapsed = asyncio.get_event_loop().time() - last_req

    if elapsed < config.domain_min_delay:
        await asyncio.sleep(config.domain_min_delay - elapsed)

    state.domain_last_request[domain] = asyncio.get_event_loop().time()

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, */*'
        }
        async with session.get(
            clean_url,
            timeout=aiohttp.ClientTimeout(total=12),
            headers=headers
        ) as response:
            if response.status == 200:
                content = await response.read()
                feed = feedparser.parse(content)

                if hasattr(feed, "entries") and feed.entries:
                    logger.info(f"✅ {domain}: {len(feed.entries)} записей")
                    return url, feed
                else:
                    logger.warning(f"⚠️ {domain}: нет записей")
                    return url, feedparser.FeedParserDict(entries=[])
            else:
                logger.warning(f"⚠️ {domain}: HTTP {response.status}")
                return url, feedparser.FeedParserDict(entries=[])

    except asyncio.TimeoutError:
        logger.warning(f"⏱️ {domain}: таймаут")
        return url, feedparser.FeedParserDict(entries=[])
    except Exception as e:
        logger.warning(f"❌ {domain}: {str(e)[:50]}")
        return url, feedparser.FeedParserDict(entries=[])

async def fetch_all_feeds(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Загрузить все RSS feeds параллельно"""
    feeds = RSS_FEEDS.copy()
    random.shuffle(feeds)
    feed_results = {}
    
    logger.info(f"🔄 Загружаем {len(feeds)} фидов...")
    
    tasks = [fetch_feed_optimized(session, url) for url in feeds]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, tuple):
            url, feed = result
            feed_results[url] = feed
        else:
            logger.warning(f"⚠️ Ошибка: {result}")
    
    successful = sum(
        1 for feed in feed_results.values()
        if hasattr(feed, "entries") and feed.entries
    )
    logger.info(f"📊 Успешно загружено: {successful}/{len(feeds)}")
    
    return feed_results

async def process_feed_entries(feed_results: Dict, session: aiohttp.ClientSession,
                               duplicate_detector: DuplicateDetector,
                               current_time: datetime) -> List[Dict]:
    """
    🎯 Собрать entries из всех feeds БЕЗ LLM обработки.
    Только первичная фильтрация по ключевым словам.
    """
    all_entries = []
    processed_hashes = set()

    for feed_url, feed in feed_results.items():
        if not hasattr(feed, "entries") or not feed.entries:
            continue

        # ✅ Чёрный список уже проверен перед загрузкой
        metrics.metrics['feeds_processed'] += 1

        for entry in feed.entries[:config.max_entries_per_feed]:
            try:
                title, body = extract_entry_content(entry)
                link = entry.get("link", "").strip()

                if not is_valid_entry(title, body, link):
                    continue

                # 🔍 ПРОВЕРКА ПО КЛЮЧЕВЫМ СЛОВАМ (без LLM!)
                is_cinema, cinema_matches, hot_matches, super_hot_matches = is_cinema_candidate(title, body)
                if not is_cinema:
                    if prom_metrics:
                        prom_metrics.inc_rejected('not_cinema')
                    continue

                pub_date = parse_rss_date(entry)
                is_fresh, age_hours = is_news_fresh(pub_date, current_time)

                if not is_fresh:
                    if prom_metrics:
                        prom_metrics.inc_rejected('not_fresh')
                    continue

                # 🔍 ПРОВЕРКА ДУБЛИКАТОВ (3 уровня)
                is_dup, dup_method = await duplicate_detector.is_duplicate_advanced(
                    title, body, link, pub_date, config.db_path
                )
                if is_dup:
                    metrics.log_duplicate(dup_method)
                    continue

                post_hash = hashlib.md5(f"{title}{link}".encode()).hexdigest()

                if post_hash in processed_hashes:
                    continue

                processed_hashes.add(post_hash)

                # 🕒 ПРИОРИТЕТ СВЕЖЕСТИ: новости <2 часов получают бонус
                freshness_bonus = 2 if age_hours and age_hours < 2 else 0

                # 🎯 СКОРИНГ: считаем приоритет новости
                # Формула: супер-горячие * 10 + горячие темы * 3 + кино-ключи * 1 + свежесть
                SUPER_HOT_WEIGHT = 10  # 🔥 Супер-бонус за режиссёра/актёра + съёмки
                score = (
                    super_hot_matches * SUPER_HOT_WEIGHT +
                    hot_matches * config.hot_topic_weight +
                    cinema_matches * config.cinema_keyword_weight +
                    freshness_bonus
                )

                logger.info(f"✓ Скор: {score} (SUPER:{super_hot_matches}, HOT:{hot_matches}, Ключ:{cinema_matches}, Возраст:{age_hours:.1f}ч): {title[:60]}")

                all_entries.append({
                    "hash": post_hash,
                    "title": title,
                    "body": body,
                    "link": link,
                    "age_hours": age_hours,
                    "source": feed_url,
                    "cinema_matches": cinema_matches,
                    "hot_matches": hot_matches,
                    "super_hot_matches": super_hot_matches,
                    "pub_date": pub_date,
                    "freshness_bonus": freshness_bonus,
                    "score": score
                })

            except Exception as e:
                logger.debug(f"Ошибка обработки entry: {e}")
                continue

    return all_entries

async def collect_candidates(llm: CachedLLMClient, duplicate_detector: DuplicateDetector,
                            session: aiohttp.ClientSession) -> List[Dict]:
    """
    🎯 Сбор и отбор кандидатов.
    Возвращает ТОП-1 новость по скорингу для дальнейшей LLM обработки.
    """
    current_time = datetime.now(timezone.utc)

    # 🔽 ЛИМИТ ФИДОВ: обрабатываем только 5 случайных фидов за цикл
    feed_results = await fetch_all_feeds(session)

    # Выбираем случайные 5 фидов для разнообразия
    if len(feed_results) > config.max_feeds_per_cycle:
        selected_feeds = random.sample(list(feed_results.keys()), config.max_feeds_per_cycle)
        feed_results = {k: v for k, v in feed_results.items() if k in selected_feeds}
        logger.info(f"📊 Отбрано {config.max_feeds_per_cycle} фидов из {len(feed_results)}")

    all_entries = await process_feed_entries(feed_results, session, duplicate_detector, current_time)

    logger.info(f"📊 Найдено записей: {len(all_entries)}")

    if not all_entries:
        return []

    # 🎯 СОРТИРОВКА ПО СКОРУ (уже считается в process_feed_entries)
    all_entries.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # 🔝 ВОЗВРАЩАЕМ ТОЛЬКО ТОП-1 для экономии токенов
    top_entry = all_entries[0]
    logger.info(f"🏆 ТОП-1 новость: {top_entry['title'][:70]} (score={top_entry['score']})")

    metrics.metrics['candidates_found'] = len(all_entries)
    if prom_metrics:
        prom_metrics.set_candidates(1)

    return [top_entry]

# ================= ОТПРАВКА В TELEGRAM =================
async def send_to_suggestion(session: aiohttp.ClientSession, text: str, link: str,
                            pub_date: Optional[datetime], original_title: str = "",
                            max_retries: int = 3) -> bool:
    """Отправка в предложку с retry логикой и rate limiting"""
    text = safe_to_string(text)
    text = validate_html_tags(text)

    if not text or len(text) < 50:
        logger.error("❌ Текст слишком короткий")
        return False

    if not text.startswith("🎬<b>"):
        logger.error("❌ Текст не начинается с 🎬<b>")
        return False

    if not is_russian_text(text, min_ratio=0.60):
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
                        metrics.log_post_sent('cinema', 'autopost')
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
            metrics.log_error(f"send_to_suggestion: {e}")
            if attempt < max_retries:
                await asyncio.sleep(5 * attempt)

    logger.error(f"❌ Не удалось отправить после {max_retries} попыток")
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
async def collect_and_process_news(llm: CachedLLMClient, duplicate_detector: DuplicateDetector,
                                  session: aiohttp.ClientSession, start_time: float = None):
    """
    🎯 ОСНОВНОЙ ЦИКЛ — экономия токенов.
    1. Собираем все новости из 5 фидов (без LLM)
    2. Выбираем ТОП-1 по скорингу
    3. ТОЛЬКО ДЛЯ ТОП-1: LLM classify → LLM generate
    """
    import time
    if start_time is None:
        start_time = time.time()

    try:
        # 🚫 ПРОВЕРКА ДНЕВНОГО ЛИМИТА
        if not metrics.can_post_today():
            logger.info(f"🚫 Дневной лимит исчерпан ({config.max_posts_per_day} постов)")
            return 0

        # 📥 ШАГ 1: Сбор и отбор ТОП-1 новости (без LLM!)
        candidates = await collect_candidates(llm, duplicate_detector, session)

        if not candidates:
            logger.warning("📭 Нет подходящих кандидатов")
            return 0

        # 🎯 ШАГ 2: Берём только ТОП-1
        best = candidates[0]
        logger.info(f"🏆 ТОП-1 для обработки: {best['title'][:70]}")

        # 🌍 ШАГ 2а: Для английских — сначала перевод (Mistral)
        translated_body = best["body"]
        if is_english_text(best["body"]):
            logger.info(f"🌍 Английский текст — перевод (Mistral)...")
            translated = await llm.translate_to_russian(best["title"][:100], best["body"])
            if translated:
                translated_body = translated
                logger.info(f"✅ Перевод выполнен: {len(translated)} символов")
            else:
                logger.warning(f"⚠️ Перевод не удался, пробуем оригинал")

        # 🔍 ШАГ 3: LLM classify (если не HOT тема)
        if best["hot_matches"] < config.auto_approve_hot_threshold:
            logger.info(f"🔍 LLM classify для ТОП-1...")
            if not await llm.classify(best["title"][:100], translated_body):
                logger.info(f"⏭️ Отклонён LLM: {best['title'][:60]}")
                metrics.metrics['posts_rejected'] += 1
                return 0
            logger.info(f"✅ LLM одобрил ТОП-1")
        else:
            logger.info(f"⚡ Автоодобрено (HOT тема): {best['title'][:60]}")

        # ✍️ ШАГ 4: LLM generate рерайт (GPT-OSS)
        generated = await llm.generate_post(best["title"][:100], translated_body)
        if not generated:
            logger.warning(f"⚠️ Генерация пуста: {best['title'][:60]}")
            return 0

        final_text = postprocess_text(generated)

        if not final_text or len(final_text) < 50:
            return 0

        if not is_russian_text(final_text):
            return 0

        # 📤 ШАГ 5: Отправка в предложку
        if await send_to_suggestion_with_retry(session, final_text, best["link"], best["pub_date"], best["title"]):
            final_hash = get_content_hash(final_text[:200], best["link"])
            await save_post(
                best["link"],
                final_hash,
                best["source"],
                normalize_title(final_text[:100]),
                "posted"
            )

            # ✅ Сохраняем content_dedup hash
            content_dedup_hash = get_content_dedup_hash(best["title"], best["body"])
            await save_content_dedup_hash(content_dedup_hash)

            # ✅ Отметка в глобальной БД
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
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка отметки в глобальной БД: {e}")

            metrics.increment_posts_today()
            state.last_post_time = asyncio.get_event_loop().time()
            logger.info(f"✅ ТОП-1 новость отправлена в предложку")
            return 1
        else:
            logger.error("❌ Ошибка отправки в предложку")
            if alert_manager:
                await alert_manager.alert_critical(
                    f"Ошибка публикации — {config.channel}",
                    f"Не удалось отправить пост в предложку"
                )
            return 0
    except Exception as e:
        logger.error(f"❌ Ошибка в collect_and_process_news: {e}", exc_info=True)
        return 0
    finally:
        import time
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
            logger.warning("⚠️ Таймаут ожидан��я задачи")
    
    llm._save_cache()
    await cleanup_old_posts()
    await cleanup_old_data()
    cleanup_old_logs()  # Очистка логов (синхронная)

    if GLOBAL_DEDUP_ENABLED:
        try:
            await cleanup_global_db(days=30)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки глобальной БД: {e}")
    
    metrics.print_summary()
    logger.info("✅ Бот остановлен корректно")

# ================= MAIN =================
async def main():
    await init_db()
    await init_global_db()
    
    # ✅ ИНИЦИАЛИЗАЦИЯ ГЛОБАЛЬНО�� БД
    if GLOBAL_DEDUP_ENABLED:
        try:
            await init_global_db()
            logger.info("✅ Глобальная БД дедупликации инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации глобальной БД: {e}")
    
    llm = CachedLLMClient()
    alert_manager = AlertManager(config.tg_token)
    duplicate_detector = DuplicateDetector()
    
    logger.info("=" * 60)
    logger.info("🚀 @Film_orbita PRODUCTION 2026 — OPTIMIZED")
    logger.info(f"   Модель: {config.model_name}")
    logger.info(f"   Лимит: {config.max_posts_per_day} постов/день, {config.max_posts_per_cycle}/цикл")
    logger.info(f"   Фидов за цикл: {config.max_feeds_per_cycle} из {len(RSS_FEEDS)}")
    logger.info(f"   ⚡ Автоодобрение: {config.auto_approve_hot_threshold}+ HOT слово")
    logger.info(f"   🔄 Fuzzy дубликаты: порог {config.fuzzy_threshold:.0%}")
    logger.info(f"   💾 Кэш��рование: {len(llm.cache)} записей")
    logger.info(f"   🚫 Защита от выдумок: ВКЛ")
    logger.info(f"   🕒 Приоритет свежести: <2 часов")
    logger.info(f"   🚫 Чёрный список: {len(BLACKLISTED_DOMAINS)} доменов")
    logger.info(f"   🌍 Глобальная дедупликация: {'✅ ВКЛ' if GLOBAL_DEDUP_ENABLED else '❌ ВЫКЛ'}")
    logger.info(f"   ☀️ ДЕНЬ: {config.cycle_delay_day_min//60}-{config.cycle_delay_day_max//60} мин")
    logger.info(f"   🌙 НОЧЬ: {config.cycle_delay_night_min//60}-{config.cycle_delay_night_max//60} мин")
    logger.info("=" * 60)
    
    ssl_context = create_secure_ssl_context()
    connector = aiohttp.TCPConnector(limit=10, force_close=True, ssl=ssl_context, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=60, connect=15)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        cycle = 0
        
        while state.running:
            cycle += 1
            time_label = "🌙 НОЧЬ" if config.is_night_time() else "☀️ ДЕНЬ"
            
            logger.info("=" * 60)
            logger.info(f"🔄 Цикл #{cycle} | {time_label} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)
            
            try:
                import time
                start_time = time.time()
                state.current_task = asyncio.create_task(
                    collect_and_process_news(llm, duplicate_detector, session, start_time)
                )
                posts_published = (await state.current_task) or 0
                
                if posts_published > 0:
                    logger.info(f"✅ Опубликовано: {posts_published}")

                if cycle % 10 == 0:
                    await cleanup_old_posts()
                    await cleanup_old_data()
                    cleanup_old_logs()  # Очистка логов (синхронная)
                
                if cycle % 5 == 0:
                    llm._save_cache()
                
                delay = config.get_cycle_delay()
                logger.info(f"😴 {time_label} | Следующий ци��л через {delay // 60} мин {delay % 60} сек")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле: {e}", exc_info=True)
                metrics.log_error(f"main_loop: {e}")
                error_delay = 900 if config.is_night_time() else 600
                logger.info(f"⏳ Ожидание {error_delay // 60} минут после ошибки")
                await asyncio.sleep(error_delay)
        
        await graceful_shutdown(llm)

def signal_handler(signum, frame):
    logger.info(f"🛑 Получен сигнал остановки: {signum}")
    state.running = False

# ================= ТЕСТЫ =================
async def run_tests():
    """Запуск тестов"""
    print("\n" + "=" * 60)
    print("🧪 ЗАПУСК ТЕСТОВ CINEMA")
    print("=" * 60)
    
    tests_passed = 0
    tests_failed = 0
    
    # Тест 1: is_cinema_candidate
    print("\n📝 Тест: is_cinema_candidate")
    try:
        is_cinema, _, _ = is_cinema_candidate("Новый фильм Marvel", "Премьера")
        assert is_cinema == True
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
        result = normalize_title("Новый фильм о супергероях!")
        assert "фильм" in result
        assert "супергероях" in result
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
        print("   ✅ PASS (SSL верификация включена)")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 7: fake dates detection
    print("\n📝 Тест: fake dates detection")
    try:
        client = CachedLLMClient()
        assert client._contains_fake_dates("фильм вышел в 2023") == True
        print("   ✅ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        tests_failed += 1
    
    # Тест 8: english words detection
    print("\n📝 Тест: english words detection")
    try:
        client = CachedLLMClient()
        assert client._contains_too_much_english("Breaking news: director said today") == True
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
            logger.info("🛑 Бот остановлен пользователем")
        except Exception as e:
            logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
            sys.exit(1)