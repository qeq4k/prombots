#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Crossposter — основной модуль кросс-постинга

Интеграция с bot_handler.py:
- Сканирует опубликованные посты в каналах
- Анализирует пригодность для кросс-постинга
- Отправляет на модерацию или публикует автоматически
"""
import logging
import asyncio
import aiohttp
import ssl
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

from crosspost.config import config
from crosspost.database import CrosspostDatabase
from crosspost.analyzer import CrosspostAnalyzer
from crosspost.publisher import CrosspostPublisher

logger = logging.getLogger(__name__)


class Crossposter:
    """Основной класс кросс-постинга"""
    
    def __init__(self):
        self.db = CrosspostDatabase(config.database_path)
        self.analyzer = CrosspostAnalyzer(
            api_key=config.router_api_key,
            base_url=config.llm_base_url
        )
        self.publisher = CrosspostPublisher(
            tg_token=config.tg_token,
            channel_ids=config.channel_ids
        )
        
        # HTTP сессия для получения постов из каналов
        self.http_session: Optional[aiohttp.ClientSession] = None
        self._ssl_context = ssl.create_default_context()
        
        # Кэш последних постов из каналов
        self.last_posts: Dict[str, List[Dict]] = {
            "politics": [],
            "economy": [],
            "cinema": [],
        }
        
        # Время последнего сканирования каналов
        self.last_scan_time: Dict[str, datetime] = {}
        
        # Счётчики для метрик
        self.stats = {
            "analyzed": 0,
            "crossposted": 0,
            "rejected": 0,
            "errors": 0,
        }
    
    async def start(self):
        """Запуск кросс-постера"""
        logger.info("🚀 Запуск crossposter...")
        
        # Подключаем БД
        await self.db.connect()
        
        # Запускаем анализатор
        await self.analyzer.start_session()
        
        # Запускаем publisher
        await self.publisher.start()
        
        # Создаём HTTP сессию
        connector = aiohttp.TCPConnector(ssl=self._ssl_context, limit=10)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        
        logger.info("✅ Crossposter запущен")
    
    async def stop(self):
        """Остановка кросс-постера"""
        logger.info("🛑 Остановка crossposter...")
        
        if self.http_session:
            await self.http_session.close()
        
        await self.publisher.stop()
        await self.analyzer.close_session()
        await self.db.close()
        
        logger.info("✅ Crossposter остановлен")
    
    async def scan_channel_posts(self, channel_key: str) -> List[Dict[str, Any]]:
        """
        Сканирование постов в канале через Telegram API
        
        Args:
            channel_key: politics/economy/cinema
        
        Returns:
            Список постов
        """
        channel_id = config.channel_ids.get(channel_key)
        if not channel_id:
            return []
        
        # Получаем последние сообщения через getUpdates или getChatHistory
        # Для этого нужен бот с правами админа в канале
        # Используем упрощённый вариант — читаем из логов или БД
        
        # В реальной реализации здесь будет вызов Telegram API
        # Для примера — заглушка
        
        logger.debug(f"📡 Сканирование канала {channel_key} ({channel_id})")
        
        # Здесь должен быть код получения постов из канала
        # Например, через бота который слушает все сообщения
        
        return []
    
    async def analyze_and_queue(self, post_text: str, source_channel: str,
                                 post_id: str = "") -> bool:
        """
        Анализ поста и добавление в очередь кросс-постинга
        
        Args:
            post_text: Текст поста
            source_channel: Исходный канал
            post_id: ID поста
        
        Returns:
            True если пост добавлен в очередь
        """
        if not post_text or len(post_text.strip()) < 50:
            return False
        
        # Анализируем пост
        result = await self.analyzer.analyze_post(post_text, source_channel)
        self.stats["analyzed"] += 1
        
        logger.info(f"📊 Анализ поста из {source_channel}: "
                   f"can_crosspost={result.can_crosspost}, "
                   f"targets={result.target_channels}, "
                   f"score={result.interest_score}")
        
        if not result.can_crosspost:
            self.stats["rejected"] += 1
            logger.debug(f"⏭️ Пост отклонён: {result.reason}")
            return False
        
        # Добавляем в очередь для каждого целевого канала
        added = False
        for target_channel in result.target_channels:
            # Проверяем лимиты
            if not await self._check_limits(target_channel):
                logger.debug(f"⏭️ Лимит для {target_channel} исчерпан")
                continue
            
            # Адаптируем текст
            adapted_text = await self.analyzer.adapt_text(
                post_text, source_channel, target_channel
            )
            
            # Добавляем подпись целевого канала
            signature = config.signatures.get(target_channel, "")
            if signature and signature not in adapted_text:
                adapted_text += f"\n\n{signature}"
            
            # Сохраняем в БД
            success = await self.db.add_crosspost(
                source_channel=source_channel,
                target_channel=target_channel,
                source_post_id=post_id or hashlib.sha256(post_text[:100].encode()).hexdigest(),
                source_post_text=post_text,
                adapted_text=adapted_text,
                interest_score=result.interest_score
            )
            
            if success:
                added = True
                logger.info(f"✅ Добавлен кросс-пост: {source_channel} → {target_channel}")
        
        return added
    
    async def _check_limits(self, target_channel: str) -> bool:
        """Проверка лимитов кросс-постинга"""
        # Количество за сегодня
        count_today = await self.db.get_crossposts_count_today(target_channel)
        if count_today >= config.max_per_day_per_channel:
            return False
        
        # Время последнего поста
        last_time = await self.db.get_last_crosspost_time(target_channel)
        if last_time:
            elapsed = datetime.now(timezone.utc) - last_time
            if elapsed < timedelta(minutes=config.min_interval_minutes):
                return False
        
        return True
    
    async def process_queue(self):
        """Обработка очереди кросс-постов"""
        pending = await self.db.get_pending_crossposts(limit=10)
        
        for crosspost in pending:
            try:
                # Проверяем лимиты ещё раз
                if not await self._check_limits(crosspost["target_channel"]):
                    logger.debug(f"⏭️ Пропуск {crosspost['id']}: лимиты")
                    continue
                
                # Проверяем на дубликат
                if await self.db.is_crosspost_duplicate(
                    crosspost["adapted_text"],
                    crosspost["target_channel"]
                ):
                    logger.debug(f"⏭️ Дубликат {crosspost['id']}")
                    await self.db.update_crosspost_status(
                        crosspost["id"], "duplicate"
                    )
                    continue
                
                # Публикуем или отправляем на модерацию
                if config.auto_publish:
                    success, result = await self.publisher.publish(
                        text=crosspost["adapted_text"],
                        channel_key=crosspost["target_channel"]
                    )
                    
                    if success:
                        await self.db.update_crosspost_status(
                            crosspost["id"], "published"
                        )
                        await self.db.mark_crosspost_published(
                            crosspost["id"],
                            crosspost["target_channel"],
                            crosspost["adapted_text"],
                            crosspost["source_channel"]
                        )
                        self.stats["crossposted"] += 1
                        logger.info(f"✅ Опубликован кросс-пост {crosspost['id']}")
                    else:
                        await self.db.update_crosspost_status(
                            crosspost["id"], "failed",
                        )
                        self.stats["errors"] += 1
                        logger.warning(f"⚠️ Ошибка публикации {crosspost['id']}: {result}")
                else:
                    # Отправка на модерацию
                    suggestion_chat = config.suggestion_chats.get(
                        crosspost["target_channel"]
                    )
                    
                    if suggestion_chat:
                        success, result = await self.publisher.send_to_moderation(
                            text=crosspost["adapted_text"],
                            source_channel=crosspost["source_channel"],
                            target_channel=crosspost["target_channel"],
                            interest_score=crosspost["interest_score"],
                            suggestion_chat_id=suggestion_chat
                        )
                        
                        if success:
                            await self.db.update_crosspost_status(
                                crosspost["id"], "moderation"
                            )
                            logger.info(f"✅ Отправлен на модерацию {crosspost['id']}")
                        else:
                            await self.db.update_crosspost_status(
                                crosspost["id"], "failed"
                            )
                            self.stats["errors"] += 1
                            
            except Exception as e:
                logger.error(f"❌ Ошибка обработки кросс-поста {crosspost['id']}: {e}")
                self.stats["errors"] += 1
    
    async def cleanup_worker(self):
        """Периодическая очистка старых данных"""
        while True:
            try:
                await asyncio.sleep(3600)  # Раз в час
                await self.db.cleanup_old_crossposts(days=30)
                logger.info("🧹 Очистка старых кросс-постов выполнена")
            except Exception as e:
                logger.error(f"❌ Ошибка очистки: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        db_stats = await self.db.get_stats()
        return {
            **self.stats,
            **db_stats,
        }


# Глобальный экземпляр
crossposter = Crossposter()
