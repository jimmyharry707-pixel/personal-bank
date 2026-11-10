import tempfile
import unittest
from pathlib import Path

from personalbank.advanced import DebtPayoffStrategyService, DebtService
from personalbank.db import Database
from personalbank.services import FinanceService


class DebtPayoffStrategyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "strategies.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.checking = self.finance.create_account(
            "Checking", "checking", opening_balance_minor=2_000_000
        )
        self.debt_service = DebtService(self.finance)
        self.debts = DebtPayoffStrategyService(self.finance)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_debts(self):
        snowball_target = self.debt_service.create_plan(
            name="Small card", creditor="Card A", principal_minor=100_000,
            apr_basis_points=0, minimum_payment_minor=10_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        avalanche_target = self.debt_service.create_plan(
            name="Large APR loan", creditor="Lender B", principal_minor=250_000,
            apr_basis_points=2_400, minimum_payment_minor=10_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        return snowball_target, avalanche_target

    def test_strategies_pay_off_all_debts_and_avalanche_saves_interest(self):
        self.create_debts()

        result = self.debts.compare(extra_monthly_minor=10_000)
        strategies = {item["strategy"]: item for item in result["strategies"]}

        self.assertEqual(set(strategies), {"minimum", "snowball", "avalanche"})
        for strategy in strategies.values():
            self.assertEqual(strategy["ending_balance_minor"], 0)
            self.assertGreater(strategy["months"], 0)
            self.assertEqual(len(strategy["monthly"]), strategy["months"])
            self.assertTrue(all(debt["payoff_month"] for debt in strategy["debts"]))
        self.assertLess(
            strategies["avalanche"]["total_interest_minor"],
            strategies["snowball"]["total_interest_minor"],
        )
        self.assertGreater(strategies["snowball"]["interest_saved_minor"], 0)
        self.assertGreater(strategies["avalanche"]["interest_saved_minor"], 0)

    def test_preview_does_not_change_ledger_or_debt_records(self):
        self.create_debts()
        initial_balance = self.finance.account_balance(self.checking)

        self.debts.compare(extra_monthly_minor=5_000)

        self.assertEqual(self.finance.account_balance(self.checking), initial_balance)
        self.assertEqual(self.finance.list_transactions(), [])
        payments = self.db.fetch_one("SELECT COUNT(*) AS count FROM debt_payments")
        self.assertEqual(payments["count"], 0)

    def test_invalid_extra_payment_and_empty_debt_list_are_rejected(self):
        with self.assertRaises(ValueError):
            self.debts.compare(extra_monthly_minor=-1)
        with self.assertRaises(ValueError):
            self.debts.compare()

    def test_mixed_currency_debts_are_rejected(self):
        other_account = self.finance.create_account("Euro Checking", "checking", currency="EUR")
        self.debt_service.create_plan(
            name="USD debt", creditor="A", principal_minor=50_000,
            apr_basis_points=0, minimum_payment_minor=5_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        self.debt_service.create_plan(
            name="EUR debt", creditor="B", principal_minor=50_000,
            apr_basis_points=0, minimum_payment_minor=5_000,
            payment_account_id=other_account, due_day=15, start_date="2026-01-01",
        )

        with self.assertRaisesRegex(ValueError, "same currency"):
            self.debts.compare()


if __name__ == "__main__":
    unittest.main()