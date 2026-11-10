from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


APP_DIR = Path.home() / ".personalbank"
DEFAULT_DATABASE = APP_DIR / "personalbank.sqlite3"
CONFIG_FILE = APP_DIR / "settings.json"


@dataclass
class AppConfig:
    database_path: str = str(DEFAULT_DATABASE)
    currency: str = "USD"
    locale: str = "en_US"
    theme: str = "light"
    date_format: str = "yyyy-MM-dd"
    confirm_deletes: bool = True
    start_page: str = "Dashboard"

    @classmethod
    def load(cls) -> "AppConfig":
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            config = cls()
            config.save()
            return config
        try:
            payload = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            known = {key: value for key, value in payload.items() if key in cls.__dataclass_fields__}
            return cls(**known)
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def update(self, **changes: Any) -> None:
        for key, value in changes.items():
            if key in self.__dataclass_fields__:
                setattr(self, key, value)
        self.save()
