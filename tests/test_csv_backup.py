import tempfile
import unittest
from pathlib import Path

from personalbank.backup import BackupService
from personalbank.csv_tools import CsvService
from personalbank.db import Database
from personalbank.services import FinanceService


class CsvAndBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.db = Database(self.folder / "source.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.account = self.finance.create_account("Checking", "checking", opening_balance_minor=100000)
        self.category = self.finance.categories.list(kind="expense")[0]["id"]
        self.csv = CsvService(self.finance)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_and_import_round_trip(self):
        self.finance.create_expense(
            self.account, 1250, "2026-03-01", self.category,
            payee="Market", description="Weekly groceries",
        )
        path = self.folder / "transactions.csv"
        self.csv.export_transactions(path)
        preview = self.csv.preview_import(path)
        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]["payee"], "Market")

    def test_backup_integrity_and_restore(self):
        backup_path = self.folder / "backup.sqlite3"
        BackupService(self.db).create_backup(backup_path)
        restored_db = Database(self.folder / "restored.sqlite3")
        restored_db.initialize()
        BackupService(restored_db).restore_backup(backup_path)
        row = restored_db.fetch_one("SELECT name FROM accounts WHERE id = ?", (self.account,))
        self.assertEqual(row["name"], "Checking")

    def test_backup_service_rejects_live_database_as_destination_or_source(self):
        backup = BackupService(self.db)
        with self.assertRaises(ValueError):
            backup.create_backup(self.db.path)
        with self.assertRaises(ValueError):
            backup.restore_backup(self.db.path)

    def test_csv_rejects_missing_required_columns(self):
        path = self.folder / "bad.csv"
        path.write_text("when,kind\n2026-01-01,expense\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.csv.preview_import(path)


if __name__ == "__main__":
    unittest.main()
