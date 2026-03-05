"""
Базовые команды пользователя: /start, /help, /language, /support
"""
import logging
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import Config
from database import Database
from keyboards import get_main_keyboard, get_channels_keyboard
from texts import get_text

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, config: Config):
    """Обработчик команды /start"""
    await state.clear()
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS

    # Импортируем функцию из bot_new
    from bot_new import check_subscription_cached
    result = await check_subscription_cached(user_id, force_check=True, db=db, config=config, bot=message.bot)

    # result это dict с ключами 'is_subscribed' и 'failed_channels'
    if result.get('is_subscribed', False):
        await message.answer(
            get_text("start_subscribed", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    else:
        # Получаем полную информацию о каналах
        all_channels = db.get_channels() or config.CHANNELS
        failed_channels_data = [
            ch for ch in all_channels
            if ch['name'] in result.get('failed_channels', [])
        ]
        failed = "\n".join([f"• {ch['name']}" for ch in failed_channels_data])
        await message.answer(
            get_text("subscription_check_failed", lang, failed_channels=failed),
            reply_markup=get_channels_keyboard(failed_channels_data, lang),
            disable_web_page_preview=True
        )


@router.message(Command("help"))
async def cmd_help(message: Message, db: Database, config: Config):
    """Обработчик команды /help"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    
    await message.answer(
        get_text("command_help", lang),
        reply_markup=get_main_keyboard(lang, is_admin=is_admin),
        parse_mode="Markdown"
    )


@router.message(Command("language"))
async def cmd_language(message: Message, db: Database):
    """Обработчик команды /language"""
    user_id = message.from_user.id
    current_lang = db.get_user_language(user_id)
    new_lang = "en" if current_lang == "ru" else "ru"
    
    is_admin = user_id in Config.ADMIN_IDS
    db.set_user_language(user_id, new_lang)
    
    await message.answer(
        get_text("language_changed", new_lang),
        reply_markup=get_main_keyboard(new_lang, is_admin=is_admin)
    )


@router.message(Command("support"))
async def cmd_support(message: Message, db: Database, config: Config):
    """Обработчик команды /support"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    
    await message.answer(
        get_text("command_support", lang, support_link=config.SUPPORT_LINK),
        reply_markup=get_main_keyboard(lang, is_admin=is_admin),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext, db: Database, config: Config):
    """Кнопка 'Меню' - возвращает в главное меню"""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_IDS
    
    await state.clear()
    
    try:
        await callback.message.edit_text(
            get_text("command_start", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            get_text("command_start", lang),
            reply_markup=get_main_keyboard(lang, is_admin=is_admin),
            parse_mode="Markdown"
        )
    
    await callback.answer()
