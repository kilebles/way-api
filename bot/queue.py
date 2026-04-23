import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from aiogram.types import Message
from loguru import logger

from src.xlsx import Row


@dataclass
class GenerationJob:
    message: Message
    accounts: list
    rows: list[Row]
    output_dir: Path
    duration: int
    filename: str
    done: int = field(default=0)
    failed: int = field(default=0)

    @property
    def total(self) -> int:
        return len(self.rows)


_queue: asyncio.Queue[GenerationJob] = asyncio.Queue()
_current: GenerationJob | None = None
_worker_task: asyncio.Task | None = None


def get_status() -> tuple[GenerationJob | None, list[GenerationJob]]:
    """Returns (current_job, list of pending jobs). Read-only, no side effects."""
    pending = list(_queue._queue)  # type: ignore[attr-defined]
    return _current, pending


async def enqueue(job: GenerationJob) -> int:
    await _queue.put(job)
    return _queue.qsize()


async def _worker() -> None:
    global _current
    from bot.handlers.generate import _run_generation
    while True:
        job = await _queue.get()
        _current = job
        logger.info("Queue: starting {} ({} pending)", job.filename, _queue.qsize())
        try:
            await _run_generation(job)
        except Exception as e:
            logger.error("Queue: job {} failed: {}", job.filename, e)
        finally:
            _current = None
            _queue.task_done()


def start_worker() -> None:
    global _worker_task
    _worker_task = asyncio.create_task(_worker())
