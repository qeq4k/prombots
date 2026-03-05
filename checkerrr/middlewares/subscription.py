"""
Middleware для проверки подписки
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, User

from config import Config
from database import Database
from cache import SubscriptionCache
from keyboards import get_channels_keyboard
from texts import get_text

# Относительный импорт для избежания конфликта с системным types.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_types import SubscriptionResult

logger = logging.getLogger(__name__)


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для проверки подписки пользователя"""

    def __init__(
        self,
        db: Database,
        config: Config,
        admin_ids: list[int],
        bot
    ):
        self.db = db
        self.config = config
        self.admin_ids = admin_ids
        self.bot = bot
        self._last_check_time: Dict[int, datetime] = {}
        self._check_cooldown = timedelta(seconds=5)
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем user_id из разных типов событий
        user_id = self._get_user_id(event)

        if user_id is None:
            return await handler(event, data)

        # Админы пропускают проверку
        if user_id in self.admin_ids:
            logger.debug(f"User {user_id} is admin, skipping subscription check")
            return await handler(event, data)

        # Проверяем подписку
        result = await self._check_subscription(user_id)
        logger.debug(f"Subscription check for user {user_id}: is_subscribed={result.is_subscribed}, failed_channels={result.failed_channels}")

        # Если не подписан и это не команда /start или /help
        if not result.is_subscribed:
            if self._is_allowed_event(event):
                logger.debug(f"Event allowed for user {user_id} without subscription")
                return await handler(event, data)

            # Блокируем и показываем сообщение о необходимости подписки
            logger.warning(f"User {user_id} is not subscribed, blocking access")
            lang = self.db.get_user_language(user_id)
            await self._show_subscription_required(event, result, lang)
            return

        return await handler(event, data)
    
    def _get_user_id(self, event: Message | CallbackQuery) -> int | None:
        """Извлекаем user_id из события"""
        if hasattr(event, 'from_user'):
            return event.from_user.id
        elif hasattr(event, 'message') and hasattr(event.message, 'from_user'):
            return event.message.from_user.id
        elif hasattr(event, 'callback_query') and hasattr(event.callback_query, 'from_user'):
            return event.callback_query.from_user.id
        return None
    
    def _is_allowed_event(self, event: Message | CallbackQuery) -> bool:
        """Проверяем, разрешено ли событие без подписки"""
        # Разрешаем определенные команды
        if isinstance(event, Message) and event.text:
            text = event.text.strip()
            allowed_commands = ['/start', '/help', '/language', '/lang', '/support']
            if text in allowed_commands:
                return True
        
        # Разрешаем определенные callback query
        if isinstance(event, CallbackQuery) and event.data:
            allowed_callbacks = ['check_subscription', 'cancel_to_main', 'back_to_menu', 'back_to_main']
            if any(event.data.startswith(prefix) for prefix in allowed_callbacks):
                return True
        
        return False
    
    async def _check_subscription(self, user_id: int, force_check: bool = False) -> SubscriptionResult:
        """Проверка подписки с кэшированием"""
        cached = await SubscriptionCache.get(user_id)
        if cached and not force_check:
            logger.debug(f"Cache hit for user {user_id}: {cached}")
            return SubscriptionResult(
                is_subscribed=cached.get('is_subscribed', True),
                failed_channels=cached.get('failed_channels', []),
                checked_at=cached.get('checked_at', datetime.now())
            )

        # Проверка cooldown
        if not force_check:
            last_time = self._last_check_time.get(user_id)
            if last_time and (datetime.now() - last_time < self._check_cooldown):
                if cached:
                    return SubscriptionResult(
                        is_subscribed=cached.get('is_subscribed', True),
                        failed_channels=cached.get('failed_channels', []),
                        checked_at=cached.get('checked_at', datetime.now())
                    )

        # Получаем каналы
        channels_db = self.db.get_channels()
        logger.debug(f"Channels from DB for user {user_id}: {channels_db}")
        channels = [
            {"name": ch["name"], "link": ch["link"], "id": ch["chat_id"]}
            for ch in (channels_db or self.config.CHANNELS)
        ]
        logger.debug(f"Channels list for user {user_id}: {channels}")

        if not channels:
            logger.warning(f"No channels configured for user {user_id}, allowing access")
            result = SubscriptionResult(is_subscribed=True, failed_channels=[])
            await self._save_result(user_id, result)
            return result

        is_subscribed = True
        failed_channels = []

        for channel in channels:
            raw_id = str(channel['id']).strip()
            if not raw_id:
                logger.warning(f"Channel {channel['name']} has empty chat_id")
                continue

            try:
                chat_id = self._parse_chat_id(raw_id)
                logger.debug(f"Checking user {user_id} in channel {channel['name']} ({chat_id})")
                chat_member = await self.bot.get_chat_member(chat_id, user_id)
                status = chat_member.status
                logger.debug(f"User {user_id} status in {channel['name']}: {status}")

                if status not in ["member", "administrator", "creator"]:
                    is_subscribed = False
                    failed_channels.append(channel['name'])

            except Exception as e:
                logger.error(f"Ошибка проверки '{channel['name']}' для {user_id}: {e}")
                is_subscribed = False
                failed_channels.append(channel['name'])

        result = SubscriptionResult(is_subscribed=is_subscribed, failed_channels=failed_channels)
        logger.info(f"Subscription check result for user {user_id}: {result.is_subscribed}, failed: {result.failed_channels}")
        await self._save_result(user_id, result)
        return result
    
    def _parse_chat_id(self, raw_id: str) -> int | str:
        """Парсинг chat_id"""
        if raw_id.lstrip('-').isdigit():
            return int(raw_id)
        elif raw_id.startswith('@'):
            return raw_id
        else:
            return '@' + raw_id.lstrip('@')
    
    async def _save_result(self, user_id: int, result: SubscriptionResult) -> None:
        """Сохранение результата проверки"""
        await SubscriptionCache.set(
            user_id, 
            result.is_subscribed, 
            result.failed_channels, 
            self.config.SUBSCRIPTION_CACHE_TTL
        )
        
        self._last_check_time[user_id] = datetime.now()
        self.db.update_user_subscription(user_id, result.is_subscribed)
    
    async def _show_subscription_required(
        self,
        event: Message | CallbackQuery,
        result: SubscriptionResult,
        lang: str
    ) -> None:
        """Показ сообщения о необходимости подписки"""
        # Получаем полную информацию о каналах, на которые не подписан пользователь
        all_channels = self.db.get_channels() or self.config.CHANNELS
        failed_channels_data = [
            ch for ch in all_channels 
            if ch['name'] in result.failed_channels
        ]
        
        failed = "\n".join([f"• {ch['name']}" for ch in failed_channels_data])
        message_text = get_text("subscription_check_failed", lang, failed_channels=failed)
        keyboard = get_channels_keyboard(failed_channels_data, lang)

        if isinstance(event, Message):
            await event.answer(
                message_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        elif isinstance(event, CallbackQuery):
            await event.answer(message_text, show_alert=True)


class VisitsLoggingMiddleware(BaseMiddleware):
    """Middleware для логирования посещений пользователей"""
    
    def __init__(self, db: Database, admin_ids: list[int]):
        self.db = db
        self.admin_ids = admin_ids
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = self._get_user_id(event)
        
        if user_id is not None and user_id not in self.admin_ids:
            try:
                self.db.log_user_visit(user_id)
            except Exception as e:
                logger.error(f"Ошибка логирования посещения для {user_id}: {e}")
        
        return await handler(event, data)
    
    def _get_user_id(self, event: Message | CallbackQuery) -> int | None:
        """Извлекаем user_id из события"""
        if hasattr(event, 'from_user'):
            return event.from_user.id
        elif hasattr(event, 'message') and hasattr(event.message, 'from_user'):
            return event.message.from_user.id
        elif hasattr(event, 'callback_query') and hasattr(event.callback_query, 'from_user'):
            return event.callback_query.from_user.id
        return None
