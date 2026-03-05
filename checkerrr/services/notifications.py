"""
Сервис уведомлений
Улучшенная версия с rate limiting, обработкой ошибок и отслеживанием прогресса
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from database import Database
from app_types import MovieInfo

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис для отправки уведомлений пользователям"""

    # Rate limiting constants
    RATE_LIMIT_DELAY = 0.05  # 50ms между сообщениями (20 сообщений в секунду)
    BATCH_SIZE = 100  # Размер пакета для логирования прогресса
    MAX_RETRY_ATTEMPTS = 3  # Максимальное количество попыток при ошибке

    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self._last_notification_time: Dict[int, datetime] = {}  # Rate limiting per user

    async def notify_new_movie(
        self,
        movie: MovieInfo,
        exclude_admins: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        Уведомить всех пользователей о новом фильме

        Args:
            movie: Информация о фильме
            exclude_admins: Исключать ли админов из рассылки
            progress_callback: Callback для отслеживания прогресса (sent, total, user_id)

        Returns:
            Dict с результатами: {'sent': int, 'failed': int, 'blocked': int, 'errors': list}
        """
        users = self.db.get_all_users_with_notifications()
        
        result = {
            'sent': 0,
            'failed': 0,
            'blocked': 0,
            'errors': [],
            'total': len(users),
            'start_time': datetime.now()
        }

        from config import Config

        logger.info(f"🔔 Начало рассылки: всего пользователей={len(users)}, exclude_admins={exclude_admins}, фильм='{movie.title}'")

        message = (
            f"🎬 **Новый фильм в каталоге!**\n\n"
            f"🎥 {movie.title}\n"
            f"📅 Год: {movie.year or 'N/A'}\n"
            f"⭐ Рейтинг: {movie.rating or 'N/A'}\n"
            f"🎭 Жанры: {', '.join(movie.genres) if movie.genres else 'N/A'}\n\n"
            f"🔍 Код фильма: `{movie.code}`\n\n"
            f"Нажмите кнопку ниже чтобы посмотреть:"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🎬 Смотреть фильм",
                    callback_data=f"movie_{movie.code}"
                )
            ]]
        )

        for idx, user in enumerate(users, 1):
            user_id = user['user_id']

            # Пропускаем админов если нужно
            if exclude_admins and user_id in Config.ADMIN_IDS:
                logger.debug(f"  ⏭️ Пропущен админ: {user_id}")
                continue

            # Rate limiting между уведомлениями
            await self._rate_limit_delay(user_id)

            logger.debug(f"  📤 Отправка пользователю {user_id} ({idx}/{len(users)})...")

            try:
                await self._send_with_retry(
                    user_id=user_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                
                result['sent'] += 1
                logger.info(f"  ✅ Отправлено пользователю {user_id} ({idx}/{len(users)})")

                # Логируем отправку
                self.db.log_notification(user_id, 0, 'new_movie')

                # Callback для прогресса
                if progress_callback:
                    await progress_callback(result['sent'], len(users), user_id)

            except TelegramForbiddenError:
                result['blocked'] += 1
                logger.warning(f"  🚫 Бот заблокирован пользователем {user_id}")
                result['errors'].append({
                    'user_id': user_id,
                    'error': 'bot_blocked',
                    'idx': idx
                })

            except TelegramRetryAfter as e:
                # Flood control - ждем указанное время
                wait_time = e.retry_after
                logger.warning(f"  ⏳ Flood control для {user_id}, ждем {wait_time}с")
                result['errors'].append({
                    'user_id': user_id,
                    'error': f'flood_control_{wait_time}s',
                    'idx': idx
                })
                await asyncio.sleep(wait_time)
                result['failed'] += 1

            except Exception as e:
                result['failed'] += 1
                error_msg = f"  ❌ Не удалось отправить пользователю {user_id}: {type(e).__name__}: {e}"
                logger.error(error_msg)
                result['errors'].append({
                    'user_id': user_id,
                    'error': str(e),
                    'idx': idx
                })

            # Логирование прогресса каждые BATCH_SIZE сообщений
            if idx % self.BATCH_SIZE == 0:
                logger.info(f"📊 Прогресс: {idx}/{len(users)} отправлено, ошибок: {result['failed'] + result['blocked']}")

        elapsed = (datetime.now() - result['start_time']).total_seconds()
        logger.info(
            f"🔔 Рассылка завершена: "
            f"отправлено={result['sent']}, "
            f"заблокировано={result['blocked']}, "
            f"ошибок={result['failed']}, "
            f"время={elapsed:.1f}с, "
            f"фильм='{movie.title}'"
        )
        
        result['end_time'] = datetime.now()
        result['elapsed_seconds'] = elapsed
        
        return result

    async def _send_with_retry(
        self,
        user_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup = None,
        parse_mode: str = "Markdown",
        max_attempts: int = None
    ) -> bool:
        """
        Отправка сообщения с повторными попытками
        
        Returns:
            True если отправлено успешно
        """
        if max_attempts is None:
            max_attempts = self.MAX_RETRY_ATTEMPTS

        for attempt in range(1, max_attempts + 1):
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return True

            except TelegramForbiddenError:
                raise  # Сразу пробрасываем, нет смысла retry'ить

            except TelegramRetryAfter as e:
                if attempt == max_attempts:
                    raise
                wait_time = e.retry_after
                logger.warning(f"  Попытка {attempt}/{max_attempts} failed, ждем {wait_time}с...")
                await asyncio.sleep(wait_time)

            except Exception as e:
                if attempt == max_attempts:
                    raise
                logger.warning(f"  Попытка {attempt}/{max_attempts} failed: {e}")
                await asyncio.sleep(1 * attempt)  # Exponential backoff

        return False

    async def _rate_limit_delay(self, user_id: int):
        """Rate limiting между уведомлениями одному пользователю"""
        now = datetime.now()
        last_time = self._last_notification_time.get(user_id)
        
        if last_time:
            elapsed = (now - last_time).total_seconds()
            if elapsed < self.RATE_LIMIT_DELAY:
                await asyncio.sleep(self.RATE_LIMIT_DELAY - elapsed)
        
        self._last_notification_time[user_id] = now

    async def notify_reminder(
        self,
        user_id: int,
        movie: MovieInfo,
        days_since_view: int
    ) -> bool:
        """
        Отправить напоминание о просмотренном фильме

        Returns:
            True если уведомление отправлено успешно
        """
        message = (
            f"🔔 **Напоминание**\n\n"
            f"Вы смотрели фильм **{movie.title}** {days_since_view} дн. назад.\n\n"
            f"Хотите пересмотреть или найти что-то похожее?\n\n"
            f"🔍 Код: `{movie.code}`"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎬 Смотреть снова",
                        callback_data=f"movie_{movie.code}"
                    ),
                    InlineKeyboardButton(
                        text="🔍 Похожие",
                        callback_data=f"similar_{movie.code}"
                    )
                ]
            ]
        )

        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            logger.info(f"Отправлено напоминание пользователю {user_id} о фильме {movie.code}")
            return True

        except TelegramForbiddenError:
            logger.warning(f"Не удалось отправить напоминание пользователю {user_id}: бот заблокирован")
            return False
            
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
            return False

    async def notify_achievement(
        self,
        user_id: int,
        achievement_name: str,
        achievement_icon: str,
        lang: str = "ru"
    ) -> bool:
        """
        Уведомить о получении достижения

        Returns:
            True если уведомление отправлено успешно
        """
        message = (
            f"{achievement_icon} **Новое достижение!**\n\n"
            f"🏆 {achievement_name}\n\n"
            f"Продолжайте пользоваться ботом и открывайте новые достижения!"
        )

        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"Отправлено уведомление о достижении пользователю {user_id}")
            return True

        except TelegramForbiddenError:
            logger.warning(f"Не удалось отправить уведомление о достижении пользователю {user_id}: бот заблокирован")
            return False

        except Exception as e:
            logger.error(f"Не удалось отправить уведомление о достижении пользователю {user_id}: {e}")
            return False

    async def broadcast_message(
        self,
        message_text: str,
        keyboard: InlineKeyboardMarkup | None = None,
        exclude_admins: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        Массовая рассылка сообщения всем пользователям

        Returns:
            Dict с результатами: {'sent': int, 'failed': int, 'blocked': int}
        """
        users = self.db.get_all_users_with_notifications()
        
        result = {
            'sent': 0,
            'failed': 0,
            'blocked': 0,
            'total': len(users)
        }

        for idx, user in enumerate(users, 1):
            user_id = user['user_id']

            if exclude_admins and user_id in self.db.admin_ids:
                continue

            await self._rate_limit_delay(user_id)

            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                result['sent'] += 1

                if progress_callback:
                    await progress_callback(result['sent'], len(users), user_id)

            except TelegramForbiddenError:
                result['blocked'] += 1
                logger.warning(f"Бот заблокирован пользователем {user_id}")

            except Exception as e:
                result['failed'] += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")

            if idx % self.BATCH_SIZE == 0:
                logger.info(f"📊 Прогресс рассылки: {idx}/{len(users)}")

        logger.info(f"Рассылка завершена: отправлено {result['sent']}, заблокировано {result['blocked']}, ошибок {result['failed']}")
        return result

    def get_stats(self) -> Dict:
        """Получить статистику сервиса уведомлений"""
        return {
            'rate_limit_delay': self.RATE_LIMIT_DELAY,
            'batch_size': self.BATCH_SIZE,
            'max_retry_attempts': self.MAX_RETRY_ATTEMPTS,
            'last_notification_time': self._last_notification_time
        }
