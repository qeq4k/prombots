#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 Shared Package — общие компоненты для всех ботов

Единый пакет для переиспользования кода между:
- bot_handler.py
- politika.py
- economika.py
- urgent_news.py
- movie.py
"""
import os
import re
import json
import ssl
import time
import hashlib
import random
import logging
import asyncio
import aiofiles
import aiohttp
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ================= BOT CONFIG =================
@dataclass
class Draft:
    """✅ Черновик поста"""
    post_id: str
    channel_id: str
    text: str
    photo: str = ""
    created_at: str = ""
    status: str = "pending"
    suggestion_chat_id: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Draft":
        return cls(
            post_id=d.get("post_id", ""),
            channel_id=d.get("channel_id", ""),
            text=d.get("text", ""),
            photo=d.get("photo", ""),
            created_at=d.get("created_at", ""),
            status=d.get("status", "pending"),
            suggestion_chat_id=d.get("suggestion_chat_id", "")
        )

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "channel_id": self.channel_id,
            "text": self.text,
            "photo": self.photo,
            "created_at": self.created_at,
            "status": self.status,
            "suggestion_chat_id": self.suggestion_chat_id
        }


@dataclass
class BotConfig:
    """✅ Единая конфигурация для всех ботов"""
    tg_token: str = field(default_factory=lambda: os.getenv("TG_TOKEN", ""))
    admin_chat_id: str = field(default_factory=lambda: os.getenv("ALERTS_CHAT_ID", "-5181669116"))
    alerts_enabled: bool = True

    # Каналы
    tg_channel_cinema: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_CINEMA", ""))
    tg_channel_economy: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_ECONOMY", ""))
    tg_channel_politics: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_POLITICS", ""))

    # Предложки
    suggestion_chat_id_cinema: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_CINEMA", ""))
    suggestion_chat_id_economy: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_ECONOMY", ""))
    suggestion_chat_id_politics: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_POLITICS", ""))

    # LLM
    router_api_key: str = field(default_factory=lambda: os.getenv("ROUTER_API_KEY", ""))
    llm_base_url: str = "https://routerai.ru/v1"
    llm_model: str = "openai/gpt-oss-20b"

    # Директории
    pending_dir: Path = field(default_factory=lambda: Path("pending_posts"))
    edit_sessions_dir: Path = field(default_factory=lambda: Path("edit_sessions"))

    # Автопостинг
    autopost_enabled: bool = True
    autopost_day_min_minutes: int = 7
    autopost_day_max_minutes: int = 10
    autopost_night_min_minutes: int = 25
    autopost_night_max_minutes: int = 35
    autopost_night_start_hour: int = 22
    autopost_night_end_hour: int = 5
    autopost_check_interval: int = 60

    # Rate limiting
    cleanup_age_hours: int = 48
    cleanup_interval_hours: int = 6
    min_post_interval_minutes: int = 10
    long_polling_timeout: int = 30

    # Ночной режим
    night_start_hour: int = 22
    night_end_hour: int = 5

    # Лимиты
    max_posts_per_day: int = 48
    duplicate_check_hours: int = 72

    def __post_init__(self):
        self.pending_dir.mkdir(exist_ok=True)
        self.edit_sessions_dir.mkdir(exist_ok=True)
        self.suggestion_to_channel = {
            self.suggestion_chat_id_cinema: self.tg_channel_cinema,
            self.suggestion_chat_id_economy: self.tg_channel_economy,
            self.suggestion_chat_id_politics: self.tg_channel_politics,
        }
        self.autopost_allowed_suggestions = [
            self.suggestion_chat_id_cinema,
            self.suggestion_chat_id_economy,
            self.suggestion_chat_id_politics,
        ]
        self.channel_names = {
            self.tg_channel_cinema: "🎬 Кино",
            self.tg_channel_economy: "💰 Экономика",
            self.tg_channel_politics: "🏛️ Политика",
        }
        self.base_url = f"https://api.telegram.org/bot{self.tg_token}"

    def get_autopost_delay_minutes(self, hour: Optional[int] = None) -> float:
        if hour is None:
            hour = datetime.now(timezone.utc).hour
        # ✅ ИСПРАВЛЕНО: ночь с 22:00 до 05:00 (через полночь)
        if hour >= self.autopost_night_start_hour or hour < self.autopost_night_end_hour:
            return random.uniform(self.autopost_night_min_minutes, self.autopost_night_max_minutes)
        return random.uniform(self.autopost_day_min_minutes, self.autopost_day_max_minutes)

    def is_night_time(self, hour: Optional[int] = None) -> bool:
        if hour is None:
            hour = datetime.now(timezone.utc).hour
        return hour >= self.autopost_night_start_hour or hour < self.autopost_night_end_hour

    def get_channel_name(self, channel_id: str) -> str:
        return self.channel_names.get(channel_id, channel_id)

    @property
    def category(self) -> str:
        """✅ Автоматически определяет категорию по имени скрипта"""
        import sys
        script_name = Path(sys.argv[0]).stem.lower()
        if 'ekonom' in script_name or 'econ' in script_name:
            return "economy"
        elif 'kino' in script_name or 'film' in script_name or 'cinema' in script_name:
            return "cinema"
        else:
            return "politics"

    @property
    def bot_signature(self) -> str:
        """✅ Возвращает подпись канала для текущей категории"""
        cat = self.category
        if cat == "economy":
            return os.getenv("SIGNATURE_ECONOMY", "@eco_steroid")
        elif cat == "cinema":
            return os.getenv("SIGNATURE_CINEMA", "@Film_orbita")
        else:
            return os.getenv("SIGNATURE_POLITICS", "@I_Politika")

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


# ================= TELEGRAM CLIENT =================
class TelegramClient:
    """✅ Единый клиент для Telegram API с переиспользованием сессии"""

    def __init__(self, token: str = None, timeout: int = 60, limit: int = 10):
        self.token = token or os.getenv("TG_TOKEN", "")
        self.timeout = timeout
        self.limit = limit
        self.session: Optional[aiohttp.ClientSession] = None
        self._is_closed = False
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            ssl=ssl.create_default_context(),
            limit=self.limit
        )
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self

    async def __aexit__(self, *_):
        self._is_closed = True
        if self.session:
            await self.session.close()

    async def request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        if self._is_closed or self.session is None:
            logger.error("❌ Сессия закрыта")
            return None

        url = f"{self.base_url}/{endpoint}"
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with self.session.request(method, url, **kwargs) as resp:
                    result = await resp.json()

                    # ✅ ОБРАБОТКА ОШИБКИ 409 (Conflict)
                    if resp.status == 409:
                        error_desc = result.get("description", "Unknown")
                        logger.error(f"❌ ОШИБКА 409: {error_desc}")
                        logger.error("⚠️ Возможно запущен другой экземпляр бота!")
                        return None

                    # Обработка 429 Too Many Requests
                    if resp.status == 429:
                        retry_after = 30
                        try:
                            retry_after = int(resp.headers.get('Retry-After', 30))
                        except (ValueError, TypeError):
                            pass
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.warning(f"⚠️ 429 Too Many Requests, ждём {retry_after}с (попытка {retry_count}/{max_retries})")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            logger.error(f"❌ 429 после {max_retries} попыток")
                            return None

                    if resp.status == 200:
                        return result

                    logger.warning(f"⚠️ API {resp.status}: {result.get('description', 'Unknown')[:200]}")
                    return None

            except asyncio.CancelledError:
                raise
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"⚠️ Ошибка запроса, повтор {retry_count}/{max_retries}: {e}")
                    await asyncio.sleep(1 * retry_count)
                else:
                    logger.error(f"❌ Request error после {max_retries} попыток: {e}")
                    return None

        return None

    async def send_message(self, chat_id, text: str, parse_mode: str = "HTML",
                           reply_markup: Optional[dict] = None,
                           reply_to_message_id: Optional[int] = None) -> Optional[int]:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        result = await self.request("POST", "sendMessage", json=payload)
        if result and result.get("ok"):
            return result["result"].get("message_id")
        return None

    async def send_photo(self, chat_id: str, photo: str, caption: str = "",
                         parse_mode: str = "HTML") -> Tuple[bool, str]:
        # ✅ ПРОВЕРКА: валидный ли URL или file_id
        if not photo or photo in ("no", "None", "null", ""):
            return False, "Некорректное фото"
        
        # Проверяем что это URL или file_id (начинается с http://, https://, или base64/file_id)
        if not (photo.startswith(("http://", "https://", "file://", "attach://")) or 
                (len(photo) > 10 and photo[:100].isalnum())):
            logger.warning(f"⚠️ Некорректный URL фото: {photo[:100]}")
            return False, "Некорректный URL фото"
        
        payload = {
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption[:1024] if caption else "",
            "parse_mode": parse_mode
        }
        result = await self.request("POST", "sendPhoto", json=payload)
        if result and result.get("ok"):
            return True, "Опубликовано с фото"
        err = result.get("description", "Unknown") if result else "Request failed"
        return False, f"Ошибка: {err[:100]}"

    async def delete_message(self, chat_id, message_id: int):
        await self.request("POST", "deleteMessage", json={"chat_id": chat_id, "message_id": message_id})

    async def answer_callback_query(self, query_id: str):
        await self.request("POST", "answerCallbackQuery", json={"callback_query_id": query_id})

    async def get_bot_info(self) -> Optional[dict]:
        result = await self.request("GET", "getMe")
        return result["result"] if result and result.get("ok") else None


# ================= ALERT MANAGER =================
class AlertManager:
    """✅ Единый менеджер алертов для всех ботов"""

    def __init__(self, telegram: TelegramClient = None, chat_id: str = None, cooldown_minutes: int = 30):
        self.telegram = telegram
        self.chat_id = chat_id or os.getenv("ALERTS_CHAT_ID", "-5181669116")
        self.cooldown_minutes = cooldown_minutes
        self.cooldowns: Dict[str, float] = {}
        self.cooldowns_file = Path("alert_cooldowns.json")
        self._load_cooldowns()

    def _load_cooldowns(self):
        try:
            if self.cooldowns_file.exists():
                with open(self.cooldowns_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.cooldowns = data
                # Очищаем старые cooldowns
                cutoff = time.time() - (self.cooldown_minutes * 60)
                self.cooldowns = {k: v for k, v in self.cooldowns.items() if v > cutoff}
        except Exception as e:
            self.cooldowns = {}

    def _save_cooldowns(self):
        try:
            with open(self.cooldowns_file, 'w', encoding='utf-8') as f:
                json.dump(self.cooldowns, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _can_send(self, key: str) -> bool:
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

        text = f"{emoji} <b>{title}</b>\n{message}\n<i>{datetime.now(timezone.utc).strftime('%H:%M:%S')}</i>"

        if self.telegram and self.telegram.session:
            # Используем переиспользуемую сессию
            await self.telegram.send_message(int(self.chat_id), text)
        else:
            # Fallback: создаём новую сессию
            import aiohttp
            ssl_ctx = ssl.create_default_context()
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{os.getenv('TG_TOKEN', '')}/sendMessage"
                payload = {
                    "chat_id": int(self.chat_id),
                    "text": text,
                    "parse_mode": "HTML"
                }
                async with session.post(url, json=payload, ssl=ssl_ctx, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Алерт отправлен: {title}")

        if key:
            self.cooldowns[key] = time.time()
            self._save_cooldowns()

    async def alert_critical(self, title: str, msg: str, key: str = None):
        await self.send_alert("🚨", title, msg, key)

    async def alert_warning(self, title: str, msg: str, key: str = None):
        await self.send_alert("⚠️", title, msg, key)

    async def alert_info(self, title: str, msg: str, key: str = None):
        await self.send_alert("ℹ️", title, msg, key)


# ================= УТИЛИТЫ =================
def strip_html_tags(text: str) -> str:
    """✅ Удаление HTML тегов"""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    return clean.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


def normalize_text_for_dedup(text: str) -> str:
    """✅ Нормализация текста для дедупликации"""
    if not text:
        return ""
    text = strip_html_tags(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()


def format_text_for_channel(text: str) -> str:
    """✅ Форматирование текста для канала"""
    if not text or not text.strip():
        return text
    lines = text.split('\n', 1)
    header = lines[0].strip()
    # ✅ ПРОВЕРЯЕМ: если уже есть <b> в любом месте — не добавляем
    if '<b>' not in header:
        header = f"<b>{header}</b>"
    return header if len(lines) == 1 else f"{header}\n{lines[1]}"


async def write_draft_atomic(draft_path: Path, data: dict):
    """✅ Атомарная запись черновика"""
    temp_path = draft_path.with_suffix(".tmp")
    try:
        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.replace(temp_path, draft_path)
    except Exception as e:
        logger.error(f"❌ Ошибка атомарной записи {draft_path.name}: {e}")
        temp_path.unlink(missing_ok=True)
        raise


async def read_draft(draft_path: Path) -> Optional[Draft]:
    """✅ Чтение черновика — возвращает Draft объект"""
    try:
        async with aiofiles.open(draft_path, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        return Draft.from_dict(data)
    except Exception as e:
        logger.error(f"❌ Чтение {draft_path.name}: {e}")
        return None


async def delete_draft(draft_path: Path):
    """✅ Удаление черновика"""
    try:
        draft_path.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"❌ Удаление {draft_path.name}: {e}")


def is_russian_text(text: str, min_ratio: float = 0.7) -> bool:
    """✅ Проверка: является ли текст русским"""
    try:
        from langdetect import detect, LangDetectException
        lang = detect(text[:500])
        if lang == "ru":
            return True
    except (ImportError, Exception):
        pass

    # Fallback: подсчёт кириллицы
    cyrillic = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF or c in "ёЁ")
    alpha = sum(1 for c in text if c.isalpha())
    return alpha > 0 and (cyrillic / alpha) >= min_ratio


def get_content_hash(title: str, body: str, category: str = "") -> str:
    """
    ✅ Создаёт хеш для дедупликации.
    Использует глобальную нормализацию если доступна.
    """
    try:
        from global_dedup import get_content_dedup_hash
        return get_content_dedup_hash(title, body, category)
    except ImportError:
        # Fallback без зависимости от global_dedup
        raw = f"{title.lower()}|{body[:400].lower()}|{category.lower()}"
        return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


# ================= EDIT SESSION =================
@dataclass
class EditSession:
    """✅ Сессия редактирования поста"""
    post_id: str
    channel_id: str
    text: str
    photo: str = ""
    original_file: Optional[Path] = None
    request_msg_id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "channel_id": self.channel_id,
            "text": self.text,
            "photo": self.photo,
            "original_file": str(self.original_file) if self.original_file else None,
            "request_msg_id": self.request_msg_id
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EditSession":
        return cls(
            post_id=d.get("post_id", ""),
            channel_id=d.get("channel_id", ""),
            text=d.get("text", ""),
            photo=d.get("photo", ""),
            original_file=Path(d["original_file"]) if d.get("original_file") else None,
            request_msg_id=d.get("request_msg_id")
        )


async def save_edit_session(session: EditSession, session_file: Path):
    """✅ Сохранение сессии редактирования"""
    try:
        async with aiofiles.open(session_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(session.to_dict(), ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"❌ Сохранение сессии {session_file}: {e}")


async def load_edit_session(session_file: Path) -> Optional[EditSession]:
    """✅ Загрузка сессии редактирования"""
    try:
        async with aiofiles.open(session_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        return EditSession.from_dict(data)
    except Exception as e:
        logger.error(f"❌ Загрузка сессии {session_file}: {e}")
        return None


async def load_all_edit_sessions(sessions_dir: Path) -> Dict[int, EditSession]:
    """
    ✅ Загрузка всех сессий редактирования при старте.
    Возвращает dict {chat_id: EditSession}
    """
    sessions = {}
    sessions_dir.mkdir(exist_ok=True)

    for session_file in sessions_dir.glob("*.json"):
        try:
            session = await load_edit_session(session_file)
            if session:
                # chat_id это имя файла без расширения
                chat_id = int(session_file.stem)
                sessions[chat_id] = session
                logger.info(f"📦 Восстановлена сессия редактирования: chat_id={chat_id}, post_id={session.post_id}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить сессию {session_file}: {e}")

    return sessions


# ================= GLOBAL DEDUP CHECK =================
def check_global_dedup_available() -> bool:
    """
    ✅ Проверка доступности global_dedup.py
    Returns: True если модуль доступен
    """
    try:
        from global_dedup import get_content_dedup_hash, init_global_db
        return True
    except ImportError:
        return False


def require_global_dedup(exit_on_missing: bool = True) -> bool:
    """
    ✅ Обязательная проверка global_dedup.py
    Если exit_on_missing=True — аварийно завершает программу при отсутствии модуля.
    """
    if check_global_dedup_available():
        logger.info("✅ global_dedup.py доступен")
        return True

    logger.error("❌ КРИТИЧЕСКОЕ: global_dedup.py не найден!")
    logger.error("❌ Без глобальной дедупликации работа бота невозможна")

    if exit_on_missing:
        logger.error("❌ Аварийная остановка — добавьте global_dedup.py")
        import sys
        sys.exit(1)

    return False


# Import asyncio for the TelegramClient
import asyncio

# Экспорт всего публичного API
__all__ = [
    # Config
    "BotConfig",
    # Telegram Client
    "TelegramClient",
    # Alert Manager
    "AlertManager",
    # Edit Session
    "EditSession",
    "save_edit_session",
    "load_edit_session",
    "load_all_edit_sessions",
    # Utils
    "strip_html_tags",
    "normalize_text_for_dedup",
    "format_text_for_channel",
    "write_draft_atomic",
    "read_draft",
    "delete_draft",
    "is_russian_text",
    "get_content_hash",
    # Global dedup check
    "check_global_dedup_available",
    "require_global_dedup",
]
