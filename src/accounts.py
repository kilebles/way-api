import json
from pathlib import Path

from pydantic import BaseModel


class Account(BaseModel):
    bearer_token: str
    proxy: str | None = None
    app_version: str
    client_id: str
    workspace_id: int

    @property
    def name(self) -> str:
        return f"account[{self.workspace_id}]"


def load_accounts(accounts_dir: Path = Path("accounts")) -> list[Account]:
    accounts = []
    for path in sorted(accounts_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if not data.get("bearer_token"):
            continue
        accounts.append(Account(**data))
    return accounts
