import asyncio

import httpx
from loguru import logger

from src.models import Task
from src.settings import settings

_submit_locks: dict[int, asyncio.Lock] = {}


def _get_submit_lock(workspace_id: int) -> asyncio.Lock:
    if workspace_id not in _submit_locks:
        _submit_locks[workspace_id] = asyncio.Lock()
    return _submit_locks[workspace_id]


def _team(workspace_id: int) -> dict:
    return {"asTeamId": workspace_id}


async def create_session(client: httpx.AsyncClient, workspace_id: int, account_name: str) -> str:
    resp = await client.post("/v1/sessions", json={**_team(workspace_id), "taskIds": []})
    resp.raise_for_status()
    session_id: str = resp.json()["session"]["id"]
    logger.debug("[{}] Session created: {}", account_name, session_id)
    return session_id


async def create_asset_group(client: httpx.AsyncClient, workspace_id: int, session_id: str, account_name: str) -> str:
    resp = await client.post(f"/v1/sessions/{session_id}/assetGroup", json=_team(workspace_id))
    resp.raise_for_status()
    asset_group_id: str = resp.json()["assetGroup"]["id"]
    logger.debug("[{}] AssetGroup created: {}", account_name, asset_group_id)
    return asset_group_id


async def submit_task(
    client: httpx.AsyncClient,
    workspace_id: int,
    task_type: str,
    options: dict,
    account_name: str,
) -> Task:
    async with _get_submit_lock(workspace_id):
        session_id = await create_session(client, workspace_id, account_name)
        asset_group_id = await create_asset_group(client, workspace_id, session_id, account_name)
        options = {**options, "assetGroupId": asset_group_id}

        payload = {
            "taskType": task_type,
            "options": options,
            "asTeamId": workspace_id,
            "sessionId": session_id,
        }

        while True:
            resp = await client.post("/v1/tasks", json=payload)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", settings.poll_interval_throttled))
                logger.warning("[{}] 429 Too Many Requests — retrying in {}s", account_name, retry_after)
                await asyncio.sleep(retry_after)
                continue
            resp.raise_for_status()
            break

    task = Task.from_api(resp.json())
    logger.info("[{}] Task submitted: {} | status={}", account_name, task.id, task.status)
    return task


async def check_token(client: httpx.AsyncClient, workspace_id: int) -> bool:
    try:
        resp = await client.post("/v1/sessions", json={**_team(workspace_id), "taskIds": []})
        return resp.status_code == 200
    except Exception:
        return False


async def get_task(client: httpx.AsyncClient, workspace_id: int, task_id: str) -> Task:
    resp = await client.get(f"/v1/tasks/{task_id}", params=_team(workspace_id))
    resp.raise_for_status()
    return Task.from_api(resp.json())
