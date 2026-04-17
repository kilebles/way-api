from aiogram import Bot
from aiogram.types import BotCommand
from loguru import logger

COMMANDS = [
    BotCommand(command="generate", description="Сгенерировать видео"),
    BotCommand(command="export", description="Экспортировать видео")
]


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(COMMANDS)
    logger.info("Bot commands registered: {}", [c.command for c in COMMANDS])
