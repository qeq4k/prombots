#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Digest Generator — Генерация дайджестов за сутки

Использование в основных ботах:
    from shared import DigestGenerator
    
    digest = DigestGenerator(llm_client, telegram_client, config)
    await digest.generate_and_send(category="politics")
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import aiosqlite
import aiohttp

logger = logging.getLogger(__name__)


class DigestGenerator:
    """Генератор дайджестов за сутки"""
    
    def __init__(self, llm_client, telegram_client, config):
        """
        Args:
            llm_client: LLM клиент для генерации текста
            telegram_client: Telegram клиент для отправки
            config: Конфигурация бота
        """
        self.llm = llm_client
        self.telegram = telegram_client
        self.config = config
        self.db_path = getattr(config, 'database_path', 'politika.db')
    
    async def get_todays_posts(self, category: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получение постов за сегодня из БД
        
        Args:
            category: politics/economy/cinema
            limit: Максимум постов
        
        Returns:
            Список постов
        """
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = today.timestamp()
        
        posts = []
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT title, summary, link, pub_date, source, priority, posted_at
                    FROM posts 
                    WHERE posted_at > ? AND category = ?
                    ORDER BY priority DESC, posted_at DESC
                    LIMIT ?
                """, (today_ts, category, limit)) as cursor:
                    async for row in cursor:
                        posts.append({
                            "title": row["title"],
                            "summary": row["summary"],
                            "link": row["link"],
                            "pub_date": row["pub_date"],
                            "source": row["source"],
                            "priority": row["priority"],
                            "posted_at": row["posted_at"]
                        })
        except Exception as e:
            logger.error(f"❌ Ошибка чтения БД: {e}")
        
        return posts
    
    async def select_top_posts(self, posts: List[Dict], top_n: int = 5) -> List[Dict]:
        """
        Выбор топ-N постов за сутки
        
        Args:
            posts: Все посты за сегодня
            top_n: Количество топ-постов
        
        Returns:
            Топ посты
        """
        if not posts:
            return []
        
        # Сортируем по приоритету и времени
        sorted_posts = sorted(posts, key=lambda x: (x.get("priority", 0), x.get("posted_at", 0)), reverse=True)
        
        # Берём топ-N
        return sorted_posts[:top_n]
    
    async def generate_digest_text(self, top_posts: List[Dict], category: str) -> str:
        """
        Генерация текста дайджеста через LLM
        
        Args:
            top_posts: Топ посты для дайджеста
            category: Категория канала
        
        Returns:
            Текст дайджеста
        """
        if not top_posts:
            return ""
        
        # Формируем контекст для LLM
        posts_context = ""
        for i, post in enumerate(top_posts, 1):
            posts_context += f"{i}. {post['title']}\n"
            posts_context += f"   {post['summary'][:200]}...\n"
            posts_context += f"   Источник: {post['source']}\n\n"
        
        category_names = {
            "politics": "политике",
            "economy": "экономике",
            "cinema": "кино",
        }
        
        category_name = category_names.get(category, "новостях")
        
        prompt = f"""
Создай дайджест главных новостей за сутки для Telegram-канала о {category_name}.

Топ новостей за сегодня:
{posts_context}

Требования к дайджесту:
1. Заголовок: "📊 <b>ДАЙДЖЕСТ ЗА {datetime.now().strftime('%d.%m.%Y')}</b>"
2. Вступление: 2-3 предложения о главном за день
3. Топ-5 новостей: кратко по каждой (2-3 предложения)
4. Используй эмодзи для каждого пункта (🏛️💰🎬🔥📈 и т.д.)
5. Форматирование: HTML (<b>жирный</b>, <i>курсив</i>)
6. Длина: 2000-3500 символов
7. Язык: русский
8. В конце: хештеги #дайджест #{category}

Важно:
- Сохрани факты и цифры из оригиналов
- Пиши живым языком, но без кликбейта
- Избегай повторов

Дайджест (ТОЛЬКО текст, без комментариев):
"""
        
        try:
            response = await self.llm.generate(prompt, max_tokens=2048)
            if response:
                # Чистим ответ
                text = response.strip()
                # Убираем возможные преамбулы
                for prefix in ["Вот дайджест:", "Дайджест:", "Текст:"]:
                    if text.startswith(prefix):
                        text = text[len(prefix):].strip()
                return text[:4096]  # Лимит Telegram
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка генерации дайджеста: {e}")
            return ""
    
    async def send_digest(self, text: str, channel_id: str) -> bool:
        """
        Отправка дайджеста в канал
        
        Args:
            text: Текст дайджеста
            channel_id: ID канала
        
        Returns:
            True если успешно
        """
        if not text or len(text.strip()) < 100:
            logger.warning("⚠️ Дайджест слишком короткий для отправки")
            return False
        
        try:
            # Отправляем как обычный текст (без ограничения 1024)
            msg_id = await self.telegram.send_message(
                channel_id,
                text,
                parse_mode="HTML"
            )
            
            if msg_id:
                logger.info(f"✅ Дайджест отправлен (msg_id={msg_id})")
                return True
            else:
                logger.warning("⚠️ Ошибка отправки дайджеста")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки дайджеста: {e}")
            return False
    
    async def is_digest_already_sent(self, category: str) -> bool:
        """
        Проверка: не был ли уже отправлен дайджест сегодня
        
        Args:
            category: Категория канала
        
        Returns:
            True если уже отправлен
        """
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = today.timestamp()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT COUNT(*) FROM posts 
                    WHERE posted_at > ? AND category = ? 
                    AND title LIKE '%ДАЙДЖЕСТ%'
                """, (today_ts, category)) as cursor:
                    result = await cursor.fetchone()
                    return result[0] > 0
        except Exception as e:
            logger.error(f"❌ Ошибка проверки дайджеста: {e}")
            return False
    
    async def generate_and_send(self, category: str, force: bool = False) -> bool:
        """
        Генерация и отправка дайджеста
        
        Args:
            category: politics/economy/cinema
            force: Игнорировать проверку "уже отправлен"
        
        Returns:
            True если успешно
        """
        logger.info(f"📊 Генерация дайджеста для {category}...")
        
        # Проверяем не был ли уже отправлен
        if not force:
            if await self.is_digest_already_sent(category):
                logger.info("ℹ️ Дайджест уже отправлен сегодня")
                return False
        
        # Получаем посты за сегодня
        posts = await self.get_todays_posts(category, limit=50)
        
        if len(posts) < 3:
            logger.info(f"ℹ️ Недостаточно постов для дайджеста ({len(posts)})")
            return False
        
        # Выбираем топ-5
        top_posts = await self.select_top_posts(posts, top_n=5)
        
        logger.info(f"📊 Топ-5 постов для дайджеста: {[p['title'][:40] for p in top_posts]}")
        
        # Генерируем текст
        digest_text = await self.generate_digest_text(top_posts, category)
        
        if not digest_text:
            logger.warning("⚠️ Не удалось сгенерировать текст дайджеста")
            return False
        
        # Отправляем в канал
        channel_id = getattr(self.config, f'tg_channel_{category}', None)
        
        if not channel_id:
            logger.error(f"❌ Канал для {category} не найден")
            return False
        
        success = await self.send_digest(digest_text, channel_id)
        
        if success:
            # Сохраняем запись о дайджесте
            await self._save_digest_record(category, digest_text)
            logger.info(f"✅ Дайджест для {category} успешно создан и отправлен")
        
        return success
    
    async def _save_digest_record(self, category: str, text: str):
        """Сохранение записи о дайджесте в БД"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO posts (title, summary, link, source, category, posted_at, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"📊 ДАЙДЖЕСТ ЗА {datetime.now().strftime('%d.%m.%Y')}",
                    text[:500],
                    "digest",
                    "auto",
                    category,
                    datetime.now(timezone.utc).timestamp(),
                    100  # Высокий приоритет
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения дайджеста: {e}")
    
    async def schedule_daily_digest(self, category: str, hour: int = 22):
        """
        Планировщик ежедневного дайджеста
        
        Args:
            category: politics/economy/cinema
            hour: Час отправки (по умолчанию 22:00)
        """
        logger.info(f"⏰ Запуск планировщика дайджестов для {category} на {hour}:00")
        
        while True:
            try:
                now = datetime.now(timezone.utc)
                
                # Вычисляем время до следующей отправки
                next_send = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                wait_seconds = (next_send - now).total_seconds()
                
                logger.info(f"⏰ Следующий дайджест через {wait_seconds/3600:.1f} ч")
                
                await asyncio.sleep(wait_seconds)
                
                # Генерируем и отправляем
                await self.generate_and_send(category)
                
            except asyncio.CancelledError:
                logger.info("🛑 Планировщик дайджестов остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка планировщика: {e}")
                await asyncio.sleep(3600)  # Ждём час при ошибке


# ========== Helper функции для быстрой интеграции ==========

async def create_digest_for_category(llm_client, telegram_client, config, category: str) -> bool:
    """
    Быстрая функция для создания дайджеста
    
    Использование:
        success = await create_digest_for_category(llm, tg, config, "politics")
    """
    digest = DigestGenerator(llm_client, telegram_client, config)
    return await digest.generate_and_send(category)


async def schedule_digest_for_category(llm_client, telegram_client, config, category: str, hour: int = 22):
    """
    Быстрая функция для запуска планировщика
    
    Использование:
        asyncio.create_task(schedule_digest_for_category(llm, tg, config, "politics", 22))
    """
    digest = DigestGenerator(llm_client, telegram_client, config)
    await digest.schedule_daily_digest(category, hour)


__all__ = [
    "DigestGenerator",
    "create_digest_for_category",
    "schedule_digest_for_category",
]
