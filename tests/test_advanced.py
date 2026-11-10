import tempfile
import unittest
from pathlib import Path

from personalbank.advanced import (
    CashFlowForecastService,
    DebtService,
    InvestmentService,
    MaintenanceService,
    NetWorthService,
    ReconciliationService,
    RecurringTransactionService,
    advance_date,
)
from personalbank.db import Database
from personalbank.services import FinanceService


class AdvancedFinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "advanced.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.checking = self.finance.create_account(
            "Checking", "checking", opening_balance_minor=1_000_000
        )
        self.savings = self.finance.create_account(
            "Savings", "savings", opening_balance_minor=250_000
        )
        self.brokerage = self.finance.create_account(
            "Brokerage", "investment", opening_balance_minor=500_000
        )
        self.expense_category = self.finance.categories.list(kind="expense")[0]["id"]
        self.income_category = self.finance.categories.list(kind="income")[0]["id"]
        self.recurring = RecurringTransactionService(self.finance)
        self.reconciliation = ReconciliationService(self.finance)
        self.debts = DebtService(self.finance)
        self.investments = InvestmentService(self.finance)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_monthly_recurrence_preserves_end_of_month_anchor(self):
        self.assertEqual(advance_date("2026-01-31", "monthly", 31), "2026-02-28")
        self.assertEqual(advance_date("2026-02-28", "monthly", 31), "2026-03-31")
        self.assertEqual(advance_date("2024-01-31", "monthly", 31), "2024-02-29")

    def test_recurring_post_creates_transaction_and_advances_date(self):
        recurring_id = self.recurring.create(
            name="Rent", kind="expense", account_id=self.checking,
            category_id=self.expense_category, amount_minor=100_000,
            frequency="monthly", next_due_date="2026-01-31",
        )
        transaction_id = self.recurring.post(recurring_id, "2026-01-31")
        self.assertGreater(transaction_id, 0)
        self.assertEqual(self.finance.account_balance(self.checking), 900_000)
        row = self.recurring.get(recurring_id)
        self.assertEqual(row["next_due_date"], "2026-02-28")
        self.assertEqual(row["last_posted_on"], "2026-01-31")

    def test_recurring_item_cannot_be_posted_before_due_date(self):
        recurring_id = self.recurring.create(
            name="Salary", kind="income", account_id=self.checking,
            category_id=self.income_category, amount_minor=200_000,
            frequency="monthly", next_due_date="2026-01-31",
        )
        with self.assertRaises(ValueError):
            self.recurring.post(recurring_id, "2026-01-30")
        self.assertEqual(self.finance.account_balance(self.checking), 1_000_000)

    def test_recurring_end_date_archives_after_final_occurrence(self):
        recurring_id = self.recurring.create(
            name="Annual fee", kind="expense", account_id=self.checking,
            category_id=self.expense_category, amount_minor=1_000,
            frequency="yearly", next_due_date="2026-01-01", end_date="2026-01-01",
        )
        self.recurring.post(recurring_id, "2026-01-01")
        self.assertEqual(self.recurring.get(recurring_id)["active"], 0)

    def test_recurring_skip_advances_without_posting(self):
        recurring_id = self.recurring.create(
            name="Subscription", kind="expense", account_id=self.checking,
            category_id=self.expense_category, amount_minor=2_000,
            frequency="weekly", next_due_date="2026-01-01",
        )
        self.assertEqual(self.recurring.skip(recurring_id), "2026-01-08")
        self.assertEqual(self.finance.account_balance(self.checking), 1_000_000)

    def test_recurring_post_rejects_archived_account(self):
        recurring_id = self.recurring.create(
            name="Rent", kind="expense", account_id=self.checking,
            category_id=self.expense_category, amount_minor=10_000,
            frequency="monthly", next_due_date="2026-01-01",
        )
        self.finance.archive_account(self.checking)
        with self.assertRaises(ValueError):
            self.recurring.post(recurring_id, "2026-01-01")

    def test_recurring_category_type_is_validated(self):
        with self.assertRaises(ValueError):
            self.recurring.create(
                name="Wrong category", kind="income", account_id=self.checking,
                category_id=self.expense_category, amount_minor=1_000,
                frequency="monthly", next_due_date="2026-01-01",
            )

    def test_reconciliation_balances_and_closes(self):
        self.finance.create_expense(
            self.checking, 10_000, "2026-01-10", self.expense_category, payee="Store"
        )
        self.finance.create_income(
            self.checking, 25_000, "2026-01-15", self.income_category, payee="Employer"
        )
        session_id = self.reconciliation.start_session(
            self.checking, "2026-01-31", 1_015_000
        )
        items = self.reconciliation.items(session_id)
        self.assertEqual(len(items), 2)
        for item in items:
            self.reconciliation.set_cleared(session_id, item["id"], True)
        summary = self.reconciliation.summary(session_id)
        self.assertEqual(summary["difference_minor"], 0)
        self.reconciliation.close_session(session_id)
        history = self.reconciliation.history(self.checking)
        self.assertEqual(history[0]["status"], "closed")

    def test_reconciliation_cannot_close_with_difference(self):
        self.finance.create_expense(
            self.checking, 10_000, "2026-01-10", self.expense_category
        )
        session_id = self.reconciliation.start_session(
            self.checking, "2026-01-31", 990_000
        )
        with self.assertRaises(ValueError):
            self.reconciliation.close_session(session_id)
        self.assertEqual(self.reconciliation.open_session(self.checking)["id"], session_id)

    def test_reconciliation_transfer_effect_is_account_specific(self):
        self.finance.create_transfer(self.checking, self.savings, 30_000, "2026-01-10")
        source_session = self.reconciliation.start_session(
            self.checking, "2026-01-31", 970_000
        )
        source_item = self.reconciliation.items(source_session)[0]
        self.assertEqual(source_item["signed_amount_minor"], -30_000)
        self.reconciliation.discard_open_session(source_session)
        target_session = self.reconciliation.start_session(
            self.savings, "2026-01-31", 280_000
        )
        target_item = self.reconciliation.items(target_session)[0]
        self.assertEqual(target_item["signed_amount_minor"], 30_000)

    def test_reconciliation_requires_only_one_open_session_per_account(self):
        self.reconciliation.start_session(self.checking, "2026-01-31", 1_000_000)
        with self.assertRaises(ValueError):
            self.reconciliation.start_session(self.checking, "2026-02-28", 1_000_000)

    def test_transaction_in_open_reconciliation_cannot_be_deleted(self):
        transaction_id = self.finance.create_expense(
            self.checking, 10_000, "2026-01-10", self.expense_category
        )
        self.reconciliation.start_session(self.checking, "2026-01-31", 990_000)
        with self.assertRaises(ValueError):
            self.finance.delete_transaction(transaction_id)

    def test_reconciled_transactions_are_not_repeated(self):
        self.finance.create_expense(
            self.checking, 10_000, "2026-01-10", self.expense_category
        )
        first = self.reconciliation.start_session(self.checking, "2026-01-31", 990_000)
        for item in self.reconciliation.items(first):
            self.reconciliation.set_cleared(first, item["id"], True)
        self.reconciliation.close_session(first)
        second = self.reconciliation.start_session(self.checking, "2026-02-28", 990_000)
        self.assertEqual(self.reconciliation.items(second), [])

    def test_debt_monthly_interest_uses_basis_points(self):
        self.assertEqual(DebtService.monthly_interest(500_000, 1_200), 5_000)
        self.assertEqual(DebtService.monthly_interest(100_000, 0), 0)

    def test_debt_plan_rejects_payment_below_interest(self):
        with self.assertRaises(ValueError):
            self.debts.create_plan(
                name="High APR", creditor="Card issuer", principal_minor=500_000,
                apr_basis_points=2_400, minimum_payment_minor=5_000,
                payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
            )

    def test_debt_schedule_reaches_zero_balance(self):
        debt_id = self.debts.create_plan(
            name="Personal loan", creditor="Lender", principal_minor=500_000,
            apr_basis_points=1_200, minimum_payment_minor=50_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        schedule = self.debts.schedule(debt_id)
        self.assertGreater(len(schedule), 0)
        self.assertEqual(schedule[-1]["closing_minor"], 0)
        self.assertLess(schedule[-1]["payment_minor"], 50_000)

    def test_debt_payment_reduces_principal_and_posts_expense(self):
        debt_id = self.debts.create_plan(
            name="Personal loan", creditor="Lender", principal_minor=500_000,
            apr_basis_points=1_200, minimum_payment_minor=50_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        result = self.debts.record_payment(debt_id, 50_000, "2026-02-15")
        self.assertEqual(result["interest_minor"], 5_000)
        self.assertEqual(result["principal_minor"], 45_000)
        self.assertEqual(result["remaining_minor"], 455_000)
        self.assertEqual(self.finance.account_balance(self.checking), 950_000)

    def test_debt_interest_accrues_by_elapsed_months_not_each_click(self):
        debt_id = self.debts.create_plan(
            name="Personal loan", creditor="Lender", principal_minor=500_000,
            apr_basis_points=1_200, minimum_payment_minor=50_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        first = self.debts.record_payment(debt_id, 50_000, "2026-02-15")
        self.assertEqual(first["interest_minor"], 5_000)
        same_month = self.debts.record_payment(debt_id, 10_000, "2026-02-28")
        self.assertEqual(same_month["interest_minor"], 0)
        later = self.debts.record_payment(debt_id, 50_000, "2026-04-15")
        self.assertGreater(later["interest_minor"], 8_000)

    def test_debt_schedule_after_payment_starts_after_last_payment(self):
        debt_id = self.debts.create_plan(
            name="Personal loan", creditor="Lender", principal_minor=500_000,
            apr_basis_points=1_200, minimum_payment_minor=50_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        self.debts.record_payment(debt_id, 50_000, "2026-02-15")
        schedule = self.debts.schedule(debt_id)
        self.assertEqual(schedule[0]["date"], "2026-03-15")
        self.assertEqual(schedule[0]["opening_minor"], 455_000)

    def test_debt_payment_date_cannot_move_backwards_within_same_month(self):
        debt_id = self.debts.create_plan(
            name="Personal loan", creditor="Lender", principal_minor=500_000,
            apr_basis_points=1_200, minimum_payment_minor=50_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        self.debts.record_payment(debt_id, 50_000, "2026-02-20")
        with self.assertRaises(ValueError):
            self.debts.record_payment(debt_id, 10_000, "2026-02-19")

    def test_debt_payment_cannot_be_less_than_interest(self):
        debt_id = self.debts.create_plan(
            name="Personal loan", creditor="Lender", principal_minor=500_000,
            apr_basis_points=1_200, minimum_payment_minor=50_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        with self.assertRaises(ValueError):
            self.debts.record_payment(debt_id, 4_999, "2026-02-15")
        self.assertEqual(self.finance.account_balance(self.checking), 1_000_000)

    def test_debt_overpayment_is_capped_at_payoff_amount(self):
        debt_id = self.debts.create_plan(
            name="Small loan", creditor="Lender", principal_minor=10_000,
            apr_basis_points=0, minimum_payment_minor=1_000,
            payment_account_id=self.checking, due_day=15, start_date="2026-01-01",
        )
        result = self.debts.record_payment(debt_id, 100_000, "2026-02-15")
        self.assertEqual(result["payment_minor"], 10_000)
        self.assertEqual(result["remaining_minor"], 0)
        self.assertEqual(self.debts.get_plan(debt_id)["active"], 0)

    def test_investment_buy_updates_holdings_and_cash_ledger(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        result = self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="buy", quantity_micros=2_000_000, price_minor=10_000,
            commission_minor=100, trade_date="2026-01-10",
        )
        self.assertEqual(result["cash_amount_minor"], 20_100)
        self.assertEqual(self.finance.account_balance(self.brokerage), 479_900)
        holding = self.investments.holdings()[0]
        self.assertEqual(holding["quantity_micros"], 2_000_000)
        self.assertEqual(holding["cost_basis_minor"], 20_100)

    def test_investment_sale_calculates_weighted_average_realized_gain(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="buy", quantity_micros=2_000_000, price_minor=10_000,
            commission_minor=100, trade_date="2026-01-10",
        )
        self.investments.update_price(security_id, 12_000)
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="sell", quantity_micros=500_000, price_minor=13_000,
            commission_minor=50, trade_date="2026-02-10",
        )
        holding = self.investments.holdings()[0]
        self.assertEqual(holding["quantity_micros"], 1_500_000)
        self.assertEqual(holding["realized_minor"], 1_425)
        self.assertEqual(holding["unrealized_minor"], 2_925)

    def test_realized_gain_remains_in_summary_after_position_is_fully_sold(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="buy", quantity_micros=1_000_000, price_minor=10_000,
            trade_date="2026-01-10",
        )
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="sell", quantity_micros=1_000_000, price_minor=12_000,
            trade_date="2026-02-10",
        )
        self.assertEqual(self.investments.holdings(), [])
        self.assertEqual(self.investments.summary()["realized_minor"], 2_000)

    def test_investment_trades_are_excluded_from_household_cashflow(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="buy", quantity_micros=1_000_000, price_minor=10_000,
            trade_date="2026-01-10",
        )
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="sell", quantity_micros=1_000_000, price_minor=12_000,
            trade_date="2026-01-11",
        )
        summary = self.finance.dashboard_summary("2026-01")
        self.assertEqual(summary["income"], 0)
        self.assertEqual(summary["expenses"], 0)
        self.assertEqual(self.finance.monthly_cashflow(2026)[0]["income"], 0)
        self.assertEqual(self.finance.monthly_cashflow(2026)[0]["expenses"], 0)

    def test_investment_sale_cannot_exceed_shares_held(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        with self.assertRaises(ValueError):
            self.investments.record_trade(
                investment_account_id=self.brokerage, security_id=security_id,
                side="sell", quantity_micros=1_000_000, price_minor=10_000,
                trade_date="2026-01-10",
            )

    def test_investment_buy_rejects_insufficient_account_cash(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        with self.assertRaises(ValueError):
            self.investments.record_trade(
                investment_account_id=self.brokerage, security_id=security_id,
                side="buy", quantity_micros=100_000_000, price_minor=10_000,
                trade_date="2026-01-10",
            )
        self.assertEqual(self.finance.account_balance(self.brokerage), 500_000)

    def test_investment_account_and_security_currency_must_match(self):
        security_id = self.investments.create_security("EURO", "Euro security", currency="EUR")
        with self.assertRaises(ValueError):
            self.investments.record_trade(
                investment_account_id=self.brokerage, security_id=security_id,
                side="buy", quantity_micros=1_000_000, price_minor=10_000,
                trade_date="2026-01-10",
            )

    def test_net_worth_includes_account_balances_investments_and_debt(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="buy", quantity_micros=1_000_000, price_minor=10_000,
            trade_date="2026-01-10",
        )
        self.investments.update_price(security_id, 12_000)
        debt_id = self.debts.create_plan(
            name="Loan", creditor="Lender", principal_minor=100_000,
            apr_basis_points=0, minimum_payment_minor=10_000,
            payment_account_id=self.checking, due_day=1, start_date="2026-01-01",
        )
        position = NetWorthService(self.finance, self.investments).current_position()
        self.assertEqual(position["assets_minor"], 1_752_000)
        self.assertEqual(position["liabilities_minor"], 100_000)
        self.assertEqual(position["net_worth_minor"], 1_652_000)

    def test_archived_debt_can_still_receive_a_payment(self):
        debt_id = self.debts.create_plan(
            name="Archived loan", creditor="Lender", principal_minor=10_000,
            apr_basis_points=0, minimum_payment_minor=1_000,
            payment_account_id=self.checking, due_day=1, start_date="2026-01-01",
        )
        self.debts.archive(debt_id)
        result = self.debts.record_payment(debt_id, 10_000, "2026-02-01")
        self.assertEqual(result["remaining_minor"], 0)
        self.assertEqual(self.debts.get_plan(debt_id)["active"], 0)

    def test_archived_unpaid_debt_remains_a_net_worth_liability(self):
        debt_id = self.debts.create_plan(
            name="Loan", creditor="Lender", principal_minor=100_000,
            apr_basis_points=0, minimum_payment_minor=10_000,
            payment_account_id=self.checking, due_day=1, start_date="2026-01-01",
        )
        self.debts.archive(debt_id)
        position = NetWorthService(self.finance, self.investments).current_position()
        self.assertEqual(position["debt_total_minor"], 100_000)
        self.assertEqual(position["liabilities_minor"], 100_000)

    def test_archived_account_balance_remains_in_net_worth(self):
        self.finance.archive_account(self.savings)
        position = NetWorthService(self.finance, self.investments).current_position()
        self.assertEqual(position["assets_minor"], 1_750_000)
        archived = next(row for row in position["accounts"] if row["id"] == self.savings)
        self.assertEqual(archived["is_active"], 0)
        self.assertEqual(archived["balance_minor"], 250_000)

    def test_net_worth_snapshot_upserts_by_date(self):
        net_worth = NetWorthService(self.finance, self.investments)
        first_id = net_worth.save_snapshot("2026-01-31", "First capture")
        second_id = net_worth.save_snapshot("2026-01-31", "Updated capture")
        self.assertEqual(first_id, second_id)
        snapshots = net_worth.snapshots()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["notes"], "Updated capture")

    def test_cash_flow_forecast_projects_recurring_income_and_bills(self):
        self.recurring.create(
            name="Salary", kind="income", account_id=self.checking,
            category_id=self.income_category, amount_minor=200_000,
            frequency="monthly", next_due_date="2026-01-05",
        )
        self.finance.create_bill(
            name="Internet", amount_minor=10_000, due_day=10,
            category_id=self.expense_category, account_id=self.checking,
            frequency="monthly", auto_post=False, next_due_date="2026-01-10",
        )
        forecast = CashFlowForecastService(self.finance).project(40, "2026-01-01")
        self.assertEqual(forecast["projected_income_minor"], 400_000)
        self.assertEqual(forecast["projected_expenses_minor"], 20_000)
        self.assertEqual(forecast["projected_net_minor"], 380_000)
        self.assertEqual(len(forecast["events"]), 4)
        self.assertEqual(self.finance.account_balance(self.checking), 1_000_000)
        checking_projection = next(
            row for row in forecast["ending_balances"] if row["account_id"] == self.checking
        )
        self.assertEqual(checking_projection["balance_minor"], 1_380_000)

    def test_cash_flow_forecast_marks_overdue_occurrences(self):
        self.recurring.create(
            name="Old subscription", kind="expense", account_id=self.checking,
            category_id=self.expense_category, amount_minor=1_000,
            frequency="monthly", next_due_date="2025-12-01",
        )
        forecast = CashFlowForecastService(self.finance).project(7, "2026-01-01")
        self.assertTrue(forecast["events"][0]["overdue"])
        self.assertEqual(forecast["events"][0]["date"], "2026-01-01")
        self.assertEqual(forecast["events"][0]["due_date"], "2025-12-01")

    def test_transaction_update_changes_account_ledger(self):
        transaction_id = self.finance.create_expense(
            self.checking, 10_000, "2026-01-10", self.expense_category
        )
        self.finance.update_transaction(
            transaction_id, account_id=self.savings, transfer_account_id=None,
            category_id=self.expense_category, kind="expense", amount_minor=20_000,
            occurred_on="2026-01-11", payee="Market", description="Updated",
        )
        self.assertEqual(self.finance.account_balance(self.checking), 1_000_000)
        self.assertEqual(self.finance.account_balance(self.savings), 230_000)

    def test_reconciled_transaction_cannot_be_edited_or_deleted(self):
        transaction_id = self.finance.create_expense(
            self.checking, 10_000, "2026-01-10", self.expense_category
        )
        session_id = self.reconciliation.start_session(self.checking, "2026-01-31", 990_000)
        self.reconciliation.set_cleared(session_id, transaction_id, True)
        self.reconciliation.close_session(session_id)
        with self.assertRaises(ValueError):
            self.finance.delete_transaction(transaction_id)
        with self.assertRaises(ValueError):
            self.finance.update_transaction(
                transaction_id, account_id=self.checking, transfer_account_id=None,
                category_id=self.expense_category, kind="expense", amount_minor=12_000,
                occurred_on="2026-01-10",
            )

    def test_investment_linked_transaction_cannot_be_deleted(self):
        security_id = self.investments.create_security("ACME", "Acme Corporation")
        trade = self.investments.record_trade(
            investment_account_id=self.brokerage, security_id=security_id,
            side="buy", quantity_micros=1_000_000, price_minor=10_000,
            trade_date="2026-01-10",
        )
        with self.assertRaises(ValueError):
            self.finance.delete_transaction(trade["transaction_id"])

    def test_database_health_check_reports_integrity_and_foreign_keys(self):
        report = MaintenanceService(self.db).integrity_report()
        self.assertEqual(report["integrity"], ["ok"])
        self.assertEqual(report["foreign_key_issues"], [])
        self.assertIn("investment_trades", report["table_counts"])


if __name__ == "__main__":
    unittest.main()
