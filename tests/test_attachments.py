import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personalbank.attachments import ReceiptAttachmentService
from personalbank.backup import BackupService
from personalbank.db import Database, SCHEMA_VERSION
from personalbank.services import FinanceService


class ReceiptAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.db = Database(self.folder / "source.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.account = self.finance.create_account("Checking", "checking")
        self.category = self.finance.categories.list(kind="expense")[0]["id"]
        self.transaction_id = self.finance.create_expense(
            self.account, 2500, "2026-02-01", self.category, payee="Market"
        )
        self.attachments = ReceiptAttachmentService(self.finance)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_file(self, name="receipt.png", content=b"receipt bytes"):
        path = self.folder / name
        path.write_bytes(content)
        return path

    def test_attachment_metadata_and_content_round_trip(self):
        attachment_id = self.attachments.add(
            self.transaction_id, self.create_file()
        )
        listed = self.attachments.list_for_transaction(self.transaction_id)
        stored = self.attachments.get(attachment_id)

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["filename"], "receipt.png")
        self.assertNotIn("content", listed[0].keys())
        self.assertEqual(stored["content"], b"receipt bytes")
        self.assertEqual(stored["size_bytes"], len(b"receipt bytes"))

    def test_attachment_validation_rejects_bad_file_and_transaction(self):
        with self.assertRaises(ValueError):
            self.attachments.add(99999, self.create_file())
        with self.assertRaises(ValueError):
            self.attachments.add(self.transaction_id, self.create_file("receipt.exe"))
        with self.assertRaises(ValueError):
            self.attachments.add(self.transaction_id, self.create_file("empty.pdf", b""))
        with patch("personalbank.attachments.MAX_ATTACHMENT_BYTES", 10):
            with self.assertRaises(ValueError):
                self.attachments.add(
                    self.transaction_id, self.create_file("large.pdf", b"x" * 11)
                )

    def test_removing_attachment_and_transaction_cleans_up_rows(self):
        attachment_id = self.attachments.add(
            self.transaction_id, self.create_file()
        )
        self.attachments.delete(attachment_id)
        self.assertEqual(self.attachments.list_for_transaction(self.transaction_id), [])
        with self.assertRaises(ValueError):
            self.attachments.delete(attachment_id)

        second_id = self.attachments.add(self.transaction_id, self.create_file("second.jpg"))
        self.finance.delete_transaction(self.transaction_id)
        self.assertIsNone(self.attachments.get(second_id))

    def test_database_backup_and_restore_preserve_attachments(self):
        attachment_id = self.attachments.add(
            self.transaction_id, self.create_file("receipt.pdf", b"%PDF receipt")
        )
        backup_path = self.folder / "with-attachments.sqlite3"
        BackupService(self.db).create_backup(backup_path)
        restored_db = Database(self.folder / "restored.sqlite3")
        restored_db.initialize()
        BackupService(restored_db).restore_backup(backup_path)

        restored = ReceiptAttachmentService(FinanceService(restored_db)).get(attachment_id)
        self.assertEqual(restored["filename"], "receipt.pdf")
        self.assertEqual(restored["content"], b"%PDF receipt")

    def test_schema_v3_database_upgrades_additively(self):
        with self.db.transaction() as connection:
            connection.execute("DROP TABLE transaction_attachments")
            connection.execute(
                "UPDATE schema_meta SET value = '3' WHERE key = 'version'"
            )

        self.db.initialize()

        version = self.db.fetch_one(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        )["value"]
        tables = {
            row["name"] for row in self.db.fetch_all(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertEqual(version, str(SCHEMA_VERSION))
        self.assertIn("transaction_attachments", tables)
        self.assertTrue(self.finance.transactions.get(self.transaction_id))


if __name__ == "__main__":
    unittest.main()