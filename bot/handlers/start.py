from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from loguru import logger

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    logger.info("User {} issued /start", message.from_user.id)
    await message.answer("Воспользуйтесь командами.")
