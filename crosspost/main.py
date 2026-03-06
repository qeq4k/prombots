#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Crosspost Service — основной файл запуска

Интеграция с bot_handler.py:
- Webhook для получения постов из каналов
- Автоматический анализ и адаптация
- Отправка на модерацию

Запуск:
    python crosspost/main.py

Или через PM2 (рекомендуется):
    pm2 start ecosystem.config.js --name crosspost
"""
import logging
import asyncio
import signal
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crosspost.config import config
from crosspost.database import CrosspostDatabase
from crosspost.analyzer import CrosspostAnalyzer
from crosspost.publisher import CrosspostPublisher
from crosspost.crossposter import Crossposter
from crosspost.bot import CrosspostModerationBot

# Настраиваем логирование
logging.basicConfig(
    level=getattr(logging, config.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.log_file, encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Prometheus метрики
prom_metrics = None
try:
    from prometheus_metrics import PrometheusMetrics
    prom_metrics = PrometheusMetrics(bot_name='crosspost', port=config.prometheus_port)
    logger.info(f"✅ Prometheus метрики на порту {config.prometheus_port}")
except Exception as e:
    logger.warning(f"⚠️ Prometheus не запущен: {e}")


class CrosspostService:
    """Основной сервис кросс-постинга"""
    
    def __init__(self):
        self.crossposter = Crossposter()
        self.moderation_bot = CrosspostModerationBot()
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Webhook сервер отключён — используется только основной цикл
        self.webhook_server = None
    
    async def start(self):
        """Запуск сервиса"""
        logger.info("🚀 Запуск crosspost service...")
        
        # Запускаем кросс-постер
        await self.crossposter.start()
        
        # Запускаем moderation bot (только API, без polling)
        await self.moderation_bot.start()
        
        self.running = True
        
        # Информируем bot_handler о готовности
        logger.info("✅ Crosspost service запущен")
        
        # Отправляем алерт в bot_handler (опционально)
        await self._notify_bot_handler("started")
    
    async def stop(self):
        """Остановка сервиса"""
        logger.info("🛑 Остановка crosspost service...")
        self.running = False
        
        await self.crossposter.stop()
        await self.moderation_bot.stop()
        
        await self._notify_bot_handler("stopped")
        
        logger.info("✅ Crosspost service остановлен")
        self.shutdown_event.set()
    
    async def _notify_bot_handler(self, status: str):
        """Уведомление bot_handler о статусе"""
        # В реальной реализации — HTTP запрос или IPC
        logger.info(f"📡 Notification to bot_handler: {status}")
    
    async def main_loop(self):
        """Основной цикл обработки очереди"""
        logger.info("🔄 Запуск основного цикла...")
        
        while self.running:
            try:
                # Обработка очереди кросс-постов
                await self.crossposter.process_queue()
                
                # Обновление метрик
                if prom_metrics:
                    stats = await self.crossposter.get_stats()
                    # prom_metrics.inc_post(...)  # при публикации
                
                await asyncio.sleep(10)  # Пауза между проверками
                
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("🛑 Основной цикл остановлен")
    
    async def run(self):
        """Запуск всех задач"""
        # Запускаем только основной цикл
        main_task = asyncio.create_task(self.main_loop())
        
        # Ждём сигнала остановки
        await self.shutdown_event.wait()
        
        # Отменяем задачи
        main_task.cancel()
        
        try:
            await asyncio.gather(main_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass


# Глобальный сервис
service = CrosspostService()


def signal_handler(signum, frame):
    """Обработчик сигналов"""
    logger.info(f"📶 Получен сигнал {signum}")
    asyncio.create_task(service.stop())


async def main():
    """Точка входа"""
    logger.info("=" * 60)
    logger.info("🔄 CROSSPOST SERVICE 2026")
    logger.info("=" * 60)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await service.start()
        await service.run()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по Ctrl+C")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
