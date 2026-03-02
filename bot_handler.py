#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Bot Handler — ASYNC 2026 FINAL
✅ parse_callback_data поддерживает оба формата (: и _)
✅ Дубликаты из pending удаляются автоматически
✅ Логи рутины на DEBUG
✅ Исправлен write_draft_atomic
✅ Graceful shutdown
"""
import os
import sys
import json
import hashlib
import logging
import signal
import asyncio
import ssl
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field
import random
import aiohttp
from dotenv import load_dotenv

try:
    from global_dedup import (
        init_global_db,
        is_global_duplicate,
        mark_global_posted,
        cleanup_global_db
    )
    GLOBAL_DEDUP_ENABLED = True
except ImportError:
    GLOBAL_DEDUP_ENABLED = False
    logging.warning("⚠️ global_dedup.py не найден — дедупликация отключена")

load_dotenv()


# ================= КОНФИГУРАЦИЯ =================
@dataclass
class BotConfig:
    tg_token: str = field(default_factory=lambda: os.getenv("TG_TOKEN", ""))
    admin_chat_id: str = field(default_factory=lambda: os.getenv("ALERTS_CHAT_ID", ""))
    alerts_enabled: bool = True

    tg_channel_cinema: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_CINEMA", ""))
    tg_channel_economy: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_ECONOMY", ""))
    tg_channel_politics: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_POLITICS", ""))

    suggestion_chat_id_cinema: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_CINEMA", ""))
    suggestion_chat_id_economy: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_ECONOMY", ""))
    suggestion_chat_id_politics: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_POLITICS", ""))

    pending_dir: Path = field(default_factory=lambda: Path("pending_posts"))

    autopost_enabled: bool = True
    autopost_day_min_minutes: int = 7
    autopost_day_max_minutes: int = 10
    autopost_night_min_minutes: int = 25
    autopost_night_max_minutes: int = 35
    autopost_night_start_hour: int = 1
    autopost_night_end_hour: int = 8
    autopost_check_interval: int = 60

    cleanup_age_hours: int = 48
    cleanup_interval_hours: int = 6
    min_post_interval_minutes: int = 10
    long_polling_timeout: int = 30

    def __post_init__(self):
        self.pending_dir.mkdir(exist_ok=True)
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
            hour = datetime.now().hour
        if self.autopost_night_start_hour <= hour < self.autopost_night_end_hour:
            return random.uniform(self.autopost_night_min_minutes, self.autopost_night_max_minutes)
        return random.uniform(self.autopost_day_min_minutes, self.autopost_day_max_minutes)

    def is_night_time(self, hour: Optional[int] = None) -> bool:
        if hour is None:
            hour = datetime.now().hour
        return self.autopost_night_start_hour <= hour < self.autopost_night_end_hour

    def get_channel_name(self, channel_id: str) -> str:
        return self.channel_names.get(channel_id, channel_id)


config = BotConfig()

# ================= ЛОГИРОВАНИЕ =================
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_dir / "bot_handler.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ================= МОДЕЛИ =================
@dataclass
class Draft:
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
            "post_id": self.post_id, "channel_id": self.channel_id,
            "text": self.text, "photo": self.photo,
            "created_at": self.created_at, "status": self.status,
            "suggestion_chat_id": self.suggestion_chat_id
        }


@dataclass
class EditSession:
    post_id: str
    channel_id: str
    text: str
    photo: str = ""
    original_file: Optional[Path] = None
    request_msg_id: Optional[int] = None


# ================= УТИЛИТЫ =================
def format_text_for_channel(text: str) -> str:
    if not text or not text.strip():
        return text
    lines = text.split('\n', 1)
    header = lines[0].strip()
    if not header.startswith('<b>'):
        header = f"<b>{header}</b>"
    return header if len(lines) == 1 else f"{header}\n{lines[1]}"


async def write_draft_atomic(draft_path: Path, data: dict):
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
    try:
        async with aiofiles.open(draft_path, 'r', encoding='utf-8') as f:
            return Draft.from_dict(json.loads(await f.read()))
    except Exception as e:
        logger.error(f"❌ Чтение {draft_path.name}: {e}")
        return None


async def write_draft(draft_path: Path, draft: Draft):
    await write_draft_atomic(draft_path, draft.to_dict())


async def delete_draft(draft_path: Path):
    try:
        draft_path.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"❌ Удаление {draft_path.name}: {e}")


# ✅ ГЛАВНОЕ ИСПРАВЛЕНИЕ: поддержка ОБОИХ форматов — ":" и "_"
def parse_callback_data(data: str) -> Tuple[str, str, str]:
    data = (data or "").strip()
    if not data:
        return "", "", ""

    # Формат с двоеточием: publish:channel:post  /  edit:post  /  reject:post
    if ":" in data:
        parts = data.split(":")
        action = parts[0]
        if action == "publish" and len(parts) >= 3:
            # channel_id может содержать ":", берём всё между первым и последним
            post_id = parts[-1]
            channel_id = ":".join(parts[1:-1])
            return action, channel_id, post_id
        if action in ("edit", "reject") and len(parts) >= 2:
            return action, "", parts[1]
        return "", "", ""

    # Старый формат с подчёркиванием: publish_channel_post  /  edit_post  /  reject_post
    parts = data.split("_")
    action = parts[0]
    if action == "publish" and len(parts) >= 3:
        post_id = parts[-1]
        channel_id = "_".join(parts[1:-1])  # channel_id может содержать "_"
        return action, channel_id, post_id
    if action in ("edit", "reject") and len(parts) >= 2:
        return action, "", parts[1]

    return "", "", ""


# ================= TELEGRAM CLIENT =================
class TelegramClient:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(), limit=10)
        self.session = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=60))
        return self

    async def __aexit__(self, *_):
        if self.session:
            await self.session.close()

    async def request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        url = f"{config.base_url}/{endpoint}"
        try:
            async with self.session.request(method, url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"⚠️ API {resp.status}: {(await resp.text())[:200]}")
                return None
        except Exception as e:
            logger.error(f"❌ Request error: {e}")
            return None

    async def send_message(self, chat_id, text: str, parse_mode: str = "HTML",
                           reply_markup: Optional[dict] = None) -> Optional[int]:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                   "disable_web_page_preview": False}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = await self.request("POST", "sendMessage", json=payload)
        if result and result.get("ok"):
            return result["result"].get("message_id")
        return None

    async def send_photo(self, chat_id: str, photo: str, caption: str = "",
                         parse_mode: str = "HTML") -> Tuple[bool, str]:
        payload = {"chat_id": chat_id, "photo": photo,
                   "caption": format_text_for_channel(caption)[:1024] if caption else "",
                   "parse_mode": parse_mode}
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


# ================= АЛЕРТЫ =================
class AlertManager:
    def __init__(self, telegram: TelegramClient, cfg: BotConfig):
        self.telegram = telegram
        self.config = cfg
        self.cooldowns: Dict[str, datetime] = {}
        self.cooldown_minutes = 30

    def _can_send(self, key: str) -> bool:
        if not self.config.alerts_enabled or not self.config.admin_chat_id:
            return False
        last = self.cooldowns.get(key)
        return not (last and (datetime.now() - last).total_seconds() < self.cooldown_minutes * 60)

    async def send_alert(self, emoji: str, title: str, message: str, key: Optional[str] = None):
        if key and not self._can_send(key):
            return
        if not self.config.alerts_enabled or not self.config.admin_chat_id:
            return
        try:
            text = f"{emoji} <b>{title}</b>\n{message}\n<i>{datetime.now().strftime('%H:%M:%S')}</i>"
            await self.telegram.send_message(int(self.config.admin_chat_id), text)
            if key:
                self.cooldowns[key] = datetime.now()
        except Exception as e:
            logger.error(f"❌ Алерт не отправлен: {e}")

    async def alert_critical(self, title: str, msg: str, key: Optional[str] = None):
        await self.send_alert("🚨", title, msg, key)

    async def alert_warning(self, title: str, msg: str, key: Optional[str] = None):
        await self.send_alert("⚠️", title, msg, key)

    async def alert_info(self, title: str, msg: str, key: Optional[str] = None):
        await self.send_alert("ℹ️", title, msg, key)

    async def alert_success(self, title: str, msg: str):
        await self.send_alert("✅", title, msg)


# ================= BOT HANDLER =================
shutdown_event = asyncio.Event()


class BotHandler:
    def __init__(self):
        self.telegram: Optional[TelegramClient] = None
        self.alert_manager: Optional[AlertManager] = None
        self.edit_sessions: Dict[int, EditSession] = {}
        self.autopost_tasks: Dict[str, asyncio.Task] = {}
        self.sessions_dir = Path("edit_sessions")
        self.sessions_dir.mkdir(exist_ok=True)
        self.published_hashes: Dict[str, Tuple[str, datetime]] = {}
        self.published_hashes_ttl = timedelta(hours=2)

    # ── Сессии ──────────────────────────────────
    async def _save_session(self, chat_id: int):
        s = self.edit_sessions.get(chat_id)
        if not s:
            return
        try:
            await write_draft_atomic(self.sessions_dir / f"{chat_id}.json", {
                "post_id": s.post_id, "channel_id": s.channel_id, "text": s.text,
                "photo": s.photo,
                "original_file": str(s.original_file) if s.original_file else None,
                "request_msg_id": s.request_msg_id
            })
        except Exception as e:
            logger.error(f"❌ Сохранение сессии {chat_id}: {e}")

    async def _load_session(self, chat_id: int) -> Optional[EditSession]:
        try:
            f = self.sessions_dir / f"{chat_id}.json"
            if not f.exists():
                return None
            async with aiofiles.open(f, 'r', encoding='utf-8') as fh:
                d = json.loads(await fh.read())
            s = EditSession(
                post_id=d["post_id"], channel_id=d["channel_id"], text=d["text"],
                photo=d.get("photo", ""),
                original_file=Path(d["original_file"]) if d.get("original_file") else None,
                request_msg_id=d.get("request_msg_id")
            )
            self.edit_sessions[chat_id] = s
            return s
        except Exception as e:
            logger.error(f"❌ Загрузка сессии {chat_id}: {e}")
            return None

    async def _delete_session(self, chat_id: int):
        try:
            (self.sessions_dir / f"{chat_id}.json").unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"❌ Удаление сессии {chat_id}: {e}")
        self.edit_sessions.pop(chat_id, None)

    async def load_all_sessions(self):
        loaded = 0
        for f in self.sessions_dir.glob("*.json"):
            try:
                await self._load_session(int(f.stem))
                loaded += 1
            except Exception as e:
                logger.warning(f"⚠️ Сессия {f.name}: {e}")
        if loaded:
            logger.info(f"📦 Загружено сессий: {loaded}")

    # ── Дедупликация ────────────────────────────
    def _get_category(self, channel_id: str) -> str:
        """Определить категорию по ID канала"""
        if channel_id == self.tg_channel_politics:
            return "politics"
        elif channel_id == self.tg_channel_economy:
            return "economy"
        elif channel_id == self.tg_channel_cinema:
            return "cinema"
        return ""

    def _get_content_hash(self, text: str, channel_id: str) -> str:
        return hashlib.sha256(f"{text[:300]}|{channel_id}".encode("utf-8", errors="ignore")).hexdigest()

    def _cleanup_published_cache(self):
        cutoff = datetime.now() - self.published_hashes_ttl
        self.published_hashes = {k: v for k, v in self.published_hashes.items() if v[1] > cutoff}

    async def _is_duplicate(self, text: str, channel_id: str) -> bool:
        h = self._get_content_hash(text, channel_id)
        if h in self.published_hashes:
            _, ts = self.published_hashes[h]
            if datetime.now() - ts < self.published_hashes_ttl:
                logger.debug(f"⏭️ Дубликат в кэше: {h[:12]}")
                return True
        if GLOBAL_DEDUP_ENABLED:
            try:
                category = self._get_category(channel_id)
                if await is_global_duplicate(h, category, hours=24):
                    logger.debug(f"⏭️ Глобальный дубликат: {h[:12]}")
                    return True
            except Exception as e:
                logger.warning(f"⚠️ Ошибка глобального дубликата: {e}")
        return False

    async def _mark_published(self, text: str, channel_id: str):
        h = self._get_content_hash(text, channel_id)
        self.published_hashes[h] = (channel_id, datetime.now())
        if GLOBAL_DEDUP_ENABLED:
            try:
                category = self._get_category(channel_id)
                await mark_global_posted(h, channel_id, "bot_handler", text.split('\n')[0][:100], category)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка отметки БД: {e}")
        if len(self.published_hashes) % 50 == 0:
            self._cleanup_published_cache()

    # ── Публикация ──────────────────────────────
    async def publish_post(self, text: str, channel_id: str, photo: str = "") -> Tuple[bool, str]:
        if not text or len(text) < 10:
            return False, "Текст слишком короткий"
        if await self._is_duplicate(text, channel_id):
            return False, "Дубликат"
        try:
            formatted = format_text_for_channel(text)
            if photo:
                success, result = await self.telegram.send_photo(channel_id, photo, formatted)
            else:
                msg_id = await self.telegram.send_message(channel_id, formatted)
                success, result = bool(msg_id), ("Опубликовано" if msg_id else "Ошибка отправки")
            if success:
                await self._mark_published(text, channel_id)
            return success, result
        except Exception as e:
            logger.error(f"❌ Ошибка публикации: {e}")
            if self.alert_manager:
                await self.alert_manager.alert_critical(
                    f"Ошибка публикации — {config.get_channel_name(channel_id)}",
                    f"<code>{str(e)[:200]}</code>", key=f"publish_error_{channel_id}"
                )
            return False, str(e)[:100]

    # ── Автопостинг ─────────────────────────────
    def cancel_autopost(self, post_id: str):
        if post_id in self.autopost_tasks:
            self.autopost_tasks[post_id].cancel()
            del self.autopost_tasks[post_id]

    async def autopost_draft(self, draft_path: Path, post_id: str):
        try:
            draft = await read_draft(draft_path)
            if not draft:
                await delete_draft(draft_path)
                return
            if draft.suggestion_chat_id not in config.autopost_allowed_suggestions:
                return

            logger.debug(f"🌙 Автопост {post_id} → {draft.channel_id}")
            success, result = await self.publish_post(draft.text, draft.channel_id, draft.photo)

            if success:
                await delete_draft(draft_path)
                logger.info(f"✅ Автопост опубликован: {post_id}")
                if self.alert_manager:
                    await self.alert_manager.alert_info(
                        f"Автопостинг — {config.get_channel_name(draft.channel_id)}",
                        f"Превью: {draft.text[:100]}..."
                    )
            elif result == "Дубликат":
                logger.debug(f"🗑️ Дубликат удалён из pending: {post_id}")
                await delete_draft(draft_path)
            else:
                logger.warning(f"⚠️ Автопост не удался {post_id}: {result}")
                if self.alert_manager:
                    await self.alert_manager.alert_warning(
                        f"Автопост не удался — {config.get_channel_name(draft.channel_id)}",
                        f"Пост: {post_id}\nОшибка: {result}",
                        key=f"autopost_fail_{post_id}"
                    )
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка автопоста {post_id}: {e}")
        finally:
            self.autopost_tasks.pop(post_id, None)

    async def autopost_after_delay(self, draft_path: Path, post_id: str, delay: float):
        try:
            await asyncio.sleep(delay)
            await self.autopost_draft(draft_path, post_id)
        except asyncio.CancelledError:
            logger.debug(f"⏹️ Автопост {post_id} отменён")

    async def schedule_autopost(self, draft_path: Path):
        if not config.autopost_enabled:
            return
        post_id = draft_path.stem
        if post_id in self.autopost_tasks:
            return
        try:
            draft = await read_draft(draft_path)
            if not draft or draft.suggestion_chat_id not in config.autopost_allowed_suggestions:
                return
            hour = datetime.now().hour
            delay_sec = max(10, config.get_autopost_delay_minutes(hour) * 60
                            - (datetime.now().timestamp() - draft_path.stat().st_mtime))
            task = asyncio.create_task(self.autopost_after_delay(draft_path, post_id, delay_sec))
            self.autopost_tasks[post_id] = task
            logger.debug(f"⏰ Запланирован {post_id} через {delay_sec / 60:.1f} мин")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка планирования {post_id}: {e}")

    # ── Кнопки ──────────────────────────────────
    async def handle_publish_button(self, chat_id: int, channel_id: str, post_id: str, draft_path: Path):
        self.cancel_autopost(post_id)
        if not draft_path.exists():
            await self.telegram.send_message(chat_id, f"❌ Черновик <code>{post_id}</code> не найден")
            return
        try:
            draft = await read_draft(draft_path)
            if not draft:
                return
            if not channel_id or channel_id in ("undefined", ""):
                channel_id = draft.channel_id
            success, result = await self.publish_post(draft.text, channel_id, draft.photo)
            await self.telegram.send_message(
                chat_id,
                f"{'✅' if success else '❌'} {result}\n"
                f"Пост: <code>{post_id}</code>\nКанал: <code>{channel_id}</code>"
            )
            if success:
                await delete_draft(draft_path)
                logger.info(f"✅ Опубликован {post_id} → {channel_id}")
        except Exception as e:
            logger.exception(f"❌ Публикация {post_id}: {e}")
            await self.telegram.send_message(chat_id, f"❌ Ошибка: {str(e)[:150]}")

    async def handle_edit_button(self, chat_id: int, post_id: str, draft_path: Path, msg_id: Optional[int]):
        self.cancel_autopost(post_id)
        if not draft_path.exists():
            await self.telegram.send_message(chat_id, "❌ Черновик не найден")
            return
        try:
            draft = await read_draft(draft_path)
            if not draft:
                return
            if msg_id:
                await self.telegram.delete_message(chat_id, msg_id)
            preview = draft.text[:200] + "..." if len(draft.text) > 200 else draft.text
            new_msg_id = await self.telegram.send_message(
                chat_id,
                f"✏️ Режим редактирования\n"
                f"Канал: <code>{draft.channel_id}</code>\n"
                f"ID: <code>{post_id}</code>\n\n"
                f"Текущий текст:\n{preview}\n\n"
                f"Отправь новый текст, затем:\n"
                f"<code>/publish</code> — опубликовать\n"
                f"<code>/reject</code> — отклонить"
            )
            self.edit_sessions[chat_id] = EditSession(
                post_id=post_id, channel_id=draft.channel_id,
                text=draft.text, photo=draft.photo,
                original_file=draft_path, request_msg_id=new_msg_id
            )
            await self._save_session(chat_id)
            logger.info(f"✏️ {post_id} → редактирование")
        except Exception as e:
            logger.exception(f"❌ Редактирование {post_id}: {e}")
            await self.telegram.send_message(chat_id, f"❌ Ошибка: {str(e)[:100]}")

    async def handle_reject_button(self, chat_id: int, post_id: str, draft_path: Path):
        self.cancel_autopost(post_id)
        if draft_path.exists():
            await delete_draft(draft_path)
            await self.telegram.send_message(chat_id, f"✅ Черновик <code>{post_id}</code> отклонён")
            logger.info(f"❌ {post_id} отклонён")
        else:
            await self.telegram.send_message(chat_id, f"⚠️ Черновик <code>{post_id}</code> не найден")

    async def handle_callback(self, update: dict):
        cb = update.get("callback_query", {})
        query_id = cb.get("id")
        data = cb.get("data", "").strip()
        msg = cb.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        msg_id = msg.get("message_id")

        await self.telegram.answer_callback_query(query_id)

        if not chat_id:
            logger.error("❌ callback без chat_id")
            return

        action, channel_id, post_id = parse_callback_data(data)
        logger.debug(f"📥 Callback: raw='{data}' → action='{action}' channel='{channel_id}' post='{post_id}'")

        if not action or not post_id:
            logger.error(f"❌ Некорректные callback данные: '{data}'")
            await self.telegram.send_message(chat_id, f"❌ Некорректные данные кнопки\nДанные: <code>{data}</code>")
            return

        draft_path = config.pending_dir / f"{post_id}.json"

        if action == "publish":
            await self.handle_publish_button(chat_id, channel_id, post_id, draft_path)
        elif action == "edit":
            await self.handle_edit_button(chat_id, post_id, draft_path, msg_id)
        elif action == "reject":
            await self.handle_reject_button(chat_id, post_id, draft_path)
        else:
            logger.warning(f"⚠️ Неизвестное действие: '{action}'")

    # ── Сообщения ────────────────────────────────
    async def handle_message(self, update: dict):
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        if not chat_id:
            return

        photo_file_id = ""
        if "photo" in msg and msg["photo"]:
            photo_file_id = msg["photo"][-1].get("file_id", "")
            text = msg.get("caption", "").strip()

        session = self.edit_sessions.get(chat_id) or await self._load_session(chat_id)

        if text.lower() == "/publish":
            if not session:
                await self.telegram.send_message(chat_id, "❌ Нет активной сессии редактирования")
                return
            if not session.text or len(session.text) < 10:
                await self.telegram.send_message(chat_id, "❌ Текст слишком короткий")
                return
            try:
                self.cancel_autopost(session.post_id)
                success, result = await self.publish_post(session.text, session.channel_id, session.photo)
                await self.telegram.send_message(
                    chat_id,
                    f"{'✅' if success else '❌'} {result}\n"
                    f"Пост: <code>{session.post_id}</code>\nКанал: <code>{session.channel_id}</code>"
                )
                if success and session.original_file and session.original_file.exists():
                    await delete_draft(session.original_file)
                await self._delete_session(chat_id)
                logger.info(f"✅ /publish {session.post_id} → {session.channel_id}")
            except Exception as e:
                logger.exception(f"❌ /publish: {e}")
                await self.telegram.send_message(chat_id, f"❌ Ошибка: {str(e)[:150]}")
            return

        if text.lower() == "/reject":
            if session:
                self.cancel_autopost(session.post_id)
                if session.original_file and session.original_file.exists():
                    await delete_draft(session.original_file)
                await self._delete_session(chat_id)
                await self.telegram.send_message(chat_id, f"✅ Черновик <code>{session.post_id}</code> отклонён")
            else:
                await self.telegram.send_message(chat_id, "❌ Нет активной сессии")
            return

        if session and not (text and text.lower().startswith("/")):
            if chat_id not in self.edit_sessions:
                self.edit_sessions[chat_id] = session
            session = self.edit_sessions[chat_id]
            session.text = text
            if photo_file_id:
                session.photo = photo_file_id
            await self._save_session(chat_id)
            if session.request_msg_id:
                await self.telegram.delete_message(chat_id, session.request_msg_id)
                session.request_msg_id = None
            preview = text[:150] + "..." if len(text) > 150 else text
            await self.telegram.send_message(
                chat_id,
                f"✅ Текст сохранён!\n"
                f"Канал: <code>{session.channel_id}</code>\n"
                f"Превью: {preview}\n\n"
                f"<code>/publish</code> — опубликовать\n"
                f"<code>/reject</code> — отклонить\n"
                f"ID: <code>{session.post_id}</code>"
            )

    # ── Воркеры ──────────────────────────────────
    async def autopost_worker(self):
        if not config.autopost_enabled:
            logger.info("🌙 Автопостинг отключён")
            return
        logger.info(f"🌙 Автопостинг запущен | День: {config.autopost_day_min_minutes}-{config.autopost_day_max_minutes} мин | Ночь: {config.autopost_night_min_minutes}-{config.autopost_night_max_minutes} мин")
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(config.autopost_check_interval)
                if shutdown_event.is_set():
                    break
                now = datetime.now().timestamp()
                delay_min = config.get_autopost_delay_minutes()
                for draft_path in list(config.pending_dir.glob("*.json")):
                    if shutdown_event.is_set():
                        break
                    post_id = draft_path.stem
                    if post_id in self.autopost_tasks:
                        continue
                    if any(s.post_id == post_id for s in self.edit_sessions.values()):
                        continue
                    draft = await read_draft(draft_path)
                    if not draft:
                        await delete_draft(draft_path)
                        continue
                    if draft.suggestion_chat_id not in config.autopost_allowed_suggestions:
                        continue
                    age_min = (now - draft_path.stat().st_mtime) / 60
                    if age_min >= delay_min * 0.95:
                        await self.autopost_draft(draft_path, post_id)
                    else:
                        await self.schedule_autopost(draft_path)
            except Exception as e:
                logger.exception(f"⚠️ autopost_worker: {e}")
                await asyncio.sleep(30)
        logger.info("🌙 autopost_worker завершён")

    async def cleanup_worker(self):
        logger.info(f"🧹 Очистка запущена (каждые {config.cleanup_interval_hours} ч)")
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(config.cleanup_interval_hours * 3600)
                if shutdown_event.is_set():
                    break
                self._cleanup_published_cache()
                threshold = datetime.now() - timedelta(hours=config.cleanup_age_hours)
                deleted = 0
                for fp in config.pending_dir.glob("*.json"):
                    try:
                        if fp.stem in self.autopost_tasks:
                            continue
                        if any(s.post_id == fp.stem for s in self.edit_sessions.values()):
                            continue
                        if datetime.fromtimestamp(fp.stat().st_mtime) < threshold:
                            fp.unlink(missing_ok=True)
                            deleted += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Очистка {fp.name}: {e}")
                if deleted:
                    logger.info(f"🧹 Удалено старых файлов: {deleted}")
                if GLOBAL_DEDUP_ENABLED:
                    try:
                        n = await cleanup_global_db(days=30)
                        if n:
                            logger.info(f"🧹 Глобальная БД: удалено {n} записей")
                    except Exception as e:
                        logger.warning(f"⚠️ Очистка глобальной БД: {e}")
            except Exception as e:
                logger.exception(f"⚠️ cleanup_worker: {e}")
                await asyncio.sleep(3600)
        logger.info("🧹 cleanup_worker завершён")

    async def polling_worker(self):
        offset = None
        logger.info("✅ Бот запущен, ожидаю сообщения...")
        while not shutdown_event.is_set():
            try:
                params = {"timeout": config.long_polling_timeout}
                if offset:
                    params["offset"] = offset
                result = await self.telegram.request("GET", "getUpdates", params=params)
                if not result or not result.get("ok"):
                    await asyncio.sleep(3)
                    continue
                for update in result.get("result", []):
                    if shutdown_event.is_set():
                        break
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        await self.handle_callback(update)
                    elif "message" in update:
                        if update["message"]["chat"].get("type") in ("supergroup", "channel", "private"):
                            await self.handle_message(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"❌ polling: {e}")
                await asyncio.sleep(5)
        logger.info("📡 polling_worker завершён")

    async def run(self):
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК BOT HANDLER")
        logger.info(f"📁 pending_posts: {config.pending_dir.absolute()}")
        logger.info(f"⏰ Автопостинг: {'✅ ВКЛ' if config.autopost_enabled else '❌ ВЫКЛ'}")
        logger.info(f"🔗 Глобальная дедупликация: {'✅ ВКЛ' if GLOBAL_DEDUP_ENABLED else '❌ ВЫКЛ'}")
        logger.info("=" * 60)

        async with TelegramClient() as tg:
            self.telegram = tg
            self.alert_manager = AlertManager(self.telegram, config)

            if GLOBAL_DEDUP_ENABLED:
                try:
                    await init_global_db()
                    logger.info("✅ Глобальная БД инициализирована")
                except Exception as e:
                    logger.error(f"❌ Ошибка глобальной БД: {e}")

            bot_info = await self.telegram.get_bot_info()
            if not bot_info:
                logger.error("❌ Не удалось получить info бота — проверь TG_TOKEN")
                return
            logger.info(f"🤖 Бот: @{bot_info.get('username')}")
            await self.alert_manager.alert_success("Bot Handler запущен", f"@{bot_info.get('username')}")
            await self.load_all_sessions()

            tasks = [
                asyncio.create_task(self.polling_worker(), name="Polling"),
                asyncio.create_task(self.autopost_worker(), name="Autopost"),
                asyncio.create_task(self.cleanup_worker(), name="Cleanup"),
            ]
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                pass
            logger.info("👋 Бот остановлен")

    def shutdown(self):
        logger.info(f"🛑 Завершение, отмена {len(self.autopost_tasks)} задач...")
        for task in self.autopost_tasks.values():
            task.cancel()


# ================= MAIN =================
async def main():
    bot = BotHandler()

    def _sig(signum, _frame):
        logger.info(f"🛑 Сигнал {signum}")
        shutdown_event.set()
        bot.shutdown()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    try:
        await bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        async def _tests():
            ok = failed = 0
            def check(name, got, exp):
                nonlocal ok, failed
                if got == exp:
                    print(f"  ✅ {name}")
                    ok += 1
                else:
                    print(f"  ❌ {name}\n     ожидалось: {exp!r}\n     получено:  {got!r}")
                    failed += 1
            print("\n🧪 ТЕСТЫ parse_callback_data")
            check("publish с :", parse_callback_data("publish:-100123:abc456"), ("publish", "-100123", "abc456"))
            check("edit с :", parse_callback_data("edit:abc456"), ("edit", "", "abc456"))
            check("reject с :", parse_callback_data("reject:abc456"), ("reject", "", "abc456"))
            check("publish с _", parse_callback_data("publish_-100123_abc456"), ("publish", "-100123", "abc456"))
            check("edit с _", parse_callback_data("edit_abc456"), ("edit", "", "abc456"))
            check("reject с _", parse_callback_data("reject_abc456"), ("reject", "", "abc456"))
            check("пустой", parse_callback_data(""), ("", "", ""))
            check("мусор", parse_callback_data("bad"), ("", "", ""))
            print(f"\n✅ {ok} пройдено | ❌ {failed} провалено")
            return failed == 0
        sys.exit(0 if asyncio.run(_tests()) else 1)
    else:
        asyncio.run(main())
