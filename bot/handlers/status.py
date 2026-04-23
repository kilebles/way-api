from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.queue import get_status

router = Router(name="status")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    current, pending = get_status()

    if not current and not pending:
        await message.answer("Очередь пуста.")
        return

    lines: list[str] = []

    if current:
        lines.append(f"Генерируется: <b>{current.filename}</b> — {current.done}/{current.total}")

    if pending:
        lines.append(f"\nВ очереди ({len(pending)}):")
        for i, job in enumerate(pending, 1):
            lines.append(f"  {i}. {job.filename}")

    await message.answer("\n".join(lines))
