#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Bot Handler — ASYNC 2026
✅ Защита от ошибки 409 (Conflict)
✅ Только один экземпляр бота
✅ Блокировка через PID файл
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
import re
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple
import random
import aiohttp
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ============ БЛОКИРОВКА ЭКЗЕМПЛЯРА ============
PID_FILE = Path("bot_handler.pid")

def check_single_instance() -> bool:
    """✅ Проверяет, запущен ли уже бот. Возвращает True если можно запускаться."""
    if PID_FILE.exists():
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # Проверяем, жив ли процесс
            os.kill(old_pid, 0)
            logger.error(f"❌ bot_handler уже запущен (PID={old_pid})")
            return False
        except (ProcessLookupError, PermissionError):
            # Процесс мёртв, удаляем PID файл
            logger.warning(f"🧹 Найден stale PID файл (PID={old_pid}), удаляю")
            PID_FILE.unlink(missing_ok=True)
        except (ValueError, IOError) as e:
            logger.warning(f"⚠️ Ошибка чтения PID файла: {e}")
            PID_FILE.unlink(missing_ok=True)
    
    # Записываем текущий PID
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    logger.info(f"🔒 Lock acquired (PID={os.getpid()})")
    return True

def release_instance_lock():
    """✅ Освобождает блокировку"""
    try:
        PID_FILE.unlink(missing_ok=True)
        logger.info("🔓 Lock released")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка удаления PID файла: {e}")

# ============ ГЛОБАЛЬНАЯ ДЕДУПЛИКАЦИЯ — ОБЯЗАТЕЛЬНА ============
# ✅ ПРОВЕРКА НА СТАРТЕ: аварийная остановка если global_dedup отсутствует
try:
    from global_dedup import (
        init_global_db,
        is_global_duplicate,
        mark_global_posted,
        cleanup_global_db
    )
    GLOBAL_DEDUP_ENABLED = True
    logger.info("✅ global_dedup.py загружен")
except ImportError:
    logger.error("❌ КРИТИЧЕСКОЕ: global_dedup.py не найден!")
    logger.error("❌ Без глобальной дедупликации работа бота невозможна")
    logger.error("❌ Аварийная остановка — добавьте global_dedup.py")
    import sys
    sys.exit(1)

# ============ PROMETHEUS ============
prom_metrics = None
try:
    from prometheus_metrics import PrometheusMetrics
    prom_metrics = PrometheusMetrics(bot_name='handler', port=8003)
    logger.info("✅ Prometheus метрики запущены на порту 8003")
except Exception as e:
    logger.warning(f"⚠️ Prometheus metrics error: {e}")
    prom_metrics = None

# ============ CROSSPOST INTEGRATION ============
crossposter_service = None
CROSSPOST_ENABLED = True
try:
    from crosspost.crossposter import crossposter as crossposter_service
    logger.info("✅ Crosspost сервис загружен")
except ImportError as e:
    logger.warning(f"⚠️ Crosspost сервис не загружен: {e}")
    CROSSPOST_ENABLED = False
    crossposter_service = None

load_dotenv()

# ============ ИМПОРТ ИЗ SHARED PACKAGE ============
from shared import (
    BotConfig,
    EditSession,
    Draft,
    TelegramClient,
    AlertManager,
    write_draft_atomic,
    read_draft,
    delete_draft,
    strip_html_tags,
    normalize_text_for_dedup,
    format_text_for_channel,
    load_all_edit_sessions,
)

config = BotConfig()


def parse_callback_data(data: str) -> Tuple[str, str, str]:
    """Парсит callback_data в формате action:channel:post или action_channel_post"""
    data = (data or "").strip()
    if not data:
        return "", "", ""

    # Формат с двоеточием: publish:channel:post / edit:post / reject:post
    if ":" in data:
        parts = data.split(":")
        action = parts[0]
        if action == "publish" and len(parts) >= 3:
            post_id = parts[-1]
            channel_id = ":".join(parts[1:-1])
            return action, channel_id, post_id
        if action in ("edit", "reject") and len(parts) >= 2:
            return action, "", parts[1]
        return "", "", ""

    # Формат с подчёркиванием: publish_channel_post / edit_post / reject_post
    parts = data.split("_")
    action = parts[0]
    if action == "publish" and len(parts) >= 3:
        post_id = parts[-1]
        channel_id = "_".join(parts[1:-1])
        return action, channel_id, post_id
    if action in ("edit", "reject") and len(parts) >= 2:
        return action, "", parts[1]

    return "", "", ""


# ============ БОТ ХЕНДЛЕР ============
shutdown_event = asyncio.Event()

class BotHandler:
    def __init__(self):
        self.telegram: Optional[TelegramClient] = None
        self.alert_manager: Optional[AlertManager] = None
        self.edit_sessions: Dict[int, EditSession] = {}
        self.sessions_dir = Path("edit_sessions")
        self.sessions_dir.mkdir(exist_ok=True)
        self.published_hashes: Dict[str, Tuple[str, datetime]] = {}
        self.published_hashes_ttl = timedelta(hours=2)
        self.published_hashes_file = Path("published_hashes.json")
        self.last_post_times: Dict[str, datetime] = {}
        self._processed_drafts: set = set()
        self._draft_lock: asyncio.Lock = asyncio.Lock()
        # ✅ ВОССТАНОВЛЕНИЕ СЕССИЙ ПРИ СТАРТЕ
        self._restore_edit_sessions()

    def _restore_edit_sessions(self):
        """✅ Восстанавливает сессии редактирования из файлов при старте"""
        if not self.sessions_dir.exists():
            return

        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                chat_id = int(session_file.stem)
                session = EditSession(
                    post_id=data.get("post_id", ""),
                    channel_id=data.get("channel_id", ""),
                    text=data.get("text", ""),
                    photo=data.get("photo", ""),
                    original_file=Path(data["original_file"]) if data.get("original_file") else None,
                    request_msg_id=data.get("request_msg_id")
                )
                self.edit_sessions[chat_id] = session
                logger.info(f"📦 Восстановлена сессия редактирования: chat_id={chat_id}, post_id={session.post_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить сессию {session_file}: {e}")

    def _get_category(self, channel_id: str) -> str:
        if channel_id == config.tg_channel_politics:
            return "politics"
        elif channel_id == config.tg_channel_economy:
            return "economy"
        elif channel_id == config.tg_channel_cinema:
            return "cinema"
        return ""
    
    def _get_channel_key(self, channel_id: str) -> str:
        """✅ Возвращает ключ канала (politics/economy/cinema) для crosspost"""
        return self._get_category(channel_id)

    def _get_content_hash(self, text: str, channel_id: str) -> str:
        normalized = normalize_text_for_dedup(text)
        return hashlib.sha256(f"{normalized[:300]}|{channel_id}".encode("utf-8", errors="ignore")).hexdigest()

    def _cleanup_published_cache(self):
        cutoff = datetime.now(timezone.utc) - self.published_hashes_ttl
        self.published_hashes = {k: v for k, v in self.published_hashes.items() if v[1] > cutoff}

    def _save_published_hashes(self):
        try:
            self._cleanup_published_cache()
            data = {k: {"channel_id": v[0], "timestamp": v[1].isoformat()} for k, v in self.published_hashes.items()}
            with open(self.published_hashes_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить published_hashes: {e}")

    def _load_published_hashes(self):
        try:
            if self.published_hashes_file.exists():
                with open(self.published_hashes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cutoff = datetime.now(timezone.utc) - self.published_hashes_ttl
                self.published_hashes = {
                    k: (v["channel_id"], datetime.fromisoformat(v["timestamp"]))
                    for k, v in data.items()
                    if datetime.fromisoformat(v["timestamp"]) > cutoff
                }
                logger.info(f"📦 Загружено {len(self.published_hashes)} published хешей")
        except Exception as e:
            self.published_hashes = {}

    async def _is_duplicate(self, text: str, channel_id: str) -> bool:
        h = self._get_content_hash(text, channel_id)
        if h in self.published_hashes:
            _, ts = self.published_hashes[h]
            if datetime.now(timezone.utc) - ts < self.published_hashes_ttl:
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
        self.published_hashes[h] = (channel_id, datetime.now(timezone.utc))
        if GLOBAL_DEDUP_ENABLED:
            try:
                category = self._get_category(channel_id)
                await mark_global_posted(h, channel_id, "bot_handler", text.split('\n')[0][:100], category)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка отметки БД: {e}")
        if len(self.published_hashes) % 50 == 0:
            self._save_published_hashes()

    def _mark_post_time(self, channel_id: str):
        self.last_post_times[channel_id] = datetime.now(timezone.utc)

    async def publish_post(self, text: str, channel_id: str, photo: str = "") -> Tuple[bool, str]:
        if not text or len(text) < 10:
            if prom_metrics:
                prom_metrics.inc_rejected('short_text')
            return False, "Текст слишком короткий"

        # ✅ ПРОВЕРКА ИНТЕРВАЛА ОТКЛЮЧЕНА — публикация без задержек
        # can_post, wait_min = self._can_post_now(channel_id)
        # if not can_post:
        #     logger.warning(f"⏳ Пропуск поста: нужно ждать ещё {wait_min:.1f} мин для {channel_id}")
        #     return False, f"Интервал: ждать {wait_min:.0f} мин"

        if await self._is_duplicate(text, channel_id):
            logger.warning(f"🎯 ПРОСКочивший дубликат обнаружен в {channel_id}")
            if prom_metrics:
                prom_metrics.inc_slipped_dup(channel_id)
            return False, "Дубликат"

        try:
            formatted = format_text_for_channel(text)
            # ✅ ПРОВЕРКА: отправляем фото только если это валидный URL или file_id
            if photo and photo not in ("no", "None", "null", ""):
                success, result = await self.telegram.send_photo(channel_id, photo, formatted)
            else:
                msg_id = await self.telegram.send_message(channel_id, formatted)
                success, result = bool(msg_id), ("Опубликовано" if msg_id else "Ошибка отправки")

            if success:
                self._mark_post_time(channel_id)
                await self._mark_published(text, channel_id)
                if prom_metrics:
                    prom_metrics.inc_post(channel_id, 'suggestion')
            return success, result
        except Exception as e:
            logger.error(f"❌ Ошибка публикации: {e}")
            if prom_metrics:
                prom_metrics.inc_rejected('error')
            return False, str(e)[:100]

    async def autopost_draft(self, draft_path: Path, post_id: str):
        # ✅ БЛОКИРОВКА - только один поток обрабатывает черновик
        async with self._draft_lock:
            # Проверка: не обрабатывали ли уже
            if post_id in self._processed_drafts:
                logger.debug(f"⏭️ Черновик {post_id} уже обработан")
                return
            
            try:
                draft = await read_draft(draft_path)
                if not draft:
                    await delete_draft(draft_path)
                    self._processed_drafts.add(post_id)
                    return

                # Игнорируем filmtop черновики
                source = draft.to_dict().get("source", "")
                if ("Filmtop TikTok" in source) or ("filmtop" in source.lower()) or \
                   draft.post_id.startswith(("top_", "hidden_", "horror_", "asian_", "trending_")):
                    logger.debug(f"⏭️ Пропущен черновик filmtop: {draft.post_id}")
                    self._processed_drafts.add(post_id)
                    return

                if draft.suggestion_chat_id not in config.autopost_allowed_suggestions:
                    return

                # Проверка возраста
                draft_age_minutes = (datetime.now(timezone.utc) - datetime.fromtimestamp(draft_path.stat().st_mtime, tz=timezone.utc)).total_seconds() / 60
                max_age = config.autopost_night_max_minutes * 2
                if draft_age_minutes > max_age:
                    logger.warning(f"🗑️ Пропущен старый черновик {post_id} (возраст {draft_age_minutes:.0f} мин)")
                    await delete_draft(draft_path)
                    self._processed_drafts.add(post_id)
                    return

                # ✅ ПРОВЕРКА ИНТЕРВАЛА ОТКЛЮЧЕНА
                # can_post, wait_min = self._can_post_now(draft.channel_id)
                # if not can_post:
                #     logger.debug(f"⏳ Автопост {post_id} отложен: ждать {wait_min:.1f} мин")
                #     return

                logger.debug(f"🌙 Автопост {post_id} → {draft.channel_id}")
                success, result = await self.publish_post(draft.text, draft.channel_id, draft.photo)

                if success:
                    await delete_draft(draft_path)
                    self._processed_drafts.add(post_id)
                    logger.info(f"✅ Автопост опубликован: {post_id}")
                    
                    # ✅ CROSSPOST: Отправляем на анализ для кросс-постинга
                    if CROSSPOST_ENABLED and crossposter_service:
                        try:
                            await crossposter_service.analyze_and_queue(
                                post_text=draft.text,
                                source_channel=self._get_channel_key(draft.channel_id),
                                post_id=post_id
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ Crosspost анализ ошибки: {e}")
                elif result == "Дубликат":
                    logger.debug(f"🗑️ Дубликат удалён: {post_id}")
                    await delete_draft(draft_path)
                    self._processed_drafts.add(post_id)
                else:
                    logger.warning(f"⚠️ Автопост не удался {post_id}: {result}")
            except Exception as e:
                logger.exception(f"❌ Ошибка автопоста {post_id}: {e}")

    async def autopost_worker(self):
        if not config.autopost_enabled:
            logger.info("🌙 Автопостинг отключён")
            return
        logger.info(f"🌙 Автопостинг запущен | День: {config.autopost_day_min_minutes}-{config.autopost_day_max_minutes} мин")
        
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(config.autopost_check_interval)
                if shutdown_event.is_set():
                    break
                
                now = datetime.now(timezone.utc).timestamp()
                delay_min = config.get_autopost_delay_minutes()
                
                for draft_path in list(config.pending_dir.glob("*.json")):
                    if shutdown_event.is_set():
                        break
                    post_id = draft_path.stem
                    draft = await read_draft(draft_path)
                    if not draft:
                        await delete_draft(draft_path)
                        continue
                    if draft.suggestion_chat_id not in config.autopost_allowed_suggestions:
                        continue
                    age_min = (now - draft_path.stat().st_mtime) / 60
                    if age_min >= delay_min * 0.95:
                        await self.autopost_draft(draft_path, post_id)
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
                self._save_published_hashes()
                threshold = datetime.now(timezone.utc) - timedelta(hours=config.cleanup_age_hours)
                deleted = 0
                for fp in config.pending_dir.glob("*.json"):
                    try:
                        if datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc) < threshold:
                            fp.unlink(missing_ok=True)
                            deleted += 1
                    except:
                        pass
                if deleted:
                    logger.info(f"🧹 Удалено старых файлов: {deleted}")
                if GLOBAL_DEDUP_ENABLED:
                    try:
                        n = await cleanup_global_db(days=30)
                        if n:
                            logger.info(f"🧹 Глобальная БД: удалено {n} записей")
                    except:
                        pass
            except Exception as e:
                logger.exception(f"⚠️ cleanup_worker: {e}")
                await asyncio.sleep(3600)
        logger.info("🧹 cleanup_worker завершён")

    async def handle_callback(self, callback_query: dict):
        """🔘 Обработка нажатий кнопок (publish/edit/reject)"""
        query_id = callback_query.get("id")
        message = callback_query.get("message", {})
        data = callback_query.get("data", "")
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        
        logger.debug(f"🔘 Callback: {data} от {chat_id}")
        
        try:
            # Отвечаем на callback (чтобы убрать loading state)
            await self.telegram.answer_callback_query(query_id)
            
            # Парсим callback_data
            action, channel_id, post_id = parse_callback_data(data)
            
            if not action or not post_id:
                logger.error(f"❌ Некорректные callback данные: '{data}'")
                await self.telegram.send_message(chat_id, f"❌ Некорректные данные кнопки")
                return
            
            draft_path = config.pending_dir / f"{post_id}.json"
            
            if action == "publish":
                logger.info(f"✅ Публикация: {post_id} → {channel_id}")
                await self.handle_publish_button(chat_id, channel_id, post_id, draft_path)
            elif action == "edit":
                logger.info(f"✏️ Редактирование: {post_id}")
                await self.handle_edit_button(chat_id, post_id, draft_path, message_id)
            elif action == "reject":
                logger.info(f"❌ Отклонение: {post_id}")
                await self.handle_reject_button(chat_id, post_id, draft_path)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки callback {data}: {e}", exc_info=True)

    async def handle_publish_button(self, chat_id: int, channel_id: str, post_id: str, draft_path: Path):
        """✅ Публикация поста из предложки"""
        if not draft_path.exists():
            await self.telegram.send_message(chat_id, f"❌ Черновик <code>{post_id}</code> не найден")
            return

        draft = await read_draft(draft_path)
        if not draft:
            return

        if not channel_id or channel_id in ("undefined", ""):
            channel_id = draft.channel_id

        success, result = await self.publish_post(draft.text, channel_id, draft.photo)

        await self.telegram.send_message(
            chat_id,
            f"{'✅' if success else '❌'} {result}\nПост: <code>{post_id}</code>\nКанал: <code>{channel_id}</code>"
        )

        if success:
            await delete_draft(draft_path)
            logger.info(f"✅ Опубликован {post_id} → {channel_id}")
            
            # ✅ CROSSPOST: Отправляем на анализ
            if CROSSPOST_ENABLED and crossposter_service:
                try:
                    channel_key = self._get_channel_key(channel_id)
                    await crossposter_service.analyze_and_queue(
                        post_text=draft.text,
                        source_channel=channel_key,
                        post_id=post_id
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Crosspost анализ ошибки: {e}")

    async def handle_edit_button(self, chat_id: int, post_id: str, draft_path: Path, msg_id: Optional[int]):
        """✏️ Редактирование поста"""
        if not draft_path.exists():
            await self.telegram.send_message(chat_id, "❌ Черновик не найден")
            return
        
        draft = await read_draft(draft_path)
        if not draft:
            return
        
        # Удаляем сообщение с кнопками
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
            post_id=post_id,
            channel_id=draft.channel_id,
            text=draft.text,
            photo=draft.photo,
            original_file=draft_path,
            request_msg_id=new_msg_id
        )
        
        logger.info(f"✏️ {post_id} → редактирование")

    async def handle_reject_button(self, chat_id: int, post_id: str, draft_path: Path):
        """❌ Отклонение поста"""
        if draft_path.exists():
            draft = await read_draft(draft_path)
            await delete_draft(draft_path)
            if prom_metrics:
                prom_metrics.inc_rejected('manual_reject')
            await self.telegram.send_message(chat_id, f"✅ Черновик <code>{post_id}</code> отклонён")
            logger.info(f"❌ {post_id} отклонён")
        else:
            await self.telegram.send_message(chat_id, f"⚠️ Черновик <code>{post_id}</code> не найден")

    async def handle_message(self, update: dict):
        """📝 Обработка сообщений (команды /publish, /reject и текст для редактирования)"""
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        
        if not chat_id:
            return
        
        # Проверяем, есть ли активная сессия редактирования
        session = self.edit_sessions.get(chat_id)
        
        if text.lower() == "/publish":
            if session:
                # Публикуем из сессии
                if not session.text or len(session.text) < 10:
                    await self.telegram.send_message(chat_id, "❌ Текст слишком короткий")
                    return
                
                success, result = await self.publish_post(session.text, session.channel_id, session.photo)
                
                await self.telegram.send_message(
                    chat_id,
                    f"{'✅' if success else '❌'} {result}\nПост: <code>{session.post_id}</code>\nКанал: <code>{session.channel_id}</code>"
                )
                
                if success and session.original_file and session.original_file.exists():
                    await delete_draft(session.original_file)
                
                # Удаляем сессию
                (self.sessions_dir / f"{chat_id}.json").unlink(missing_ok=True)
                self.edit_sessions.pop(chat_id, None)
                
                logger.info(f"✅ /publish {session.post_id} → {session.channel_id}")
            else:
                await self.telegram.send_message(chat_id, "❌ Нет активной сессии редактирования")
            return
        
        if text.lower() == "/reject":
            if session:
                # Отклоняем сессию
                if session.original_file and session.original_file.exists():
                    await delete_draft(session.original_file)

                (self.sessions_dir / f"{chat_id}.json").unlink(missing_ok=True)
                self.edit_sessions.pop(chat_id, None)

                if prom_metrics:
                    prom_metrics.inc_rejected('manual_reject')

                await self.telegram.send_message(chat_id, f"✅ Черновик <code>{session.post_id}</code> отклонён")
                logger.info(f"❌ /reject {session.post_id}")
            else:
                await self.telegram.send_message(chat_id, "❌ Нет активной сессии редактирования")
            return
        
        # Если есть сессия и это не команда — сохраняем текст
        if session and not (text and text.lower().startswith("/")):
            session.text = text
            
            # Сохраняем сессию
            try:
                session_data = {
                    "post_id": session.post_id,
                    "channel_id": session.channel_id,
                    "text": session.text,
                    "photo": session.photo,
                    "original_file": str(session.original_file) if session.original_file else None,
                    "request_msg_id": session.request_msg_id
                }
                async with aiofiles.open(self.sessions_dir / f"{chat_id}.json", 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(session_data, ensure_ascii=False, indent=2))
            except Exception as e:
                logger.error(f"❌ Сохранение сессии {chat_id}: {e}")
            
            # Удаляем предыдущее сообщение
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
                    
                    # 🔘 Обработка callback_query
                    if "callback_query" in update:
                        await self.handle_callback(update["callback_query"])
                    
                    # 📝 Обработка сообщений
                    elif "message" in update:
                        chat_type = update["message"]["chat"].get("type", "")
                        if chat_type in ("supergroup", "group", "channel", "private"):
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
            
            self._load_published_hashes()
            logger.info(f"📦 Индекс pending: {config.pending_dir.exists()}")

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
        logger.info(f"🛑 Завершение, отмена {len(self._processed_drafts)} задач...")
        self._save_published_hashes()
        logger.info("💾 published_hashes сохранён")

# ============ MAIN ============
async def main():
    # ✅ ПРОВЕРКА НА ЗАПУЩЕННОСТЬ
    if not check_single_instance():
        logger.error("❌ bot_handler уже запущен — выход")
        return
    
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
    finally:
        release_instance_lock()

if __name__ == "__main__":
    asyncio.run(main())
