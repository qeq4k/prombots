#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Crosspost Database — SQLite для хранения истории кросс-постов
"""
import aiosqlite
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class CrosspostDatabase:
    """База данных для кросс-постинга"""
    
    def __init__(self, db_path: str = "crosspost.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Подключение к БД и создание таблиц"""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"✅ БД кросс-постинга подключена: {self.db_path}")
    
    async def close(self):
        """Закрытие подключения"""
        if self._conn:
            await self._conn.close()
            logger.info("🔒 БД кросс-постинга закрыта")
    
    async def _create_tables(self):
        """Создание таблиц"""
        async with self._conn.execute("""
            CREATE TABLE IF NOT EXISTS crossposts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_channel TEXT NOT NULL,
                target_channel TEXT NOT NULL,
                source_post_id TEXT NOT NULL,
                source_post_text TEXT,
                adapted_text TEXT,
                interest_score INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMP,
                UNIQUE(source_post_id, target_channel)
            )
        """):
            pass
        
        async with self._conn.execute("""
            CREATE TABLE IF NOT EXISTS published_crossposts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_channel TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                text_preview TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_channel TEXT
            )
        """):
            pass
        
        async with self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_crossposts_status 
            ON crossposts(status)
        """):
            pass
        
        async with self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_crossposts_source 
            ON crossposts(source_channel, created_at)
        """):
            pass
        
        async with self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_crossposts_target 
            ON crossposts(target_channel, status)
        """):
            pass
        
        async with self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_published_channel 
            ON published_crossposts(target_channel, published_at)
        """):
            pass
        
        await self._conn.commit()
    
    async def add_crosspost(self, source_channel: str, target_channel: str, 
                           source_post_id: str, source_post_text: str,
                           adapted_text: str = "", interest_score: int = 0) -> bool:
        """Добавление кросс-поста в очередь"""
        try:
            await self._conn.execute("""
                INSERT OR IGNORE INTO crossposts 
                (source_channel, target_channel, source_post_id, source_post_text, 
                 adapted_text, interest_score, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (source_channel, target_channel, source_post_id, 
                  source_post_text[:2000], adapted_text[:2000], interest_score))
            await self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления кросс-поста: {e}")
            return False
    
    async def get_pending_crossposts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получениеpending кросс-постов"""
        async with self._conn.execute("""
            SELECT * FROM crossposts 
            WHERE status = 'pending' 
            ORDER BY created_at ASC 
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def update_crosspost_status(self, crosspost_id: int, status: str, 
                                      published_at: Optional[datetime] = None):
        """Обновление статуса кросс-поста"""
        if published_at is None:
            published_at = datetime.now(timezone.utc)
        
        await self._conn.execute("""
            UPDATE crossposts 
            SET status = ?, published_at = ?
            WHERE id = ?
        """, (status, published_at, crosspost_id))
        await self._conn.commit()
    
    async def mark_crosspost_published(self, crosspost_id: int, target_channel: str,
                                       text: str, source_channel: str):
        """Отметка опубликованного кросс-поста"""
        import hashlib
        text_hash = hashlib.sha256(text[:500].encode()).hexdigest()
        
        await self._conn.execute("""
            INSERT INTO published_crossposts 
            (target_channel, text_hash, text_preview, published_at, source_channel)
            VALUES (?, ?, ?, ?, ?)
        """, (target_channel, text_hash, text[:200], datetime.now(timezone.utc), source_channel))
        await self._conn.commit()
    
    async def is_crosspost_duplicate(self, text: str, target_channel: str, 
                                     hours: int = 72) -> bool:
        """Проверка: не был ли похожий кросс-пост уже опубликован"""
        import hashlib
        text_hash = hashlib.sha256(text[:500].encode()).hexdigest()
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        async with self._conn.execute("""
            SELECT COUNT(*) FROM published_crossposts 
            WHERE target_channel = ? AND text_hash = ? AND published_at > ?
        """, (target_channel, text_hash, cutoff)) as cursor:
            result = await cursor.fetchone()
            return result[0] > 0
    
    async def get_crossposts_count_today(self, target_channel: str) -> int:
        """Количество кросс-постов в канал за сегодня"""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        async with self._conn.execute("""
            SELECT COUNT(*) FROM crossposts 
            WHERE target_channel = ? AND status = 'published' AND created_at > ?
        """, (target_channel, today)) as cursor:
            result = await cursor.fetchone()
            return result[0]
    
    async def get_last_crosspost_time(self, target_channel: str) -> Optional[datetime]:
        """Время последнего кросс-поста в канал"""
        async with self._conn.execute("""
            SELECT published_at FROM crossposts 
            WHERE target_channel = ? AND status = 'published'
            ORDER BY published_at DESC 
            LIMIT 1
        """, (target_channel,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return datetime.fromisoformat(result[0])
            return None
    
    async def cleanup_old_crossposts(self, days: int = 30):
        """Очистка старых записей"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        await self._conn.execute("""
            DELETE FROM crossposts 
            WHERE status IN ('published', 'rejected') AND created_at < ?
        """, (cutoff,))
        
        await self._conn.execute("""
            DELETE FROM published_crossposts 
            WHERE published_at < ?
        """, (cutoff,))
        
        await self._conn.commit()
        logger.info(f"🧹 Удалены старые кросс-посты (> {days} дней)")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Статистика кросс-постинга"""
        stats = {}
        
        # Общее количество
        async with self._conn.execute("""
            SELECT status, COUNT(*) FROM crossposts GROUP BY status
        """) as cursor:
            rows = await cursor.fetchall()
            stats["by_status"] = {row[0]: row[1] for row in rows}
        
        # По каналам
        async with self._conn.execute("""
            SELECT target_channel, COUNT(*) FROM crossposts 
            WHERE status = 'published' 
            GROUP BY target_channel
        """) as cursor:
            rows = await cursor.fetchall()
            stats["by_channel"] = {row[0]: row[1] for row in rows}
        
        # За сегодня
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self._conn.execute("""
            SELECT COUNT(*) FROM crossposts 
            WHERE status = 'published' AND created_at > ?
        """, (today,)) as cursor:
            stats["today"] = (await cursor.fetchone())[0]
        
        return stats
