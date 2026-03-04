"""
Сервис уведомлений
"""
import logging
from datetime import datetime
from typing import List

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import Database
from app_types import MovieInfo

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис для отправки уведомлений пользователям"""
    
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
    
    async def notify_new_movie(
        self,
        movie: MovieInfo,
        exclude_admins: bool = True
    ) -> int:
        """
        Уведомить всех пользователей о новом фильме

        Returns:
            Количество отправленных уведомлений
        """
        users = self.db.get_all_users_with_notifications()
        sent_count = 0
        failed_count = 0

        from config import Config

        logger.info(f"🔔 Начало рассылки: всего пользователей={len(users)}, exclude_admins={exclude_admins}")

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

        for user in users:
            user_id = user['user_id']

            # Пропускаем админов если нужно
            if exclude_admins and user_id in Config.ADMIN_IDS:
                logger.debug(f"  ⏭️ Пропущен админ: {user_id}")
                continue

            logger.debug(f"  📤 Отправка пользователю {user_id}...")

            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                sent_count += 1
                logger.info(f"  ✅ Отправлено пользователю {user_id}")

                # Логируем отправку
                self.db.log_notification(user_id, 0, 'new_movie')

            except Exception as e:
                failed_count += 1
                logger.error(f"  ❌ Не удалось отправить пользователю {user_id}: {e}")

        logger.info(f"🔔 Рассылка завершена: отправлено={sent_count}, ошибок={failed_count}, фильм='{movie.title}'")
        return sent_count
    
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
            
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление о достижении пользователю {user_id}: {e}")
            return False
    
    async def broadcast_message(
        self, 
        message_text: str,
        keyboard: InlineKeyboardMarkup | None = None,
        exclude_admins: bool = True
    ) -> int:
        """
        Массовая рассылка сообщения всем пользователям
        
        Returns:
            Количество отправленных сообщений
        """
        users = self.db.get_all_users()
        sent_count = 0
        
        for user in users:
            user_id = user['user_id']
            
            if exclude_admins and user_id in self.db.admin_ids:
                continue
            
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
        
        logger.info(f"Отправлено {sent_count} сообщений в рассылке")
        return sent_count
