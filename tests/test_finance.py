import tempfile
import unittest
from pathlib import Path

from personalbank.db import Database
from personalbank.domain import to_minor_units
from personalbank.services import FinanceService


class FinanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.checking = self.finance.create_account("Main checking", "checking", opening_balance_minor=100000)
        self.savings = self.finance.create_account("Savings", "savings", opening_balance_minor=50000)
        self.income_category = self.finance.categories.list(kind="income")[0]["id"]
        self.expense_category = self.finance.categories.list(kind="expense")[0]["id"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_money_conversion_uses_minor_units(self):
        self.assertEqual(to_minor_units("12.34"), 1234)
        self.assertEqual(to_minor_units("0.105"), 11)

    def test_income_increases_balance(self):
        self.finance.create_income(self.checking, 25000, "2026-01-02", self.income_category)
        self.assertEqual(self.finance.account_balance(self.checking), 125000)

    def test_expense_decreases_balance(self):
        self.finance.create_expense(self.checking, 2500, "2026-01-02", self.expense_category)
        self.assertEqual(self.finance.account_balance(self.checking), 97500)

    def test_transfer_moves_balance_between_accounts(self):
        self.finance.create_transfer(self.checking, self.savings, 10000, "2026-01-03")
        self.assertEqual(self.finance.account_balance(self.checking), 90000)
        self.assertEqual(self.finance.account_balance(self.savings), 60000)

    def test_transfer_rejects_same_account(self):
        with self.assertRaises(ValueError):
            self.finance.create_transfer(self.checking, self.checking, 1000, "2026-01-03")

    def test_adjustment_can_increase_or_decrease_balance(self):
        self.finance.create_adjustment(self.checking, 5000, "2026-01-03")
        self.assertEqual(self.finance.account_balance(self.checking), 105000)
        self.finance.create_adjustment(self.checking, -2500, "2026-01-04")
        self.assertEqual(self.finance.account_balance(self.checking), 102500)

    def test_archived_category_cannot_be_used_for_new_expense(self):
        self.finance.categories.archive(self.expense_category)
        with self.assertRaises(ValueError):
            self.finance.create_expense(
                self.checking, 1000, "2026-01-03", self.expense_category
            )

    def test_category_color_must_be_valid_hex(self):
        with self.assertRaises(ValueError):
            self.finance.create_category("Bad color", "expense", "#gggggg")

    def test_invalid_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            self.finance.create_expense(self.checking, 0, "2026-01-03")

    def test_invalid_date_is_rejected(self):
        with self.assertRaises(ValueError):
            self.finance.create_expense(self.checking, 1000, "not-a-date")

    def test_budget_tracks_expense_spending(self):
        self.finance.set_budget(self.expense_category, "2026-01", 20000)
        self.finance.create_expense(self.checking, 5000, "2026-01-10", self.expense_category)
        status = self.finance.budget_status("2026-01")[0]
        self.assertEqual(status["spent_minor"], 5000)
        self.assertEqual(status["remaining_minor"], 15000)
        self.assertEqual(status["percent"], 25.0)

    def test_budget_alerts_apply_thresholds_and_handle_zero_limits(self):
        near_category = self.expense_category
        over_category = self.finance.create_category("Travel", "expense", "#208060")
        critical_category = self.finance.create_category("Repairs", "expense", "#c06040")
        zero_category = self.finance.create_category("Gifts", "expense", "#7050a0")
        below_category = self.finance.create_category("Dining test", "expense", "#3070a0")
        budgets = {
            near_category: (10_000, 8_000),
            over_category: (10_000, 10_500),
            critical_category: (10_000, 12_500),
            zero_category: (0, 500),
            below_category: (10_000, 7_900),
        }
        for category_id, (limit_minor, spent_minor) in budgets.items():
            self.finance.set_budget(category_id, "2026-01", limit_minor)
            if spent_minor:
                self.finance.create_expense(
                    self.checking, spent_minor, "2026-01-10", category_id
                )

        alerts = self.finance.budget_alerts(
            "2026-01", warning_percent=80, critical_percent=120
        )
        by_category = {alert["category_id"]: alert for alert in alerts}

        self.assertEqual(set(by_category), {near_category, over_category, critical_category, zero_category})
        self.assertEqual(by_category[near_category]["severity"], "warning")
        self.assertEqual(by_category[over_category]["severity"], "over")
        self.assertEqual(by_category[critical_category]["severity"], "critical")
        self.assertEqual(by_category[zero_category]["status"], "Over budget")
        self.assertIsNone(by_category[zero_category]["percent"])

    def test_budget_alerts_reject_invalid_thresholds(self):
        with self.assertRaises(ValueError):
            self.finance.budget_alerts("2026-01", warning_percent=100)
        with self.assertRaises(ValueError):
            self.finance.budget_alerts("2026-01", critical_percent=99)

    def test_bill_payment_creates_expense_and_advances_due_date(self):
        bill_id = self.finance.create_bill(
            name="Internet", amount_minor=6500, due_day=15,
            category_id=self.expense_category, account_id=self.checking,
            frequency="monthly", auto_post=False, next_due_date="2026-01-15",
        )
        self.finance.pay_bill(bill_id, "2026-01-15")
        self.assertEqual(self.finance.account_balance(self.checking), 93500)
        bill = self.db.fetch_one("SELECT next_due_date FROM bills WHERE id = ?", (bill_id,))
        self.assertEqual(bill["next_due_date"], "2026-02-15")

    def test_bill_payment_rejects_archived_account_without_posting_transaction(self):
        bill_id = self.finance.create_bill(
            name="Internet", amount_minor=6500, due_day=15,
            category_id=self.expense_category, account_id=self.checking,
            frequency="monthly", auto_post=False, next_due_date="2026-01-15",
        )
        self.finance.archive_account(self.checking)
        with self.assertRaises(ValueError):
            self.finance.pay_bill(bill_id, "2026-01-15")
        transactions = self.finance.list_transactions()
        self.assertEqual(transactions, [])
        bill = self.db.fetch_one("SELECT next_due_date FROM bills WHERE id = ?", (bill_id,))
        self.assertEqual(bill["next_due_date"], "2026-01-15")

    def test_goal_contribution_updates_progress(self):
        goal_id = self.finance.create_goal("Emergency fund", 100000, "2026-12-31")
        self.finance.contribute_to_goal(goal_id, 25000)
        goal = self.db.fetch_one("SELECT current_minor FROM savings_goals WHERE id = ?", (goal_id,))
        self.assertEqual(goal["current_minor"], 25000)

    def test_dashboard_summary(self):
        self.finance.create_income(self.checking, 50000, "2026-01-05", self.income_category)
        self.finance.create_expense(self.checking, 10000, "2026-01-06", self.expense_category)
        summary = self.finance.dashboard_summary("2026-01")
        self.assertEqual(summary["income"], 50000)
        self.assertEqual(summary["expenses"], 10000)
        self.assertEqual(summary["net"], 40000)


if __name__ == "__main__":
    unittest.main()
