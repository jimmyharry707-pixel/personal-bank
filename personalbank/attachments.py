from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from .domain import now_iso


MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}


class ReceiptAttachmentService:
    """Store local receipt documents inside the SQLite database."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    def add(self, transaction_id: int, source_path: str | Path) -> int:
        transaction_id = int(transaction_id)
        if not self.finance.transactions.get(transaction_id):
            raise ValueError("Transaction was not found.")

        source = Path(source_path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.suffix.lower() not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise ValueError("Choose a PDF, PNG, JPG, WEBP, or GIF receipt file.")

        with source.open("rb") as handle:
            content = handle.read(MAX_ATTACHMENT_BYTES + 1)
        if not content:
            raise ValueError("Receipt files cannot be empty.")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError("Receipt files must be 25 MB or smaller.")

        filename = source.name
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        timestamp = now_iso()
        with self.db.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO transaction_attachments(
                    transaction_id, filename, media_type, size_bytes, content, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)""",
                (transaction_id, filename, media_type, len(content), content, timestamp),
            )
            attachment_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('transaction_attachment', ?, 'attach', ?, ?)""",
                (attachment_id, f"transaction:{transaction_id}:{filename}", timestamp),
            )
        return attachment_id

    def list_for_transaction(self, transaction_id: int) -> list[Any]:
        transaction_id = int(transaction_id)
        if not self.finance.transactions.get(transaction_id):
            raise ValueError("Transaction was not found.")
        return self.db.fetch_all(
            """SELECT id, transaction_id, filename, media_type, size_bytes, created_at
               FROM transaction_attachments WHERE transaction_id = ?
               ORDER BY created_at, id""",
            (transaction_id,),
        )

    def get(self, attachment_id: int) -> Any | None:
        return self.db.fetch_one(
            "SELECT * FROM transaction_attachments WHERE id = ?", (int(attachment_id),)
        )

    def delete(self, attachment_id: int) -> None:
        attachment_id = int(attachment_id)
        row = self.get(attachment_id)
        if not row:
            raise ValueError("Receipt attachment was not found.")
        timestamp = now_iso()
        with self.db.transaction() as connection:
            connection.execute(
                "DELETE FROM transaction_attachments WHERE id = ?", (attachment_id,)
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('transaction_attachment', ?, 'remove', ?, ?)""",
                (attachment_id, f"transaction:{row['transaction_id']}:{row['filename']}", timestamp),
            )