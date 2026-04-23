import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from bot.commands import set_commands
from bot.config import bot_settings
from bot.handlers import register_all
from bot.queue import start_worker

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="DEBUG",
    colorize=True,
)


async def main() -> None:
    bot = Bot(
        token=bot_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    register_all(dp)

    @dp.startup()
    async def on_startup() -> None:
        await set_commands(bot)
        start_worker()
        me = await bot.get_me()
        logger.info("Bot started: @{}", me.username)

    @dp.shutdown()
    async def on_shutdown() -> None:
        logger.info("Bot stopped")
        await bot.session.close()

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
