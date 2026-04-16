import httpx
from loguru import logger

from src.accounts import Account

BASE_URL = "https://api.runwayml.com"


def make_client(account: Account) -> httpx.AsyncClient:
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "authorization": f"Bearer {account.bearer_token}",
        "content-type": "application/json",
        "origin": "https://app.runwayml.com",
        "referer": "https://app.runwayml.com/",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        ),
        "x-runway-client-id": account.client_id,
        "x-runway-source-application": "web",
        "x-runway-source-application-version": account.app_version,
        "x-runway-workspace": str(account.workspace_id),
    }

    proxies = {"all://": account.proxy} if account.proxy else None

    client = httpx.AsyncClient(
        base_url=BASE_URL,
        headers=headers,
        proxy=account.proxy,
        http2=True,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )
    logger.debug("Client created → {} (proxy={})", account.name, account.proxy or "none")
    return client
