import tempfile
import unittest
import csv
from pathlib import Path

from personalbank.advanced import RecurringTransactionService
from personalbank.db import Database, SCHEMA_VERSION
from personalbank.scenarios import FinancialScenarioService
from personalbank.services import FinanceService


class FinancialScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "scenarios.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.account = self.finance.create_account(
            "Checking", "checking", opening_balance_minor=100_000
        )
        self.category = self.finance.categories.list(kind="expense")[0]["id"]
        self.scenarios = FinancialScenarioService(self.finance)
        self.scenario_id = self.scenarios.create(
            name="Stay the course", account_id=self.account,
            start_date="2026-01-01", horizon_months=3,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_preview_layers_monthly_and_one_time_changes_without_posting(self):
        RecurringTransactionService(self.finance).create(
            name="Salary", kind="income", account_id=self.account,
            category_id=None, amount_minor=200_000, frequency="monthly",
            next_due_date="2026-01-05",
        )
        self.finance.create_bill(
            name="Rent", amount_minor=80_000, due_day=10,
            category_id=self.category, account_id=self.account,
            frequency="monthly", auto_post=False, next_due_date="2026-01-10",
        )
        self.scenarios.add_adjustment(
            self.scenario_id, name="Freelance work", kind="income", cadence="monthly",
            amount_minor=25_000, start_month=2,
        )
        self.scenarios.add_adjustment(
            self.scenario_id, name="Laptop", kind="expense", cadence="one_time",
            amount_minor=150_000, start_month=2,
        )

        result = self.scenarios.preview(self.scenario_id)

        self.assertEqual(len(result["months"]), 3)
        self.assertEqual(result["months"][0]["baseline_net_minor"], 120_000)
        self.assertEqual(result["months"][1]["planned_income_minor"], 25_000)
        self.assertEqual(result["months"][1]["planned_expenses_minor"], 150_000)
        self.assertEqual(result["ending_baseline_minor"], 460_000)
        self.assertEqual(result["ending_scenario_minor"], 360_000)
        self.assertEqual(self.finance.list_transactions(), [])
        self.assertEqual(self.finance.account_balance(self.account), 100_000)

    def test_adjustment_validation_and_update(self):
        with self.assertRaises(ValueError):
            self.scenarios.add_adjustment(
                self.scenario_id, name="Too late", kind="expense", cadence="monthly",
                amount_minor=1000, start_month=4,
            )
        with self.assertRaises(ValueError):
            self.scenarios.add_adjustment(
                self.scenario_id, name="Bad range", kind="expense", cadence="monthly",
                amount_minor=1000, start_month=2, end_month=1,
            )
        adjustment_id = self.scenarios.add_adjustment(
            self.scenario_id, name="Gym", kind="expense", cadence="monthly",
            amount_minor=5000, start_month=1, end_month=2,
        )
        self.scenarios.update_adjustment(adjustment_id, amount_minor=7000, end_month=3)
        self.assertEqual(self.scenarios.adjustments(self.scenario_id)[0]["amount_minor"], 7000)
        self.scenarios.delete_adjustment(adjustment_id)
        self.assertEqual(self.scenarios.adjustments(self.scenario_id), [])

    def test_scenario_creation_validates_name_account_date_and_horizon(self):
        with self.assertRaises(ValueError):
            self.scenarios.create(
                name="  ", account_id=self.account,
                start_date="2026-01-01", horizon_months=3,
            )
        with self.assertRaises(ValueError):
            self.scenarios.create(
                name="Bad date", account_id=self.account,
                start_date="not-a-date", horizon_months=3,
            )
        with self.assertRaises(ValueError):
            self.scenarios.create(
                name="Long plan", account_id=self.account,
                start_date="2026-01-01", horizon_months=61,
            )
        archived_account = self.finance.create_account("Archived", "savings")
        self.finance.archive_account(archived_account)
        with self.assertRaises(ValueError):
            self.scenarios.create(
                name="Archived", account_id=archived_account,
                start_date="2026-01-01", horizon_months=3,
            )

    def test_preview_identifies_first_month_projected_below_zero(self):
        self.scenarios.add_adjustment(
            self.scenario_id, name="Large purchase", kind="expense", cadence="one_time",
            amount_minor=150_000, start_month=2,
        )
        preview = self.scenarios.preview(self.scenario_id)
        self.assertEqual(preview["first_negative_month"], "2026-02")
        self.assertTrue(preview["months"][1]["below_zero"])

    def test_compare_requires_matching_account_dates_and_horizon(self):
        second_id = self.scenarios.create(
            name="Lower spending", account_id=self.account,
            start_date="2026-01-01", horizon_months=3,
        )
        self.scenarios.add_adjustment(
            second_id, name="Cut dining", kind="expense", cadence="monthly",
            amount_minor=10_000,
        )
        comparison = self.scenarios.compare([self.scenario_id, second_id])
        self.assertEqual(len(comparison["ending_balances"]), 2)
        self.assertEqual(comparison["ending_balances"][1]["difference_minor"], -30_000)

        mismatched_id = self.scenarios.create(
            name="Different horizon", account_id=self.account,
            start_date="2026-01-01", horizon_months=2,
        )
        with self.assertRaises(ValueError):
            self.scenarios.compare([self.scenario_id, mismatched_id])

    def test_deleting_scenario_cascades_assumptions(self):
        self.scenarios.add_adjustment(
            self.scenario_id, name="Trip", kind="expense", cadence="one_time",
            amount_minor=5000,
        )
        self.scenarios.delete(self.scenario_id)
        rows = self.db.fetch_all(
            "SELECT id FROM scenario_adjustments WHERE scenario_id = ?", (self.scenario_id,)
        )
        self.assertEqual(rows, [])

    def test_duplicate_copies_settings_and_assumptions(self):
        self.scenarios.add_adjustment(
            self.scenario_id, name="Annual trip", kind="expense", cadence="one_time",
            amount_minor=75_000, start_month=2, notes="Summer travel",
        )
        duplicate_id = self.scenarios.duplicate(self.scenario_id, "Summer alternative")
        duplicate = self.scenarios.get(duplicate_id)
        assumption = self.scenarios.adjustments(duplicate_id)[0]

        self.assertEqual(duplicate["account_id"], self.account)
        self.assertEqual(duplicate["horizon_months"], 3)
        self.assertEqual(assumption["name"], "Annual trip")
        self.assertEqual(assumption["amount_minor"], 75_000)
        self.assertEqual(assumption["notes"], "Summer travel")

    def test_projection_csv_contains_monthly_baseline_and_scenario_values(self):
        self.scenarios.add_adjustment(
            self.scenario_id, name="Side income", kind="income", cadence="monthly",
            amount_minor=12_345, start_month=1, end_month=2,
        )
        path = Path(self.temp_dir.name) / "projection.csv"

        row_count = self.scenarios.export_csv(self.scenario_id, path)

        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(row_count, 3)
        self.assertEqual(rows[0]["scenario"], "Stay the course")
        self.assertEqual(rows[0]["currency"], "USD")
        self.assertEqual(rows[0]["planned_income"], "123.45")
        self.assertEqual(rows[0]["below_zero"], "False")

    def test_schema_v5_upgrades_to_six_additively(self):
        with self.db.transaction() as connection:
            connection.execute("DROP TABLE scenario_adjustments")
            connection.execute("DROP TABLE financial_scenarios")
            connection.execute("UPDATE schema_meta SET value = '5' WHERE key = 'version'")
        self.db.initialize()
        version = self.db.fetch_one(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        )["value"]
        self.assertEqual(version, str(SCHEMA_VERSION))
        tables = {
            row["name"] for row in self.db.fetch_all(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertIn("financial_scenarios", tables)
        self.assertIn("scenario_adjustments", tables)


if __name__ == "__main__":
    unittest.main()