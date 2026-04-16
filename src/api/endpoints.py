import asyncio

import httpx
from loguru import logger

from src.models import Task
from src.settings import settings


def _team(workspace_id: int) -> dict:
    return {"asTeamId": workspace_id}


async def create_session(client: httpx.AsyncClient, workspace_id: int) -> str:
    resp = await client.post("/v1/sessions", json={**_team(workspace_id), "taskIds": []})
    resp.raise_for_status()
    session_id: str = resp.json()["session"]["id"]
    logger.info("Session created: {}", session_id)
    return session_id


async def create_asset_group(client: httpx.AsyncClient, workspace_id: int, session_id: str) -> str:
    resp = await client.post(f"/v1/sessions/{session_id}/assetGroup", json=_team(workspace_id))
    resp.raise_for_status()
    asset_group_id: str = resp.json()["assetGroup"]["id"]
    logger.info("AssetGroup created: {}", asset_group_id)
    return asset_group_id


async def submit_task(
    client: httpx.AsyncClient,
    workspace_id: int,
    session_id: str,
    task_type: str,
    options: dict,
) -> Task:
    payload = {
        "taskType": task_type,
        "options": options,
        "asTeamId": workspace_id,
        "sessionId": session_id,
    }
    logger.debug("Submitting task: {}", payload)

    while True:
        resp = await client.post("/v1/tasks", json=payload)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", settings.poll_interval_throttled))
            logger.warning("429 Too Many Requests — retrying in {}s", retry_after)
            await asyncio.sleep(retry_after)
            continue
        resp.raise_for_status()
        break

    task = Task.from_api(resp.json())
    logger.info("Task submitted: {} | status={}", task.id, task.status)
    return task


async def get_task(client: httpx.AsyncClient, workspace_id: int, task_id: str) -> Task:
    resp = await client.get(f"/v1/tasks/{task_id}", params=_team(workspace_id))
    resp.raise_for_status()
    return Task.from_api(resp.json())
