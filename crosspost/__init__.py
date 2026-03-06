#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Crosspost Package — сервис кросс-постинга для Telegram каналов

Модули:
- config: Конфигурация
- database: SQLite для хранения истории
- analyzer: LLM анализ постов
- publisher: Публикация в каналы
- crossposter: Основная логика
- bot: Бот для модерации
- main: Точка входа
"""

__version__ = "1.0.0"
__author__ = "Crosspost Team"

__all__ = [
    "config",
    "database",
    "analyzer",
    "publisher",
    "crossposter",
    "bot",
    "main",
]
