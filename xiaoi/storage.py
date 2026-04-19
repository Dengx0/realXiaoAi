from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import XiaoAiAccount


class AccountStorage:
    def __init__(self, path: Optional[str | Path]) -> None:
        self.path = Path(path) if path else None

    def load(self, user_id: str) -> Optional[XiaoAiAccount]:
        if not self.path or not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        account = XiaoAiAccount.from_dict(data)
        if account.user_id != user_id:
            return None
        return account

    def save(self, account: XiaoAiAccount) -> None:
        if not self.path:
            return
        self.path.write_text(
            json.dumps(account.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
