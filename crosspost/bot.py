#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Crosspost Bot — Telegram бот для модерации кросс-постов

⚠️ ВНИМАНИЕ: Этот модуль НЕ используется в текущей версии.
Модерация кросс-постов интегрирована напрямую в bot_handler.py

Для включения модерации:
1. Добавь обработку callback в bot_handler.py
2. Используй CrosspostModerationBot как middleware
"""
import logging
from typing import Optional, Dict
from pathlib import Path

from crosspost.config import config
from crosspost.database import CrosspostDatabase
from crosspost.publisher import CrosspostPublisher

logger = logging.getLogger(__name__)


class CrosspostModerationBot:
    """
    Бот для модерации кросс-постов.
    
    ⚠️ ВНИМАНИЕ: В текущей версии работает в режиме "только API".
    Для полноценной модерации нужно интегрировать в bot_handler.py
    """
    
    def __init__(self):
        self.db = CrosspostDatabase(config.database_path)
        self._db_ready = False
    
    async def start(self):
        """Запуск бота"""
        logger.info("🚀 Запуск crosspost moderation bot (API mode)...")
        await self.db.connect()
        self._db_ready = True
        logger.info("✅ Crosspost moderation bot запущен (API mode)")
    
    async def stop(self):
        """Остановка бота"""
        logger.info("🛑 Остановка crosspost moderation bot...")
        if self._db_ready:
            await self.db.close()
        logger.info("✅ Crosspost moderation bot остановлен")
    
    def get_moderation_keyboard(self, crosspost_id: int) -> dict:
        """
        Клавиатура для модерации.
        Используется в bot_handler.py для отображения кнопок.
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ КП Опубликовать", "callback_data": f"cp_approve_{crosspost_id}"},
                    {"text": "❌ КП Отклонить", "callback_data": f"cp_reject_{crosspost_id}"}
                ]
            ]
        }
    
    async def get_stats(self) -> Dict:
        """Получение статистики"""
        if self._db_ready:
            return await self.db.get_stats()
        return {}
    
    async def approve_crosspost(self, crosspost_id: int, publisher) -> tuple[bool, str]:
        """
        Одобрение кросс-поста.
        
        Args:
            crosspost_id: ID кросс-поста в БД
            publisher: CrosspostPublisher экземпляр
        
        Returns:
            (success, message)
        """
        if not self._db_ready:
            return False, "БД не подключена"
        
        # Получаем кросс-пост
        pending = await self.db.get_pending_crossposts(limit=100)
        crosspost = next((cp for cp in pending if cp["id"] == crosspost_id), None)
        
        if not crosspost:
            return False, "Кросс-пост не найден"
        
        # Публикуем
        success, result = await publisher.publish(
            text=crosspost["adapted_text"],
            channel_key=crosspost["target_channel"]
        )
        
        if success:
            await self.db.update_crosspost_status(crosspost_id, "published")
            await self.db.mark_crosspost_published(
                crosspost_id,
                crosspost["target_channel"],
                crosspost["adapted_text"],
                crosspost["source_channel"]
            )
            logger.info(f"✅ Кросс-пост {crosspost_id} опубликован")
            return True, "Опубликовано"
        else:
            await self.db.update_crosspost_status(crosspost_id, "failed")
            logger.warning(f"⚠️ Ошибка публикации кросс-поста {crosspost_id}: {result}")
            return False, result
    
    async def reject_crosspost(self, crosspost_id: int) -> tuple[bool, str]:
        """
        Отклонение кросс-поста.
        
        Args:
            crosspost_id: ID кросс-поста в БД
        
        Returns:
            (success, message)
        """
        if not self._db_ready:
            return False, "БД не подключена"
        
        await self.db.update_crosspost_status(crosspost_id, "rejected")
        logger.info(f"❌ Кросс-пост {crosspost_id} отклонён")
        return True, "Отклонено"


# Глобальный экземпляр
moderation_bot = CrosspostModerationBot()
