from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from bot import runtime
from bot.config import config
from bot.fsm_storage import JSONFileStorage
from bot.logger import setup_logging
from bot.middlewares.antispam import AntiSpamMiddleware, DebounceMiddleware
from bot.middlewares.blacklist import BlacklistMiddleware
from bot.middlewares.user_directory import UserDirectoryMiddleware

from bot.handlers import admin_form, anketa_form, dm_bridge, moderation, owner, user_start

logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> None:
    """Глобальный обработчик ошибок: логирует и не даёт боту упасть.
    Пользователь при этом никогда не видит traceback — апдейт просто
    считается обработанным (с ошибкой в логах), а бот продолжает работать."""
    logger.exception(
        "Ошибка при обработке апдейта %s: %s",
        getattr(event.update, "update_id", "?"),
        event.exception,
    )


async def main() -> None:
    setup_logging()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    runtime.bot_username = me.username or ""

    storage = JSONFileStorage(config.fsm_file)
    dp = Dispatcher(storage=storage)

    # Антиспам и защита от блокировки применяются и к сообщениям, и к нажатиям кнопок
    blacklist_mw = BlacklistMiddleware()
    antispam_mw = AntiSpamMiddleware()
    debounce_mw = DebounceMiddleware()
    user_directory_mw = UserDirectoryMiddleware()

    dp.message.middleware(user_directory_mw)
    dp.callback_query.middleware(user_directory_mw)
    dp.message.middleware(blacklist_mw)
    dp.callback_query.middleware(blacklist_mw)
    dp.message.middleware(antispam_mw)
    dp.callback_query.middleware(antispam_mw)
    dp.callback_query.middleware(debounce_mw)

    # Доступно хендлерам как параметр antispam_mw (например, для кнопки
    # "У меня спамблок!", которая должна снимать блокировку мгновенно)
    dp["antispam_mw"] = antispam_mw

    dp.errors.register(on_error)

    # Порядок важен: служебные и модераторские команды регистрируем раньше,
    # чтобы они не перехватывались обработчиками анкеты. dm_bridge — самый
    # общий обработчик (живая переписка), поэтому регистрируется последним.
    dp.include_router(owner.router)
    dp.include_router(moderation.router)
    dp.include_router(user_start.router)
    dp.include_router(anketa_form.router)
    dp.include_router(admin_form.router)
    dp.include_router(dm_bridge.router)

    logger.info("Бот запускается как @%s. Владелец: %s", runtime.bot_username, config.owner_id)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except TelegramAPIError:
        logger.warning("Не удалось сбросить webhook (не критично)")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Бот остановлен.")
