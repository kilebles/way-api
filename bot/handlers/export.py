import asyncio
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from src.settings import settings
from src.yandex_disk import upload_videos

router = Router(name="export")


def _available_dirs() -> list[Path]:
    """Return all category/number dirs that contain at least one mp4."""
    output = settings.output_dir
    if not output.exists():
        return []
    return sorted(
        p for p in output.glob("*/*")
        if p.is_dir() and any(p.glob("*.mp4"))
    )


def _build_keyboard(dirs: list[Path]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"📤 {p.parent.name}/{p.name}",
            callback_data=f"export:upload:{p.parent.name}/{p.name}",
        )]
        for p in dirs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    dirs = _available_dirs()
    if not dirs:
        await message.answer("Нет готовых видео для экспорта.")
        return

    if not settings.yandex_disk_token:
        await message.answer("YANDEX_DISK_TOKEN не задан.")
        return

    await message.answer(
        f"Готово к загрузке: {len(dirs)} папок",
        reply_markup=_build_keyboard(dirs),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("export:upload:"))
async def cb_upload(call: CallbackQuery) -> None:
    key = call.data.removeprefix("export:upload:")
    category, number = key.split("/", 1)
    path = settings.output_dir / category / number

    if not path.exists() or not any(path.glob("*.mp4")):
        await call.answer("Папка уже загружена или не найдена.")
        remaining = _available_dirs()
        if remaining:
            await call.message.edit_reply_markup(reply_markup=_build_keyboard(remaining))
        else:
            await call.message.edit_text("Нет папок для загрузки.")
        return

    await call.answer()
    await call.message.edit_text(f"Загружаю {category}/{number}...")

    try:
        ok = await upload_videos(settings.yandex_disk_token, category, number, path)
    except Exception as e:
        logger.error("Export {}/{} failed: {}", category, number, e)
        ok = False

    if not ok:
        await call.message.edit_text(
            f"Ошибка загрузки {category}/{number}.",
            reply_markup=_build_keyboard(_available_dirs()),
        )
        return

    # Delete files and dirs only after successful upload
    for mp4 in path.glob("*.mp4"):
        try:
            mp4.unlink()
        except Exception:
            pass
    try:
        path.rmdir()
    except Exception:
        pass
    try:
        path.parent.rmdir()
    except Exception:
        pass

    logger.success("Exported and cleaned {}/{}", category, number)

    remaining = _available_dirs()
    if remaining:
        await call.message.edit_text(
            f"Загружено: {category}/{number}",
            reply_markup=_build_keyboard(remaining),
        )
    else:
        await call.message.edit_text(f"Загружено: {category}/{number}. Все папки выгружены.")
