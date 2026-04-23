import asyncio
import re
from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Document, InlineKeyboardButton, InlineKeyboardMarkup, Message
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


_DURATION_OPTIONS = [5, 10, 15]

_DURATION_KB = InlineKeyboardMarkup(
    inline_keyboard=[[
        InlineKeyboardButton(text=f"{d} сек", callback_data=f"gen:duration:{d}")
        for d in _DURATION_OPTIONS
    ]]
)


class GenerateStates(StatesGroup):
    waiting_duration = State()
    waiting_file = State()


@router.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext) -> None:
    logger.info("User {} issued /generate", message.from_user.id)
    await state.set_state(GenerateStates.waiting_duration)
    await message.answer("Выберите длительность видео:", reply_markup=_DURATION_KB)


@router.callback_query(GenerateStates.waiting_duration, lambda c: c.data and c.data.startswith("gen:duration:"))
async def cb_duration(call: CallbackQuery, state: FSMContext) -> None:
    duration = int(call.data.removeprefix("gen:duration:"))
    await state.update_data(duration=duration)
    await state.set_state(GenerateStates.waiting_file)
    await call.answer()
    await call.message.edit_text(f"Длительность: {duration} сек. Теперь отправьте xlsx файл.")


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

    data = await state.get_data()
    duration: int = data["duration"]
    await state.clear()

    # Пропускаем уже сгенерированные
    pending = [r for r in rows if not (output_dir / f"{r.number}.mp4").exists()]
    skipped = len(rows) - len(pending)

    if skipped:
        logger.info("Skipping {} already generated videos", skipped)

    if not pending:
        await message.answer("Все видео уже сгенерированы.")
        return

    from bot.queue import GenerationJob, enqueue
    job = GenerationJob(
        message=message,
        accounts=accounts,
        rows=pending,
        output_dir=output_dir,
        duration=duration,
        filename=doc.file_name,
    )
    position = await enqueue(job)
    if position > 1:
        await message.answer(f"{doc.file_name} поставлен в очередь (позиция {position})")
    else:
        await message.answer(f"{doc.file_name} начал генерироваться")




async def _run_generation(job: "GenerationJob") -> None:
    from bot.queue import GenerationJob
    message, accounts, rows, output_dir, duration = job.message, job.accounts, job.rows, job.output_dir, job.duration

    row_queue: asyncio.Queue[Row] = asyncio.Queue()
    for row in rows:
        await row_queue.put(row)

    async def worker(account, sem: asyncio.Semaphore) -> None:
        while True:
            try:
                row = row_queue.get_nowait()
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
                        duration=duration,
                        explore_mode=True,
                    )
                if ok:
                    job.done += 1
                    logger.success("Saved {} → {}", row.number, dest)
                else:
                    job.failed += 1
            except Exception as e:
                job.failed += 1
                logger.error("Failed {} | {}", row.number, e)
            finally:
                row_queue.task_done()

    async def launch_account(acc, delay: float) -> None:
        await asyncio.sleep(delay)
        sem = asyncio.Semaphore(settings.account_concurrency)
        await asyncio.gather(*[worker(acc, sem) for _ in range(settings.account_concurrency)])

    await asyncio.gather(*[
        launch_account(acc, i * 2.0)
        for i, acc in enumerate(accounts)
    ])

    logger.info("Generation complete: done={} failed={} total={}", job.done, job.failed, job.total)
    await message.answer(f"Готово: {job.done}/{job.total}" + (f" | ошибок: {job.failed}" if job.failed else ""))

    if job.done > 0 and settings.yandex_disk_token:
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
