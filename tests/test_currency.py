import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from personalbank.advanced import DebtService, InvestmentService
from personalbank.currency import CurrencyValuationService
from personalbank.db import Database, SCHEMA_VERSION
from personalbank.services import FinanceService


class CurrencyValuationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "currency.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.usd_account = self.finance.create_account(
            "USD Checking", "checking", currency="USD", opening_balance_minor=50_000
        )
        self.eur_account = self.finance.create_account(
            "Euro Savings", "savings", currency="EUR", opening_balance_minor=100_000
        )
        self.investments = InvestmentService(self.finance)
        self.currency = CurrencyValuationService(self.finance, self.investments)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rates_support_direct_inverse_and_rounding(self):
        self.currency.set_rate("eur", "usd", "1.1")
        self.assertEqual(self.currency.rate("EUR", "USD"), Decimal("1.1"))
        self.assertEqual(self.currency.convert_minor(100_000, "EUR", "USD"), 110_000)
        self.assertEqual(self.currency.convert_minor(110_000, "USD", "EUR"), 100_000)
        self.assertEqual(self.currency.convert_minor(101, "EUR", "USD"), 111)
        self.assertEqual(self.currency.rate("USD", "USD"), Decimal(1))
        self.assertEqual(self.currency.convert_minor(123, "USD", "USD"), 123)

    def test_rates_update_existing_pair_and_reject_invalid_values(self):
        self.currency.set_rate("EUR", "USD", "1.1")
        self.currency.set_rate("EUR", "USD", "1.2")
        self.assertEqual(len(self.currency.rates("USD")), 1)
        self.assertEqual(self.currency.rate("EUR", "USD"), Decimal("1.2"))
        self.currency.delete_rate("EUR", "USD")
        self.assertIsNone(self.currency.rate("EUR", "USD"))
        actions = self.db.fetch_all(
            "SELECT action FROM audit_log WHERE entity = 'exchange_rate' ORDER BY id"
        )
        self.assertEqual([row["action"] for row in actions], ["set", "set", "delete"])
        for source, target, rate in [
            ("US", "USD", "1"),
            ("USD", "USD", "1"),
            ("EUR", "USD", "0"),
            ("EUR", "USD", "NaN"),
            ("EUR", "USD", "Infinity"),
        ]:
            with self.subTest(source=source, target=target, rate=rate):
                with self.assertRaises(ValueError):
                    self.currency.set_rate(source, target, rate)

    def test_valuation_converts_accounts_investments_and_debts(self):
        investment_account = self.finance.create_account(
            "Euro Brokerage", "investment", currency="EUR", opening_balance_minor=100_000
        )
        security_id = self.investments.create_security(
            "EURO", "Euro fund", currency="EUR"
        )
        self.investments.update_price(security_id, 10_000)
        self.investments.record_trade(
            investment_account_id=investment_account,
            security_id=security_id,
            side="buy",
            quantity_micros=2_000_000,
            price_minor=10_000,
            trade_date="2026-01-01",
        )
        debts = DebtService(self.finance)
        debts.create_plan(
            name="Card balance", creditor="Issuer", principal_minor=25_000,
            apr_basis_points=0, minimum_payment_minor=5_000,
            payment_account_id=self.usd_account, due_day=15, start_date="2026-01-01",
        )
        self.currency.set_rate("EUR", "USD", "1.1")

        report = self.currency.valuation("USD")

        self.assertTrue(report["complete"])
        self.assertEqual(report["assets_minor"], 270_000)
        self.assertEqual(report["liabilities_minor"], 25_000)
        self.assertEqual(report["net_worth_minor"], 245_000)
        investment = next(row for row in report["rows"] if row["source_type"] == "investment")
        self.assertEqual(investment["amount_minor"], 20_000)
        self.assertEqual(investment["base_minor"], 22_000)

    def test_missing_rates_are_reported_and_excluded_from_totals(self):
        report = self.currency.valuation("USD")
        self.assertFalse(report["complete"])
        self.assertEqual(report["missing_currencies"], ["EUR"])
        euro_rows = [row for row in report["rows"] if row["currency"] == "EUR"]
        self.assertTrue(euro_rows)
        self.assertTrue(all(row["base_minor"] is None for row in euro_rows))
        self.assertEqual(report["assets_minor"], 50_000)

    def test_schema_v4_database_adds_exchange_rates(self):
        with self.db.transaction() as connection:
            connection.execute("DROP TABLE exchange_rates")
            connection.execute("UPDATE schema_meta SET value = '4' WHERE key = 'version'")

        self.db.initialize()

        version = self.db.fetch_one(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        )["value"]
        table = self.db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_rates'"
        )
        self.assertEqual(version, str(SCHEMA_VERSION))
        self.assertIsNotNone(table)
        self.assertTrue(self.finance.accounts.get(self.eur_account))


if __name__ == "__main__":
    unittest.main()