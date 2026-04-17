import json
from pathlib import Path

from pydantic import BaseModel


class Account(BaseModel):
    bearer_token: str
    proxy: str | None = None
    app_version: str
    client_id: str
    workspace_id: int
    name: str = ""

    @property
    def proxy_url(self) -> str | None:
        """Convert host:port:user:pass → http://user:pass@host:port"""
        if not self.proxy:
            return None
        parts = self.proxy.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"http://{user}:{password}@{host}:{port}"
        return self.proxy  # already a URL


def load_accounts(accounts_dir: Path = Path("accounts")) -> list[Account]:
    accounts = []
    for path in sorted(accounts_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if not data.get("bearer_token"):
            continue
        data.setdefault("name", path.stem)
        accounts.append(Account(**data))
    return accounts
