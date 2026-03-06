#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 Crosspost Analyzer — LLM анализ постов для кросс-постинга
"""
import logging
import json
import aiohttp
import ssl
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Результат анализа поста"""
    can_crosspost: bool
    target_channels: List[str]
    interest_score: int  # 0-100
    reason: str
    adapted_titles: Dict[str, str]  # Заголовки для каждого канала


class CrosspostAnalyzer:
    """Анализ постов через LLM"""
    
    def __init__(self, api_key: str, base_url: str = "https://routerai.ru/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._ssl_context = ssl.create_default_context()
    
    async def start_session(self):
        """Создание HTTP сессии"""
        connector = aiohttp.TCPConnector(ssl=self._ssl_context, limit=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=60)
        )
        logger.info("✅ HTTP сессия анализатора создана")
    
    async def close_session(self):
        """Закрытие HTTP сессии"""
        if self.session:
            await self.session.close()
            logger.info("🔒 HTTP сессия анализатора закрыта")
    
    async def analyze_post(self, text: str, source_channel: str) -> AnalysisResult:
        """
        Анализ поста на пригодность для кросс-постинга
        
        Args:
            text: Текст поста
            source_channel: Исходный канал (politics/economy/cinema)
        
        Returns:
            AnalysisResult с результатами анализа
        """
        # Определяем целевые каналы
        target_map = {
            "politics": ["economy", "cinema"],
            "economy": ["politics", "cinema"],
            "cinema": ["politics", "economy"],
        }
        targets = target_map.get(source_channel, [])
        
        if not targets:
            return AnalysisResult(
                can_crosspost=False,
                target_channels=[],
                interest_score=0,
                reason="Нет целевых каналов",
                adapted_titles={}
            )
        
        prompt = f"""
Проанализируй пост из Telegram-канала и определи:

1. Можно ли адаптировать этот пост для других каналов?
2. Для каких каналов подходит (из: economy, politics, cinema)?
3. Оценка интереса для каждого канала (0-100)
4. Краткая причина решения

Исходный канал: {source_channel}
Целевые каналы: {', '.join(targets)}

Пост:
{text[:1500]}

Ответь ТОЛЬКО в формате JSON:
{{
    "can_crosspost": true/false,
    "targets": {{
        "economy": {{"score": 0-100, "reason": "причина"}},
        "politics": {{"score": 0-100, "reason": "причина"}},
        "cinema": {{"score": 0-100, "reason": "причина"}}
    }},
    "general_reason": "общая причина"
}}

Важно:
- Если пост чисто тематический (только политика/экономика/кино) — не подходит
- Если есть общие темы (культура, общество, технологии) — подходит
- Минимальный порог интереса: 50
"""
        
        try:
            response = await self._call_llm(prompt)
            
            if not response:
                return AnalysisResult(
                    can_crosspost=False,
                    target_channels=[],
                    interest_score=0,
                    reason="Ошибка LLM",
                    adapted_titles={}
                )
            
            # Парсим JSON ответ
            try:
                # Пытаемся найти JSON в ответе
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    result = json.loads(json_str)
                else:
                    result = json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Ошибка парсинга JSON: {e}")
                logger.debug(f"Ответ LLM: {response[:500]}")
                return AnalysisResult(
                    can_crosspost=False,
                    target_channels=[],
                    interest_score=0,
                    reason="Ошибка парсинга ответа LLM",
                    adapted_titles={}
                )
            
            # Обрабатываем результат
            can_crosspost = result.get("can_crosspost", False)
            targets_data = result.get("targets", {})
            general_reason = result.get("general_reason", "Нет причины")
            
            # Фильтруем каналы с достаточным интересом
            suitable_targets = []
            adapted_titles = {}
            max_score = 0
            
            for target in targets:
                if target in targets_data:
                    score = targets_data[target].get("score", 0)
                    if score >= 50:  # Порог интереса
                        suitable_targets.append(target)
                        if score > max_score:
                            max_score = score
            
            return AnalysisResult(
                can_crosspost=can_crosspost and len(suitable_targets) > 0,
                target_channels=suitable_targets,
                interest_score=max_score,
                reason=general_reason,
                adapted_titles=adapted_titles
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа поста: {e}", exc_info=True)
            return AnalysisResult(
                can_crosspost=False,
                target_channels=[],
                interest_score=0,
                reason=f"Ошибка: {str(e)[:100]}",
                adapted_titles={}
            )
    
    async def adapt_text(self, text: str, source_channel: str, 
                         target_channel: str) -> str:
        """
        Адаптация текста под стиль целевого канала
        
        Args:
            text: Исходный текст
            source_channel: Исходный канал
            target_channel: Целевой канал
        
        Returns:
            Адаптированный текст
        """
        styles = {
            "politics": "официально-деловой, с акцентом на политические аспекты",
            "economy": "аналитический, с акцентом на экономические последствия",
            "cinema": "развлекательный, с акцентом на зрелищность и эмоции",
        }
        
        target_style = styles.get(target_channel, "нейтральный")
        
        prompt = f"""
Адаптируй текст поста из одного Telegram-канала для другого.

Исходный канал: {source_channel}
Целевой канал: {target_channel}
Стиль целевого канала: {target_style}

Важно:
- Сохрани основную суть и факты
- Адаптируй тон и стиль под целевую аудиторию
- Убери специфичные для исходного канала отсылки
- Добавь уместные эмодзи для целевого канала
- Длина: примерно как оригинал (±20%)
- Язык: русский
- Форматирование: HTML (<b>жирный</b>, <i>курсив</i>)

Исходный текст:
{text[:1500]}

Адаптированный текст (ТОЛЬКО текст, без комментариев):
"""
        
        try:
            adapted = await self._call_llm(prompt)
            if adapted:
                # Чистим ответ от лишних комментариев
                adapted = adapted.strip()
                # Убираем возможные преамбулы
                for prefix in ["Вот адаптированный текст:", "Адаптированный текст:", "Текст:"]:
                    if adapted.startswith(prefix):
                        adapted = adapted[len(prefix):].strip()
                return adapted[:1024]  # Лимит Telegram
            return text  # Возвращаем оригинал если ошибка
        except Exception as e:
            logger.error(f"❌ Ошибка адаптации текста: {e}")
            return text
    
    async def _call_llm(self, prompt: str, model: str = "openai/gpt-oss-20b") -> Optional[str]:
        """Вызов LLM через API"""
        if not self.session:
            await self.start_session()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.7
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                ssl=self._ssl_context
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return content.strip()
                else:
                    error_text = await resp.text()
                    logger.error(f"❌ LLM API error {resp.status}: {error_text[:200]}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"❌ Ошибка запроса к LLM: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка LLM: {e}")
            return None
