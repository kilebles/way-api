from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Dirs
    input_dir: Path = Path("input")
    output_dir: Path = Path("output")

    # Polling
    poll_interval: float = 3.0
    poll_interval_throttled: float = 30.0
    poll_timeout: float = 3600.0

    # Generation
    account_concurrency: int = 2

    # Yandex Disk
    yandex_disk_token: str = ""


settings = Settings()
