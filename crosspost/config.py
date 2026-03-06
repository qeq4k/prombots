#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Crosspost Config — конфигурация сервиса кросс-постинга
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class CrosspostConfig:
    """Конфигурация кросс-постинга"""
    
    # Telegram
    tg_token: str = field(default_factory=lambda: os.getenv("TG_TOKEN", ""))
    
    # Каналы
    tg_channel_politics: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_POLITICS", "-1003739906790"))
    tg_channel_economy: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_ECONOMY", "-1003701005081"))
    tg_channel_cinema: str = field(default_factory=lambda: os.getenv("TG_CHANNEL_CINEMA", "-1003635948209"))
    
    # Предложки для кросс-постов
    suggestion_chat_id_politics: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_POLITICS", "-1003659350130"))
    suggestion_chat_id_economy: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_ECONOMY", "-1003711339547"))
    suggestion_chat_id_cinema: str = field(default_factory=lambda: os.getenv("SUGGESTION_CHAT_ID_CINEMA", "-1003892651191"))
    
    # LLM
    router_api_key: str = field(default_factory=lambda: os.getenv("ROUTER_API_KEY", ""))
    llm_base_url: str = "https://routerai.ru/v1"
    llm_model_analyze: str = "openai/gpt-oss-20b"  # Для анализа
    llm_model_adapt: str = "openai/gpt-oss-20b"   # Для адаптации текста
    
    # Настройки анализа
    analyze_delay_seconds: int = 60  # Задержка перед анализом (даём посту устояться)
    max_post_age_hours: int = 24     # Не анализируем посты старше 24 часов
    
    # Настройки публикации
    auto_publish: bool = True       # Если True — публиковать без модерации
    min_interest_score: int = 60     # Минимальный интерес (0-100) для кросс-поста
    
    # Интервалы между кросс-постами (минуты)
    min_interval_minutes: int = 30   # Минимум между кросс-постами в один канал
    max_per_day_per_channel: int = 10  # Макс кросс-постов в день в один канал
    
    # Директории
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    crosspost_dir: Path = field(default_factory=lambda: Path("crosspost_posts"))
    database_path: str = "crosspost.db"
    
    # Логирование
    log_level: str = "INFO"
    log_file: str = "crosspost.log"
    
    # Prometheus
    prometheus_port: int = 8006
    
    def __post_init__(self):
        self.crosspost_dir.mkdir(exist_ok=True)
        
        # Маппинг каналов
        self.channel_ids = {
            "politics": self.tg_channel_politics,
            "economy": self.tg_channel_economy,
            "cinema": self.tg_channel_cinema,
        }
        
        self.suggestion_chats = {
            "politics": self.suggestion_chat_id_politics,
            "economy": self.suggestion_chat_id_economy,
            "cinema": self.suggestion_chat_id_cinema,
        }
        
        # Каналы в которые можно постить из каждого канала
        self.crosspost_targets = {
            "politics": ["economy", "cinema"],    # Из политики можно в экономику и кино
            "economy": ["politics", "cinema"],    # Из экономики в политику и кино
            "cinema": ["politics", "economy"],    # Из кино в политику и экономику
        }
        
        # Названия каналов
        self.channel_names = {
            "politics": "🏛️ Политика",
            "economy": "💰 Экономика",
            "cinema": "🎬 Кино",
        }
        
        # Подписи
        self.signatures = {
            "politics": os.getenv("SIGNATURE_POLITICS", "@I_Politika"),
            "economy": os.getenv("SIGNATURE_ECONOMY", "@eco_steroid"),
            "cinema": os.getenv("SIGNATURE_CINEMA", "@Film_orbita"),
        }


# Глобальный экземпляр
config = CrosspostConfig()
