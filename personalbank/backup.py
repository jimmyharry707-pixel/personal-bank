from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import Database


class BackupService:
    def __init__(self, database: Database):
        self.database = database

    def create_backup(self, destination: str | Path) -> Path:
        destination = Path(destination).expanduser()
        if destination.resolve() == self.database.path.resolve():
            raise ValueError("Backup destination must be different from the live database file.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = self.database.connect()
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("Backup failed SQLite integrity_check.")
            target.commit()
        finally:
            target.close()
            source.close()
        return destination

    def restore_backup(self, source_path: str | Path) -> None:
        source_path = Path(source_path).expanduser()
        if source_path.resolve() == self.database.path.resolve():
            raise ValueError("Choose a backup file different from the live database file.")
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        source = sqlite3.connect(source_path)
        try:
            check = source.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                raise ValueError("Backup file failed SQLite integrity_check.")
            tables = {
                row[0] for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "accounts" not in tables or "transactions" not in tables:
                raise ValueError("This file does not look like a PersonalBank database.")
            target = self.database.connect()
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
