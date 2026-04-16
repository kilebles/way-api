import asyncio
import sys

from loguru import logger

from src.accounts import load_accounts
from src.generator import generate_video

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="DEBUG",
    colorize=True,
)


async def main() -> None:
    accounts = load_accounts()
    if not accounts:
        logger.error("No accounts found in accounts/")
        return

    logger.info("Loaded {} account(s)", len(accounts))

    tasks = [
        generate_video(
            account=account,
            prompt="monke monk",
            name="test generation",
            duration=15,
            explore_mode=True,
        )
        for account in accounts
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for account, result in zip(accounts, results):
        if isinstance(result, Exception):
            logger.error("[{}] Failed: {}", account.name, result)
        else:
            logger.success("[{}] {} file(s) saved", account.name, len(result))


if __name__ == "__main__":
    asyncio.run(main())
