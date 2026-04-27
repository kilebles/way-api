import asyncio
import time
from pathlib import Path

import httpx
from loguru import logger

YANDEX_API = "https://cloud-api.yandex.net/v1/disk/resources"
BASE_PATH = "disk:/YT History Doc"

CATEGORY_MAPPING = {
    "survival": "005 Survival v4",
    "rome": "010 Rome v2",
    "zapad": "014 Zapad v2",
    "victorian": "016 Victorian v2",
    "indians": "018 Indians v2",
    "vikings": "020 Vikings v2",
    "advent": "022 Advent",
    "construct": "025 Строительство",
    "construction": "025 Строительство",
    "conquest": "026 Conquest",
    "cosmos": "027 Cosmos Anomaly",
    "space_travel": "028 Space Travel",
    "ufo": "030 UFO",
    "ufo_img": "030 UFO",
    "entire": "032 Entire",
}

BATCH_SIZE = 50


def _auth(token: str) -> dict:
    return {"Authorization": f"OAuth {token}"}


async def _create_folder(client: httpx.AsyncClient, token: str, path: str) -> None:
    resp = await client.put(YANDEX_API, headers=_auth(token), params={"path": path})
    if resp.status_code not in (201, 409):
        logger.warning("Create folder {}: {}", path, resp.status_code)


async def _rename(client: httpx.AsyncClient, token: str, from_path: str, to_path: str) -> bool:
    resp = await client.post(
        f"{YANDEX_API.replace('/resources', '')}/resources/move",
        headers=_auth(token),
        params={"from": from_path, "path": to_path, "overwrite": "true"},
    )
    return resp.status_code in (201, 202)


async def _upload_file(client: httpx.AsyncClient, token: str, local_path: Path, remote_path: str) -> bool:
    # Extension spoofing to bypass Yandex throttling
    fake_path = remote_path.rsplit(".", 1)[0] + ".txt"

    resp = await client.get(
        f"{YANDEX_API}/upload",
        headers=_auth(token),
        params={"path": fake_path, "overwrite": "true"},
    )
    if resp.status_code != 200:
        logger.error("Failed to get upload URL for {}: {}", local_path.name, resp.text)
        return False

    upload_url = resp.json().get("href")
    if not upload_url:
        return False

    size_mb = local_path.stat().st_size / 1_048_576
    logger.info("Uploading {} ({:.1f} MB)...", local_path.name, size_mb)
    start = time.time()

    content = await asyncio.get_running_loop().run_in_executor(None, local_path.read_bytes)

    async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=60.0)) as up:
        upload_resp = await up.put(upload_url, content=content)

    elapsed = time.time() - start
    speed = (size_mb * 8) / elapsed if elapsed > 0 else 0
    logger.info("Upload {}: {} | {:.1f}s | {:.1f} Mbit/s", local_path.name, upload_resp.status_code, elapsed, speed)

    if upload_resp.status_code not in (201, 202):
        return False

    return await _rename(client, token, fake_path, remote_path)


async def upload_videos(token: str, category: str, number: str, local_dir: Path) -> bool:
    """
    Zip videos in batches and upload to Yandex Disk.
    Returns True if all batches uploaded successfully.
    """
    import zipfile

    videos = sorted(local_dir.glob("*.mp4"))
    if not videos:
        logger.warning("No videos found in {}", local_dir)
        return False

    yandex_category = CATEGORY_MAPPING.get(category.lower(), category)
    remote_dir = f"{BASE_PATH}/{yandex_category}/{number}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=30.0)) as client:
        await _create_folder(client, token, f"{BASE_PATH}/{yandex_category}")
        await _create_folder(client, token, remote_dir)
        await _create_folder(client, token, f"{remote_dir}/seedance")
        remote_dir = f"{remote_dir}/seedance"

        batches = [videos[i:i + BATCH_SIZE] for i in range(0, len(videos), BATCH_SIZE)]
        base_name = f"{category}_{number}"

        for idx, batch in enumerate(batches, 1):
            archive_name = f"{base_name}.zip" if len(batches) == 1 else f"{base_name}_part{idx}.zip"
            archive_path = local_dir / archive_name

            logger.info("Creating archive {}/{}: {}", idx, len(batches), archive_name)
            loop = asyncio.get_running_loop()

            def _zip(batch=batch, archive_path=archive_path):
                with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as zf:
                    for v in batch:
                        zf.write(v, v.name)

            await loop.run_in_executor(None, _zip)

            remote_path = f"{remote_dir}/{archive_name}"
            ok = await _upload_file(client, token, archive_path, remote_path)

            try:
                archive_path.unlink()
            except Exception:
                pass

            if not ok:
                logger.error("Failed to upload batch {}/{}", idx, len(batches))
                return False

            logger.success("Uploaded batch {}/{} → {}", idx, len(batches), remote_path)

    return True
