import asyncio
import re
from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Document, Message
from loguru import logger

from src.accounts import load_accounts
from src.generator import generate_video
from src.settings import settings
from src.xlsx import Row, read_rows
from src.yandex_disk import upload_videos

router = Router(name="generate")

_NAME_RE = re.compile(r"^([a-zA-Z]+)_(\d+)")


def _output_path(filename: str) -> Path | None:
    m = _NAME_RE.match(Path(filename).stem)
    if not m:
        return None
    return settings.output_dir / m.group(1) / m.group(2)


class GenerateStates(StatesGroup):
    waiting_file = State()


@router.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext) -> None:
    logger.info("User {} issued /generate", message.from_user.id)
    await state.set_state(GenerateStates.waiting_file)
    await message.answer("Отправьте xlsx файл.")


@router.message(GenerateStates.waiting_file)
async def handle_file(message: Message, state: FSMContext, bot: Bot) -> None:
    doc: Document | None = message.document

    if not doc or not doc.file_name or not doc.file_name.endswith(".xlsx"):
        await message.answer("Нужен xlsx файл.")
        return

    output_dir = _output_path(doc.file_name)
    if not output_dir:
        await message.answer("Неверное имя файла. Ожидается формат: <code>category_number.xlsx</code>")
        return

    input_path = settings.input_dir / doc.file_name
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, destination=input_path)
    logger.info("User {} uploaded {} → output dir: {}", message.from_user.id, doc.file_name, output_dir)

    rows = read_rows(input_path)
    if not rows:
        await message.answer("Файл пустой или неверная структура.")
        return

    accounts = load_accounts()
    if not accounts:
        await message.answer("Нет доступных аккаунтов.")
        return

    await state.clear()

    # Пропускаем уже сгенерированные
    pending = [r for r in rows if not (output_dir / f"{r.number}.mp4").exists()]
    skipped = len(rows) - len(pending)

    if skipped:
        logger.info("Skipping {} already generated videos", skipped)

    if not pending:
        await message.answer("Все видео уже сгенерированы.")
        return

    await message.answer(
        f"Запускаю генерацию: {len(pending)} видео"
        + (f" (пропущено {skipped} уже готовых)" if skipped else "")
    )

    asyncio.create_task(_run_generation(message, accounts, pending, output_dir))




async def _run_generation(message: Message, accounts: list, rows: list[Row], output_dir: Path) -> None:
    queue: asyncio.Queue[Row] = asyncio.Queue()
    for row in rows:
        await queue.put(row)

    done = 0
    failed = 0
    total = len(rows)

    async def worker(account, sem: asyncio.Semaphore) -> None:
        nonlocal done, failed
        while True:
            try:
                row = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            dest = output_dir / f"{row.number}.mp4"
            logger.info("[{}] Generating {} | prompt={!r}", account.name, row.number, row.prompt)
            try:
                async with sem:
                    ok = await generate_video(
                        account=account,
                        prompt=row.prompt,
                        dest=dest,
                        name=row.number,
                        explore_mode=True,
                    )
                if ok:
                    done += 1
                    logger.success("Saved {} → {}", row.number, dest)
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.error("Failed {} | {}", row.number, e)
            finally:
                queue.task_done()

    # Один семафор на аккаунт — ограничивает до N одновременных генераций
    async def launch_account(acc, delay: float) -> None:
        await asyncio.sleep(delay)
        sem = asyncio.Semaphore(settings.account_concurrency)
        await asyncio.gather(*[worker(acc, sem) for _ in range(settings.account_concurrency)])

    # Запускаем аккаунты с задержкой чтобы не флудить сабмитами одновременно
    await asyncio.gather(*[
        launch_account(acc, i * 2.0)
        for i, acc in enumerate(accounts)
    ])

    logger.info("Generation complete: done={} failed={} total={}", done, failed, total)
    await message.answer(f"Готово: {done}/{total}" + (f" | ошибок: {failed}" if failed else ""))

    if done > 0 and settings.yandex_disk_token:
        category, number = output_dir.parts[-2], output_dir.parts[-1]
        await message.answer(f"Загружаю на Яндекс Диск...")
        try:
            ok = await upload_videos(settings.yandex_disk_token, category, number, output_dir)
            if ok:
                await message.answer(f"Загружено на Яндекс Диск: {category}/{number}")
            else:
                await message.answer("Ошибка загрузки на Яндекс Диск.")
        except Exception as e:
            logger.error("Yandex Disk upload failed: {}", e)
            await message.answer(f"Ошибка загрузки: {e}")
