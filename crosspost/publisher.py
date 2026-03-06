#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📤 Crosspost Publisher — Публикация кросс-постов в каналы
"""
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict
from pathlib import Path

# Импортируем из shared
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import TelegramClient, normalize_text_for_dedup, format_text_for_channel

logger = logging.getLogger(__name__)


class CrosspostPublisher:
    """Публикация кросс-постов"""
    
    def __init__(self, tg_token: str, channel_ids: Dict[str, str]):
        self.telegram = TelegramClient(token=tg_token)
        self.channel_ids = channel_ids
        self._session_active = False
        
        # Кэш опубликованных хешей (защита от дублей)
        self.published_hashes: Dict[str, Tuple[str, datetime]] = {}
        self.published_hashes_ttl = timedelta(hours=72)
    
    async def start(self):
        """Запуск сессии Telegram"""
        await self.telegram.__aenter__()
        self._session_active = True
        logger.info("✅ Сессия Telegram publisher запущена")
    
    async def stop(self):
        """Остановка сессии Telegram"""
        if self._session_active:
            await self.telegram.__aexit__(None, None, None)
            self._session_active = False
            logger.info("🔒 Сессия Telegram publisher закрыта")
    
    def _get_content_hash(self, text: str, channel_id: str) -> str:
        """Хеш контента для проверки дублей"""
        normalized = normalize_text_for_dedup(text)
        return hashlib.sha256(f"{normalized[:500]}|{channel_id}".encode()).hexdigest()
    
    def _cleanup_hashes(self):
        """Очистка старых хешей"""
        cutoff = datetime.now(timezone.utc) - self.published_hashes_ttl
        self.published_hashes = {
            k: v for k, v in self.published_hashes.items() 
            if v[1] > cutoff
        }
    
    async def is_duplicate(self, text: str, channel_id: str) -> bool:
        """Проверка на дубликат"""
        self._cleanup_hashes()
        h = self._get_content_hash(text, channel_id)
        
        if h in self.published_hashes:
            _, ts = self.published_hashes[h]
            if datetime.now(timezone.utc) - ts < self.published_hashes_ttl:
                logger.debug(f"⏭️ Дубликат в кэше: {h[:12]}")
                return True
        
        return False
    
    async def publish(self, text: str, channel_key: str, 
                      photo: Optional[str] = None) -> Tuple[bool, str]:
        """
        Публикация поста в канал
        
        Args:
            text: Текст поста
            channel_key: Ключ канала (politics/economy/cinema)
            photo: URL фото (опционально)
        
        Returns:
            (success, message)
        """
        channel_id = self.channel_ids.get(channel_key)
        
        if not channel_id:
            return False, f"Канал {channel_key} не найден"
        
        if not text or len(text.strip()) < 10:
            return False, "Текст слишком короткий"
        
        # Проверка на дубликат
        if await self.is_duplicate(text, channel_id):
            logger.warning(f"🎯 Дубликат обнаружен для {channel_key}")
            return False, "Дубликат"
        
        try:
            # Форматируем текст
            formatted = format_text_for_channel(text)
            
            # Отправляем
            if photo and photo not in ("no", "None", "null", ""):
                success, result = await self.telegram.send_photo(
                    channel_id, photo, formatted
                )
            else:
                msg_id = await self.telegram.send_message(channel_id, formatted)
                success, result = bool(msg_id), "Опубликовано" if msg_id else "Ошибка отправки"
            
            if success:
                # Сохраняем хеш
                h = self._get_content_hash(text, channel_id)
                self.published_hashes[h] = (channel_id, datetime.now(timezone.utc))
                logger.info(f"✅ Опубликовано в {channel_key} (msg_id={msg_id})")
            else:
                logger.warning(f"⚠️ Ошибка публикации в {channel_key}: {result}")
            
            return success, result
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации в {channel_key}: {e}", exc_info=True)
            return False, str(e)[:150]
    
    async def send_to_moderation(self, text: str, source_channel: str,
                                  target_channel: str, interest_score: int,
                                  suggestion_chat_id: str) -> Tuple[bool, str]:
        """
        Отправка кросс-поста на модерацию в предложку
        
        Args:
            text: Текст поста
            source_channel: Исходный канал
            target_channel: Целевой канал
            interest_score: Оценка интереса
            suggestion_chat_id: ID чата предложки
        
        Returns:
            (success, message)
        """
        # Формируем заголовок
        channel_names = {
            "politics": "🏛️ Политика",
            "economy": "💰 Экономика", 
            "cinema": "🎬 Кино",
        }
        
        source_name = channel_names.get(source_channel, source_channel)
        target_name = channel_names.get(target_channel, target_channel)
        
        header = f"🔄 <b>Кросс-пост из {source_name}</b>\n"
        header += f"🎯 Для: {target_name}\n"
        header += f"⭐ Интерес: {interest_score}/100\n\n"
        
        full_text = header + text[:1000]
        
        # Отправляем в предложку
        try:
            msg_id = await self.telegram.send_message(
                suggestion_chat_id, 
                full_text,
                parse_mode="HTML"
            )
            
            if msg_id:
                logger.info(f"✅ Отправлено на модерацию в {suggestion_chat_id}")
                return True, f"Отправлено в модерацию (msg_id={msg_id})"
            else:
                return False, "Ошибка отправки"
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки на модерацию: {e}")
            return False, str(e)[:150]
