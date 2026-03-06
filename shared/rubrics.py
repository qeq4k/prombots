#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📑 Auto Rubrics — Авто-рубрикация постов

Использование:
    from shared import AutoRubrics
    
    rubrics = AutoRubrics(llm_client)
    rubric = await rubrics.get_rubric(title, text)
    # Результат: "#политика #внешняя_политика"
"""
import logging
import json
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class AutoRubrics:
    """Авто-рубрикация постов через LLM"""
    
    # Предопределённые рубрики по категориям
    RUBRICS = {
        "politics": [
            "#политика",
            "#внешняя_политика",
            "#внутренняя_политика",
            "#дипломатия",
            "#выборы",
            "#правительство",
            "#парламент",
            "#санкции",
            "#конфликты",
            "#безопасность",
        ],
        "economy": [
            "#экономика",
            "#финансы",
            "#бизнес",
            "#рынки",
            "#акции",
            "#валюты",
            "#нефть",
            "#газ",
            "#инфляция",
            "#ставки",
            "#криптовалюты",
        ],
        "cinema": [
            "#кино",
            "#премьеры",
            "#сериалы",
            "#актёры",
            "#режиссёры",
            "#блокбастеры",
            "#инди",
            "#ужасы",
            "#комедии",
            "#драмы",
        ],
    }
    
    def __init__(self, llm_client):
        """
        Args:
            llm_client: LLM клиент для классификации
        """
        self.llm = llm_client
        self._cache = {}  # Кэш рубрик
    
    async def get_rubric(self, title: str, text: str = "", category: str = "politics") -> str:
        """
        Получение рубрики для поста
        
        Args:
            title: Заголовок поста
            text: Текст поста (опционально)
            category: Категория (politics/economy/cinema)
        
        Returns:
            Строка с рубриками (например: "#политика #дипломатия")
        """
        # Проверяем кэш
        cache_key = f"{title[:50]}|{category}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Получаем доступные рубрики для категории
        available_rubrics = self.RUBRICS.get(category, self.RUBRICS["politics"])
        
        prompt = f"""
Классифицируй новость и выбери 1-2 подходящие рубрики из списка.

Заголовок: {title}
{"Текст: " + text[:300] if text else ""}

Доступные рубрики:
{", ".join(available_rubrics)}

Верни ТОЛЬКО 1-2 рубрики через пробел. Без комментариев.
Пример: #политика #дипломатия
"""
        
        try:
            response = await self.llm.generate(prompt, max_tokens=50)
            if response:
                # Парсим ответ
                rubrics = self._parse_rubrics(response.strip(), available_rubrics)
                if rubrics:
                    result = " ".join(rubrics[:2])  # Максимум 2 рубрики
                    self._cache[cache_key] = result
                    return result
        except Exception as e:
            logger.warning(f"⚠️ Ошибка авто-рубрикации: {e}")
        
        # Fallback: возвращаем общую рубрику категории
        fallback = available_rubrics[0]
        self._cache[cache_key] = fallback
        return fallback
    
    def _parse_rubrics(self, response: str, available: List[str]) -> List[str]:
        """Парсинг рубрик из ответа LLM"""
        # Нормализуем ответ
        response = response.lower().strip()
        
        # Убираем лишние символы
        response = response.replace(",", " ").replace(".", " ").replace(";", " ")
        
        # Разбиваем на слова
        words = response.split()
        
        # Ищем рубрики
        found = []
        for word in words:
            # Проверяем точное совпадение
            if word in available:
                found.append(word)
            # Проверяем с хешем
            elif word.startswith("#") and word[1:] in [r[1:] for r in available]:
                found.append(word)
            # Проверяем без хеша
            elif not word.startswith("#") and ("#" + word) in available:
                found.append("#" + word)
        
        # Если ничего не нашли — берём первую рубрику
        if not found:
            found = [available[0]]
        
        return found
    
    def get_rubric_for_post(self, post_data: dict) -> str:
        """
        Синхронная версия для использования в существующем коде
        
        Args:
            post_data: Данные поста (title, text, category)
        
        Returns:
            Строка с рубриками
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.get_rubric(
                post_data.get("title", ""),
                post_data.get("text", ""),
                post_data.get("category", "politics")
            )
        )


# ========== Helper для быстрой интеграции ==========

def add_rubric_to_text(text: str, rubric: str) -> str:
    """
    Добавление рубрики к тексту поста
    
    Args:
        text: Текст поста
        rubric: Рубрика (например: "#политика #дипломатия")
    
    Returns:
        Текст с добавленной рубрикой
    """
    if not rubric:
        return text
    
    # Разбиваем текст на строки
    lines = text.split('\n')
    
    # Находим первую пустую строку или конец
    insert_pos = 0
    for i, line in enumerate(lines):
        if line.strip() == "":
            insert_pos = i
            break
    else:
        insert_pos = len(lines)
    
    # Вставляем рубрику
    if insert_pos > 0:
        lines.insert(insert_pos, rubric)
    else:
        lines.insert(0, rubric)
        lines.insert(1, "")
    
    return '\n'.join(lines)


__all__ = ['AutoRubrics', 'add_rubric_to_text']
