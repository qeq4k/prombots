#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📝 Draft Manager — Управление черновиками постов
✅ Сохранение черновиков перед публикацией
✅ Проверка на дубликаты среди черновиков
✅ Автоматическая очистка старых черновиков
✅ Атомарная запись
"""
import os
import json
import hashlib
import logging
import aiofiles
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from global_dedup import normalize_text_for_dedup, texts_are_similar

logger = logging.getLogger(__name__)

DRAFTS_DIR = Path("pending_posts")
DRAFTS_DIR.mkdir(exist_ok=True)

MAX_DRAFT_AGE_HOURS = 24  # Максимальный возраст черновика
MAX_DRAFTS_PER_CATEGORY = 50  # Максимум черновиков на категорию


def get_draft_id(text: str, link: str) -> str:
    """Генерирует уникальный ID для черновика"""
    raw = f"{text[:100]}|{link}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get_draft_path(draft_id: str) -> Path:
    """Возвращает путь к файлу черновика"""
    return DRAFTS_DIR / f"{draft_id}.json"


async def save_draft(
    text: str,
    link: str,
    channel_id: str,
    suggestion_chat_id: str,
    category: str,
    photo: str = ""
) -> Tuple[str, bool]:
    """
    ✅ Сохраняет черновик и возвращает (draft_id, is_duplicate).
    Если черновик уже существует — возвращает его ID.
    """
    # Проверяем на дубликаты среди активных черновиков
    existing = await find_similar_draft(text, category, hours=2)
    if existing:
        logger.info(f"🔄 Черновик уже существует: {existing['post_id']}")
        return existing['post_id'], True
    
    draft_id = get_draft_id(text, link)
    draft_path = get_draft_path(draft_id)
    
    # Если файл уже существует — возвращаем его
    if draft_path.exists():
        logger.info(f"📁 Черновик уже сохранён: {draft_id}")
        return draft_id, True
    
    # Создаём черновик
    draft_data = {
        "text": text,
        "link": link,
        "channel_id": channel_id,
        "suggestion_chat_id": suggestion_chat_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "post_id": draft_id,
        "status": "pending",
        "photo": photo,
        "category": category
    }
    
    # Атомарная запись
    temp_path = draft_path.with_suffix(".tmp")
    try:
        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(draft_data, ensure_ascii=False, indent=2))
        os.replace(temp_path, draft_path)
        logger.info(f"📝 Черновик сохранён: {draft_id}")
        
        # Очищаем старые черновики
        await cleanup_old_drafts()
        
        return draft_id, False
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения черновика: {e}")
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


async def load_draft(draft_id: str) -> Optional[Dict]:
    """Загружает черновик по ID"""
    draft_path = get_draft_path(draft_id)
    if not draft_path.exists():
        return None
    
    try:
        async with aiofiles.open(draft_path, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        return data
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки черновика {draft_id}: {e}")
        return None


async def delete_draft(draft_id: str) -> bool:
    """Удаляет черновик"""
    draft_path = get_draft_path(draft_id)
    if draft_path.exists():
        draft_path.unlink()
        logger.info(f"🗑️ Черновик удалён: {draft_id}")
        return True
    return False


async def mark_draft_published(draft_id: str) -> bool:
    """Отмечает черновик как опубликованный"""
    draft = await load_draft(draft_id)
    if not draft:
        return False
    
    draft['status'] = 'published'
    draft['published_at'] = datetime.now(timezone.utc).isoformat()
    
    draft_path = get_draft_path(draft_id)
    temp_path = draft_path.with_suffix(".tmp")
    
    try:
        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(draft, ensure_ascii=False, indent=2))
        os.replace(temp_path, draft_path)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления черновика: {e}")
        return False


async def find_similar_draft(text: str, category: str, hours: int = 2) -> Optional[Dict]:
    """
    ✅ Ищет похожие черновики в категории.
    Возвращает черновик если найден похожий.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    for draft_file in DRAFTS_DIR.glob("*.json"):
        try:
            async with aiofiles.open(draft_file, 'r', encoding='utf-8') as f:
                data = json.loads(await f.read())
            
            # Проверяем категорию
            if data.get('category', '') != category:
                continue
            
            # Проверяем возраст
            created = datetime.fromisoformat(data['created_at'])
            if created < cutoff:
                continue
            
            # Проверяем статус
            if data.get('status') == 'published':
                continue
            
            # Сравниваем текст
            draft_text = data.get('text', '')
            if texts_are_similar(text, draft_text, threshold=0.75):
                logger.info(f"🔄 Найден похожий черновик: {data['post_id']}")
                return data
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки черновика {draft_file.name}: {e}")
            continue
    
    return None


async def cleanup_old_drafts() -> int:
    """
    🧹 Удаляет старые черновики.
    Возвращает количество удалённых.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_DRAFT_AGE_HOURS)
    deleted = 0
    
    for draft_file in DRAFTS_DIR.glob("*.json"):
        try:
            async with aiofiles.open(draft_file, 'r', encoding='utf-8') as f:
                data = json.loads(await f.read())
            
            created = datetime.fromisoformat(data['created_at'])
            
            # Удаляем если старше максимума
            if created < cutoff:
                draft_file.unlink()
                deleted += 1
                logger.debug(f"🧹 Удалён старый черновик: {draft_file.name}")
                continue
            
            # Удаляем опубликованные (они уже в БД)
            if data.get('status') == 'published':
                draft_file.unlink()
                deleted += 1
                logger.debug(f"🧹 Удалён опубликованный черновик: {draft_file.name}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки черновика {draft_file.name}: {e}")
            continue
    
    # Проверяем лимит на категорию
    await enforce_draft_limits()
    
    logger.info(f"🧹 Удалено старых черновиков: {deleted}")
    return deleted


async def enforce_draft_limits():
    """Ограничивает количество черновиков на категорию"""
    category_counts: Dict[str, List[Tuple[Path, datetime]]] = {}
    
    for draft_file in DRAFTS_DIR.glob("*.json"):
        try:
            async with aiofiles.open(draft_file, 'r', encoding='utf-8') as f:
                data = json.loads(await f.read())
            
            category = data.get('category', 'unknown')
            created = datetime.fromisoformat(data['created_at'])
            
            if category not in category_counts:
                category_counts[category] = []
            category_counts[category].append((draft_file, created))
        except:
            continue
    
    # Если больше лимита — удаляем самые старые
    for category, drafts in category_counts.items():
        if len(drafts) > MAX_DRAFTS_PER_CATEGORY:
            drafts.sort(key=lambda x: x[1])  # Сортируем по времени
            for draft_file, _ in drafts[:-MAX_DRAFTS_PER_CATEGORY]:
                draft_file.unlink()
                logger.info(f"🧹 Удалён черновик сверх лимита: {draft_file.name}")


async def get_draft_stats() -> Dict:
    """Возвращает статистику по черновикам"""
    stats = {
        'total': 0,
        'pending': 0,
        'published': 0,
        'by_category': {}
    }
    
    for draft_file in DRAFTS_DIR.glob("*.json"):
        try:
            async with aiofiles.open(draft_file, 'r', encoding='utf-8') as f:
                data = json.loads(await f.read())
            
            stats['total'] += 1
            status = data.get('status', 'unknown')
            if status == 'pending':
                stats['pending'] += 1
            elif status == 'published':
                stats['published'] += 1
            
            category = data.get('category', 'unknown')
            if category not in stats['by_category']:
                stats['by_category'][category] = 0
            stats['by_category'][category] += 1
        except:
            continue
    
    return stats


async def init_draft_manager():
    """Инициализация менеджера черновиков"""
    await cleanup_old_drafts()
    stats = await get_draft_stats()
    logger.info(f"📋 Draft Manager инициализирован: {stats['total']} черновиков")
