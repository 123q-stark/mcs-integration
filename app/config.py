from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    loop_seconds: float
    history_limit: int

    @classmethod
    def from_env(cls) -> "Settings":
        default_db = f"sqlite:///{(PROJECT_ROOT / 'data' / 'demo.db').as_posix()}"
        return cls(
            database_url=os.getenv("EMS_DATABASE_URL", default_db),
            loop_seconds=float(os.getenv("EMS_LOOP_SECONDS", "3")),
            history_limit=int(os.getenv("EMS_HISTORY_LIMIT", "60")),
        )
