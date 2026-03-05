#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Prometheus Metrics Module for Telegram Bots
Универсальный модуль метрик для всех ботов

Использование:
    from prometheus_metrics import PrometheusMetrics

    # Политика бот
    prom_metrics = PrometheusMetrics(bot_name='politics', port=8000)

    # Экономика бот
    prom_metrics = PrometheusMetrics(bot_name='economy', port=8001)

    # Кино бот
    prom_metrics = PrometheusMetrics(bot_name='cinema', port=8002)

    # Срочные новости
    prom_metrics = PrometheusMetrics(bot_name='urgent', port=8005)
"""

import logging
import time
import atexit
from typing import Optional, List, Tuple

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server, CollectorRegistry, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None
    Gauge = None
    Histogram = None
    start_http_server = None
    REGISTRY = None

logger = logging.getLogger(__name__)


class PrometheusMetrics:
    """
    Универсальный класс метрик Prometheus для Telegram ботов

    Attributes:
        bot_name: Название бота ('politics', 'economy', 'cinema', 'urgent')
        port: Порт для метрик (8000, 8001, 8002, 8005)
        enabled: Флаг доступности Prometheus
    """

    # Отслеживаем запущенные сервера для graceful shutdown
    _active_servers: List[Tuple] = []
    _shutdown_registered = False

    def __init__(self, bot_name: str, port: int = 8000):
        """
        Инициализация метрик

        Args:
            bot_name: Название бота ('politics', 'economy', 'cinema', 'urgent')
            port: Порт для HTTP сервера метрик
        """
        self.bot_name = bot_name
        self.port = port
        self.enabled = PROMETHEUS_AVAILABLE
        self._http_server = None
        self._start_time = time.time() if PROMETHEUS_AVAILABLE else 0

        # Регистрируем shutdown только один раз
        if not PrometheusMetrics._shutdown_registered and PROMETHEUS_AVAILABLE:
            atexit.register(PrometheusMetrics.shutdown_all)
            PrometheusMetrics._shutdown_registered = True

        if not PROMETHEUS_AVAILABLE:
            logger.warning(f"⚠️ prometheus-client не установлен. Метрики отключены.")
            logger.warning(f"   Установите: pip install prometheus-client")
            return

        # Изолированный реестр для каждого бота
        self.registry = CollectorRegistry()

        # 📨 Метрика: Отправленные посты
        self.posts_sent = Counter(
            'bot_posts_sent_total',
            'Total posts sent to Telegram channels',
            ['channel', 'type', 'bot'],
            registry=self.registry
        )

        # 🔄 Метрика: Дубликаты
        self.duplicates = Counter(
            'bot_duplicates_total',
            'Duplicates blocked by type',
            ['type', 'bot'],
            registry=self.registry
        )

        # 🤖 Метрика: LLM вызовы
        self.llm_calls = Counter(
            'bot_llm_calls_total',
            'LLM API calls by operation',
            ['operation', 'bot'],
            registry=self.registry
        )

        # 💾 Метрика: LLM cache hits
        self.llm_cache = Counter(
            'bot_llm_cache_hits_total',
            'LLM cache hits',
            ['bot'],
            registry=self.registry
        )

        # ⚠️ Метрика: LLM ошибки
        self.llm_errors = Counter(
            'bot_llm_errors_total',
            'LLM API errors',
            ['bot'],
            registry=self.registry
        )

        # 📋 Метрика: Кандидаты в очереди
        self.candidates = Gauge(
            'bot_candidates_current',
            'Current candidates in queue',
            ['bot'],
            registry=self.registry
        )

        # ⏱️ Метрика: Время обработки поста
        self.proc_time = Histogram(
            'bot_post_proc_seconds',
            'Post processing time in seconds',
            ['bot'],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
            registry=self.registry
        )

        # 🚫 Метрика: Заблокированные фейковые даты
        self.fake_dates = Counter(
            'bot_fake_dates_total',
            'Posts blocked due to fake dates',
            ['bot'],
            registry=self.registry
        )

        # 🇬🇧 Метрика: Заблокированные посты с английским
        self.english_blocked = Counter(
            'bot_english_blocked_total',
            'Posts blocked due to English words',
            ['bot'],
            registry=self.registry
        )

        # 🎯 Метрика: Проскочившие дубликаты (опубликованные)
        self.slipped_duplicates = Counter(
            'bot_slipped_duplicates_total',
            'Duplicates that slipped through and were posted to channel',
            ['channel', 'bot'],
            registry=self.registry
        )

        # ❌ Метрика: Отклонённые посты
        self.posts_rejected = Counter(
            'bot_posts_rejected_total',
            'Posts rejected by reason',
            ['reason', 'bot'],
            registry=self.registry
        )

        # ⏱️ Метрика: Время работы бота (uptime)
        self.uptime = Gauge(
            'bot_uptime_seconds',
            'Bot uptime in seconds',
            ['bot'],
            registry=self.registry
        )

        # Запускаем HTTP сервер для метрик
        try:
            self._http_server = start_http_server(port, registry=self.registry)
            PrometheusMetrics._active_servers.append((self._http_server, port, self.registry))
            logger.info(f"📊 Prometheus метрики запущены на порту http://localhost:{port}/metrics (bot={bot_name})")
        except OSError as e:
            if "Address already in use" in str(e):
                logger.warning(f"⚠️ Порт {port} уже используется — метрики отключены (возможно запущен другой экземпляр)")
                self.enabled = False
                self._http_server = None
            else:
                raise

        # Инициализируем uptime
        self.uptime.labels(bot=self.bot_name).set(0)

    # ========== Методы для инкремента метрик ==========

    def inc_post(self, channel: str, post_type: str):
        """
        Инкремент счётчика отправленных постов

        Args:
            channel: Название канала (e.g., 'economy', 'politics')
            post_type: Тип отправки ('autopost', 'suggestion', 'hot_news')
        """
        if self.enabled:
            self.posts_sent.labels(
                channel=channel,
                type=post_type,
                bot=self.bot_name
            ).inc()
            self._update_uptime()

    def inc_dup(self, dup_type: str):
        """
        Инкремент счётчика дубликатов

        Args:
            dup_type: Тип дубликата ('exact', 'fuzzy', 'global', 'content', 'entity', 'urgent')
        """
        if self.enabled:
            self.duplicates.labels(
                type=dup_type,
                bot=self.bot_name
            ).inc()
            self._update_uptime()

    def inc_llm(self, operation: str):
        """
        Инкремент счётчика LLM вызовов

        Args:
            operation: Тип операции ('classify', 'rewrite', 'summarize', 'translate')
        """
        if self.enabled:
            self.llm_calls.labels(
                operation=operation,
                bot=self.bot_name
            ).inc()
            self._update_uptime()

    def inc_cache(self):
        """Инкремент счётчика попаданий в LLM кэш"""
        if self.enabled:
            self.llm_cache.labels(bot=self.bot_name).inc()
            self._update_uptime()

    def inc_err(self):
        """Инкремент счётчика ошибок LLM"""
        if self.enabled:
            self.llm_errors.labels(bot=self.bot_name).inc()
            self._update_uptime()

    def inc_date(self):
        """Инкремент счётчика заблокированных фейковых дат"""
        if self.enabled:
            self.fake_dates.labels(bot=self.bot_name).inc()
            self._update_uptime()

    def inc_eng(self):
        """Инкремент счётчика заблокированных постов с английским"""
        if self.enabled:
            self.english_blocked.labels(bot=self.bot_name).inc()
            self._update_uptime()

    def inc_slipped_dup(self, channel: str):
        """
        Инкремент счётчика проскочивших дубликатов (опубликованных)

        Args:
            channel: Название канала (e.g., 'cinema', 'economy', 'politics')
        """
        if self.enabled:
            self.slipped_duplicates.labels(
                channel=channel,
                bot=self.bot_name
            ).inc()
            self._update_uptime()

    def inc_rejected(self, reason: str):
        """
        Инкремент счётчика отклонённых постов

        Args:
            reason: Причина отклонения:
                - 'low_priority' — LLM отклонил (не тематика)
                - 'not_economy' — не экономика (ключевые слова)
                - 'not_politics' — не политика (ключевые слова)
                - 'not_cinema' — не кино (ключевые слова)
                - 'not_fresh' — слишком старая новость
                - 'digest' — дайджест/сводка
                - 'no_video' — видео-новость без видео
                - 'duplicate' — дубликат
                - 'blacklist' — чёрный список
                - 'fake_date' — выдуманная дата
                - 'english' — много английского
                - 'manual_reject' — отклонено вручную через бота
                - 'short_text' — слишком короткий текст
                - 'error' — ошибка публикации
        """
        if self.enabled:
            self.posts_rejected.labels(
                reason=reason,
                bot=self.bot_name
            ).inc()
            self._update_uptime()

    def set_candidates(self, count: int):
        """
        Установка текущего количества кандидатов в очереди

        Args:
            count: Количество кандидатов
        """
        if self.enabled:
            self.candidates.labels(bot=self.bot_name).set(count)
            self._update_uptime()

    def observe_proc_time(self, duration: float):
        """
        Наблюдение времени обработки поста

        Args:
            duration: Время обработки в секундах
        """
        if self.enabled:
            self.proc_time.labels(bot=self.bot_name).observe(duration)
            self._update_uptime()

    def _update_uptime(self):
        """Обновление метрики uptime"""
        if self.enabled and self._start_time > 0:
            uptime = time.time() - self._start_time
            self.uptime.labels(bot=self.bot_name).set(uptime)

    # ========== Утилитные методы ==========

    def get_metrics_dict(self) -> Optional[dict]:
        """
        Получение текущих метрик в виде словаря

        Returns:
            Словарь с метриками или None если Prometheus недоступен
        """
        if not self.enabled:
            return None

        return {
            'bot_name': self.bot_name,
            'uptime_seconds': time.time() - self._start_time if self._start_time > 0 else 0,
            'posts_sent': self._get_counter_value(self.posts_sent),
            'posts_rejected': self._get_counter_value(self.posts_rejected),
            'duplicates': self._get_counter_value(self.duplicates),
            'llm_calls': self._get_counter_value(self.llm_calls),
            'llm_cache_hits': self._get_counter_value(self.llm_cache),
            'llm_errors': self._get_counter_value(self.llm_errors),
            'candidates': self._get_gauge_value(self.candidates),
            'fake_dates': self._get_counter_value(self.fake_dates),
            'english_blocked': self._get_counter_value(self.english_blocked),
            'slipped_duplicates': self._get_counter_value(self.slipped_duplicates),
        }

    def _get_counter_value(self, counter: Counter) -> int:
        """Получение значения Counter для текущего бота"""
        try:
            # Для Counter с labels нужно указывать все labels
            if 'bot' in counter._labelnames:
                return int(counter.labels(bot=self.bot_name)._value.get())
            return int(counter._value.get())
        except Exception:
            return 0

    def _get_gauge_value(self, gauge: Gauge) -> float:
        """Получение значения Gauge для текущего бота"""
        try:
            if 'bot' in gauge._labelnames:
                return float(gauge.labels(bot=self.bot_name)._value.get())
            return float(gauge._value.get())
        except Exception:
            return 0.0

    def disable(self):
        """Отключить метрики"""
        self.enabled = False
        logger.info(f"📊 Метрики отключены для бота {self.bot_name}")

    def enable(self):
        """Включить метрики"""
        if PROMETHEUS_AVAILABLE:
            self.enabled = True
            self._start_time = time.time()
            logger.info(f"📊 Метрики включены для бота {self.bot_name}")
        else:
            logger.warning(f"⚠️ prometheus-client не установлен")

    @staticmethod
    def shutdown_all():
        """
        Graceful shutdown для всех Prometheus метрик.
        Вызывается автоматически при выходе из программы (atexit).
        """
        logger.info("🛑 Graceful shutdown Prometheus метрик...")
        for server, port, registry in PrometheusMetrics._active_servers:
            try:
                logger.info(f"   📊 Остановка сервера на порту {port}")
                # prometheus_client не имеет явного stop(), но при выходе процесс закроется
            except Exception as e:
                logger.warning(f"⚠️ Ошибка shutdown порта {port}: {e}")
        PrometheusMetrics._active_servers.clear()
        logger.info("✅ Prometheus метрики остановлены")

    def shutdown(self):
        """
        Graceful shutdown для конкретного бота.
        """
        logger.info(f"🛑 Graceful shutdown метрик для {self.bot_name}...")
        self.enabled = False
        
        # Финальное обновление uptime
        self._update_uptime()
        
        # Удаляем из списка активных серверов
        PrometheusMetrics._active_servers = [
            (s, p, r) for s, p, r in PrometheusMetrics._active_servers 
            if p != self.port
        ]
        logger.info(f"✅ Метрики {self.bot_name} остановлены")


# ========== Глобальный экземпляр для импорта ==========
# Пример использования:
# from prometheus_metrics import prom_metrics
# prom_metrics = PrometheusMetrics(bot_name='economy', port=8001)

__all__ = ['PrometheusMetrics', 'PROMETHEUS_AVAILABLE']
