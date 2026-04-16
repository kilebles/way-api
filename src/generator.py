import asyncio
import time
from pathlib import Path

import httpx
from loguru import logger

from src.accounts import Account
from src.api.client import make_client
from src.api.endpoints import create_asset_group, create_session, get_task, submit_task
from src.models import Task, TaskOptions, TaskStatus
from src.settings import settings


async def _poll_until_done(client: httpx.AsyncClient, workspace_id: int, task_id: str) -> Task:
    deadline = time.monotonic() + settings.poll_timeout
    attempt = 0

    while True:
        task = await get_task(client, workspace_id, task_id)
        attempt += 1
        progress = float(task.progress_ratio or 0) * 100

        logger.info(
            "Poll #{} | status={} | progress={:.1f}% | text={}",
            attempt,
            task.status,
            progress,
            task.progress_text or "-",
        )

        if task.status == TaskStatus.SUCCEEDED:
            logger.success("Task completed in {} polls", attempt)
            return task

        if task.status == TaskStatus.FAILED:
            raise RuntimeError(f"Task failed: {task.error}")

        if time.monotonic() > deadline:
            raise TimeoutError(f"Task {task_id} did not finish in {settings.poll_timeout}s")

        if task.status == TaskStatus.THROTTLED:
            logger.warning("Throttled — next check in {}s", settings.poll_interval_throttled)
            await asyncio.sleep(settings.poll_interval_throttled)
        else:
            await asyncio.sleep(settings.poll_interval)


async def _download_artifact(client: httpx.AsyncClient, url: str, dest: Path) -> None:
    logger.info("Downloading → {}", dest)
    async with client.stream("GET", url) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    logger.debug("  {:.1f} / {:.1f} MB", downloaded / 1e6, total / 1e6)
    logger.success("Saved: {}", dest)


async def generate_video(
    account: Account,
    prompt: str,
    name: str = "generation",
    task_type: str = "seedance_2",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    generate_audio: bool = True,
    explore_mode: bool = False,
) -> list[Path]:
    async with make_client(account) as client:
        logger.info("[{}] Starting: '{}'", account.name, prompt)

        session_id = await create_session(client, account.workspace_id)
        asset_group_id = await create_asset_group(client, account.workspace_id, session_id)

        options = TaskOptions(
            name=name,
            text_prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            generate_audio=generate_audio,
            explore_mode=explore_mode,
            asset_group_id=asset_group_id,
        )

        task = await submit_task(
            client=client,
            workspace_id=account.workspace_id,
            session_id=session_id,
            task_type=task_type,
            options=options.to_api(),
        )

        task = await _poll_until_done(client, account.workspace_id, task.id)

        output_dir = settings.output_dir / task.id
        saved: list[Path] = []

        for i, artifact in enumerate(task.artifacts):
            ext = artifact.url.split("?")[0].rsplit(".", 1)[-1] or "mp4"
            dest = output_dir / f"{i}.{ext}"
            await _download_artifact(client, artifact.url, dest)
            saved.append(dest)

        logger.info("[{}] Done. {} file(s) → {}", account.name, len(saved), output_dir)
        return saved
