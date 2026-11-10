import csv
import tempfile
import unittest
from pathlib import Path

from personalbank.csv_tools import EXPORT_COLUMNS
from personalbank.db import Database
from personalbank.services import FinanceService
from personalbank.statement_import import StatementMatchingService


class StatementMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.db = Database(self.folder / "statement.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.checking = self.finance.create_account("Checking", "checking")
        self.savings = self.finance.create_account("Savings", "savings")
        self.expense_category = self.finance.categories.list(kind="expense")[0]["id"]
        self.matching = StatementMatchingService(self.finance)
        self.path = self.folder / "statement.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_rows(self, rows):
        with self.path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def row(self, **overrides):
        result = {
            "date": "2026-03-10", "type": "expense", "account": "Checking",
            "transfer_account": "", "category": "Groceries", "amount": "12.50",
            "payee": "Market", "description": "Weekly shop", "reference": "R-17",
            "notes": "",
        }
        result.update(overrides)
        return result

    def test_exact_key_and_payee_reference_scores_flag_likely_duplicates(self):
        self.finance.create_expense(
            self.checking, 1250, "2026-03-10", self.expense_category,
            payee="Market", description="Weekly shop", reference="R-17",
        )
        self.write_rows([self.row()])

        result = self.matching.review(str(self.path))[0]

        self.assertTrue(result["valid"])
        self.assertFalse(result["import_selected"])
        self.assertEqual(result["matches"][0]["confidence"], 1.0)
        self.assertIn("100%", result["match_label"])

    def test_same_date_amount_and_account_with_different_payee_is_possible_match(self):
        self.finance.create_expense(
            self.checking, 1250, "2026-03-10", self.expense_category,
            payee="Corner Store", reference="",
        )
        self.write_rows([self.row(payee="Market", reference="")])

        result = self.matching.review(str(self.path))[0]

        self.assertEqual(result["matches"][0]["confidence"], 0.70)
        self.assertFalse(result["import_selected"])

    def test_transfer_matches_include_destination_account(self):
        self.finance.create_transfer(self.checking, self.savings, 5000, "2026-03-10")
        other_account = self.finance.create_account("Other", "cash")
        self.write_rows([self.row(
            type="transfer", amount="50.00", category="", transfer_account="Savings",
        )])
        exact = self.matching.review(str(self.path))[0]
        self.write_rows([self.row(
            type="transfer", amount="50.00", category="", transfer_account="Other",
        )])
        different_destination = self.matching.review(str(self.path))[0]

        self.assertEqual(len(exact["matches"]), 1)
        self.assertEqual(different_destination["matches"], [])
        self.assertTrue(different_destination["import_selected"])

    def test_repeated_rows_in_file_are_marked_after_first_occurrence(self):
        self.write_rows([self.row(), self.row()])

        rows = self.matching.review(str(self.path))

        self.assertTrue(rows[0]["import_selected"])
        self.assertFalse(rows[1]["import_selected"])
        self.assertEqual(rows[1]["duplicate_in_file_line"], 2)

    def test_invalid_rows_are_not_selectable_for_import(self):
        self.write_rows([self.row(date="bad-date"), self.row(account="Unknown")])

        rows = self.matching.review(str(self.path))

        self.assertTrue(all(not row["valid"] for row in rows))
        self.assertTrue(all(not row["import_selected"] for row in rows))
        self.assertIn("Date must use", rows[0]["error"])

    def test_user_can_import_selected_rows_and_leave_matches_out(self):
        self.finance.create_expense(
            self.checking, 1250, "2026-03-10", self.expense_category,
            payee="Market", reference="R-17",
        )
        self.write_rows([self.row(), self.row(date="2026-03-11", amount="7.25")])
        rows = self.matching.review(str(self.path))
        rows[0]["import_selected"] = False

        result = self.matching.import_selected(rows)

        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["selected"], 1)
        self.assertEqual(len(self.finance.list_transactions()), 2)

    def test_empty_selection_does_not_import(self):
        self.write_rows([self.row()])
        rows = self.matching.review(str(self.path))
        rows[0]["import_selected"] = False

        result = self.matching.import_selected(rows)

        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["selected"], 0)
        self.assertEqual(self.finance.list_transactions(), [])


if __name__ == "__main__":
    unittest.main()