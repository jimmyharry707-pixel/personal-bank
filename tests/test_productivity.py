import tempfile
import unittest
from pathlib import Path

from personalbank.advanced import RecurringTransactionService
from personalbank.db import Database
from personalbank.productivity import (
    CategorizationRuleService,
    FinanceCalendarService,
    SubscriptionService,
    TaxService,
)
from personalbank.services import FinanceService


class ProductivityFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "productivity.sqlite3")
        self.db.initialize()
        self.finance = FinanceService(self.db)
        self.checking = self.finance.create_account(
            "Checking", "checking", currency="USD", opening_balance_minor=500_000
        )
        self.expense_category = self.finance.categories.list(kind="expense")[0]["id"]
        self.income_category = self.finance.categories.list(kind="income")[0]["id"]
        self.recurring = RecurringTransactionService(self.finance)
        self.subscriptions = SubscriptionService(self.finance)
        self.calendar = FinanceCalendarService(self.finance)
        self.tax = TaxService(self.finance)
        self.rules = CategorizationRuleService(self.finance)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_subscription(self, **overrides):
        values = {
            "name": "Music Plus", "vendor": "Example Media", "amount_minor": 1299,
            "currency": "USD", "frequency": "monthly", "next_renewal_date": "2026-01-15",
            "category_id": self.expense_category, "account_id": self.checking,
            "trial_end_date": None, "cancel_by_date": "2026-01-14",
            "website_url": "https://example.test", "notes": "Family plan",
        }
        values.update(overrides)
        return self.subscriptions.create(**values)

    def test_subscription_monthly_and_annual_equivalents(self):
        self.assertEqual(SubscriptionService.monthly_equivalent(1200, "yearly"), 100)
        self.assertEqual(SubscriptionService.annual_equivalent(1000, "quarterly"), 4000)
        self.assertEqual(SubscriptionService.monthly_equivalent(1000, "weekly"), 4333)

    def test_subscription_summary_counts_active_services(self):
        self.create_subscription()
        self.create_subscription(name="Cloud storage", amount_minor=600, frequency="yearly")
        summary = self.subscriptions.summary()
        self.assertEqual(summary["active_count"], 2)
        self.assertEqual(summary["monthly_equivalent_minor"], 1299 + 50)

    def test_subscription_renewal_posts_expense_and_advances_date(self):
        subscription_id = self.create_subscription()
        transaction_id = self.subscriptions.record_renewal(subscription_id, "2026-01-15")
        self.assertGreater(transaction_id, 0)
        self.assertEqual(self.finance.account_balance(self.checking), 498_701)
        row = self.subscriptions.get(subscription_id)
        self.assertEqual(row["next_renewal_date"], "2026-02-15")
        self.assertEqual(row["last_renewed_on"], "2026-01-15")

    def test_subscription_cannot_be_paid_before_due_date(self):
        subscription_id = self.create_subscription()
        with self.assertRaises(ValueError):
            self.subscriptions.record_renewal(subscription_id, "2026-01-14")
        self.assertEqual(self.finance.account_balance(self.checking), 500_000)

    def test_subscription_requires_matching_currency_for_payment_account(self):
        with self.assertRaises(ValueError):
            self.create_subscription(currency="EUR")

    def test_subscription_summary_does_not_add_different_currencies(self):
        self.create_subscription()
        self.create_subscription(
            name="International service", currency="EUR", account_id=None,
            amount_minor=1000, frequency="monthly", cancel_by_date=None,
        )
        summary = self.subscriptions.summary()
        self.assertTrue(summary["currency_mixed"])
        self.assertEqual(summary["currencies"], ["EUR", "USD"])
        self.assertEqual(summary["monthly_equivalent_minor"], 0)

    def test_subscription_price_change_is_historized(self):
        subscription_id = self.create_subscription()
        self.subscriptions.update_price(subscription_id, 1599, "2026-02-01", "Price increase")
        history = self.subscriptions.price_history(subscription_id)
        self.assertEqual(len(history), 2)
        changed = next(row for row in history if row["new_amount_minor"] == 1599)
        self.assertEqual(changed["old_amount_minor"], 1299)
        self.assertEqual(changed["notes"], "Price increase")

    def test_subscription_archive_removes_it_from_active_summary(self):
        subscription_id = self.create_subscription()
        self.subscriptions.archive(subscription_id)
        self.assertEqual(self.subscriptions.summary()["active_count"], 0)

    def test_finance_calendar_collects_month_occurrences_without_posting(self):
        self.recurring.create(
            name="Rent", kind="expense", account_id=self.checking,
            category_id=self.expense_category, amount_minor=100_000,
            frequency="monthly", next_due_date="2026-01-31",
            end_date="2026-03-31",
        )
        self.finance.create_bill(
            name="Internet", amount_minor=6_500, due_day=10,
            category_id=self.expense_category, account_id=self.checking,
            frequency="monthly", auto_post=False, next_due_date="2026-03-10",
        )
        self.create_subscription(
            next_renewal_date="2026-02-28", cancel_by_date="2026-02-27",
        )

        events = self.calendar.events("2026-03")
        occurrences = {
            (event["source_type"], event["due_date"]): event for event in events
        }

        self.assertEqual(len(events), 6)
        self.assertEqual(
            set(occurrences),
            {
                ("recurring", "2026-01-31"),
                ("recurring", "2026-02-28"),
                ("recurring", "2026-03-31"),
                ("bill", "2026-03-10"),
                ("subscription", "2026-02-28"),
                ("subscription", "2026-03-28"),
            },
        )
        self.assertTrue(occurrences[("recurring", "2026-01-31")]["overdue"])
        self.assertEqual(occurrences[("recurring", "2026-01-31")]["date"], "2026-03-01")
        self.assertEqual(occurrences[("bill", "2026-03-10")]["currency"], "USD")
        self.assertEqual(self.finance.list_transactions(), [])
        self.assertEqual(self.finance.account_balance(self.checking), 500_000)

    def test_subscription_validates_cancel_deadline(self):
        with self.assertRaises(ValueError):
            self.create_subscription(cancel_by_date="2026-01-16")

    def test_tax_record_calculates_partial_deduction(self):
        transaction_id = self.finance.create_expense(
            self.checking, 10000, "2026-04-02", self.expense_category, payee="Office store"
        )
        self.tax.tag_transaction(transaction_id, "deductible_expense", "Office supplies", 5000)
        summary = self.tax.summary(2026)
        self.assertEqual(summary["deductible_expenses_minor"], 5000)
        self.assertEqual(summary["classified_count"], 1)

    def test_tax_summary_distinguishes_taxable_and_exempt_income(self):
        taxable = self.finance.create_income(
            self.checking, 100000, "2026-02-01", self.income_category, payee="Employer"
        )
        exempt = self.finance.create_income(
            self.checking, 20000, "2026-03-01", self.income_category, payee="Gift"
        )
        self.tax.tag_transaction(taxable, "taxable_income", "Wages")
        self.tax.tag_transaction(exempt, "tax_exempt_income", "Gift")
        summary = self.tax.summary(2026)
        self.assertEqual(summary["gross_income_minor"], 120000)
        self.assertEqual(summary["taxable_income_minor"], 100000)

    def test_tax_classification_rejects_wrong_transaction_kind(self):
        transaction_id = self.finance.create_income(
            self.checking, 10000, "2026-02-01", self.income_category
        )
        with self.assertRaises(ValueError):
            self.tax.tag_transaction(transaction_id, "deductible_expense", "Supplies", 10000)

    def test_tax_classification_upserts_and_can_be_removed(self):
        transaction_id = self.finance.create_expense(
            self.checking, 10000, "2026-05-01", self.expense_category
        )
        self.tax.tag_transaction(transaction_id, "tax_payment", "Estimated taxes")
        self.tax.tag_transaction(transaction_id, "deductible_expense", "Supplies", 2500)
        self.assertEqual(len(self.tax.records(2026)), 1)
        self.tax.delete_tag(transaction_id)
        self.assertEqual(self.tax.records(2026), [])

    def test_tax_summary_counts_unclassified_transactions(self):
        self.finance.create_expense(self.checking, 5000, "2026-05-01", self.expense_category)
        self.finance.create_income(self.checking, 10000, "2026-05-02", self.income_category)
        summary = self.tax.summary(2026)
        self.assertEqual(summary["unclassified_income_count"], 1)
        self.assertEqual(summary["unclassified_expense_count"], 1)

    def test_tax_gross_income_includes_unclassified_income(self):
        self.finance.create_income(self.checking, 10000, "2026-05-02", self.income_category)
        tagged = self.finance.create_income(
            self.checking, 20000, "2026-05-03", self.income_category
        )
        self.tax.tag_transaction(tagged, "taxable_income", "Wages")
        summary = self.tax.summary(2026)
        self.assertEqual(summary["gross_income_minor"], 30000)
        self.assertEqual(summary["taxable_income_minor"], 20000)

    def test_tax_csv_export_contains_classification(self):
        transaction_id = self.finance.create_expense(
            self.checking, 5000, "2026-06-01", self.expense_category, payee="Pharmacy"
        )
        self.tax.tag_transaction(transaction_id, "deductible_expense", "Medical", 10000)
        path = Path(self.temp_dir.name) / "tax.csv"
        self.assertEqual(self.tax.export_csv(path, 2026), 1)
        self.assertIn("Medical", path.read_text(encoding="utf-8-sig"))

    def test_rule_applies_to_uncategorized_matching_expense(self):
        transaction_id = self.finance.create_expense(
            self.checking, 2500, "2026-01-10", None, payee="ACME MARKET #45"
        )
        rule_id = self.rules.create(
            name="Groceries", keyword="acme market", match_field="payee",
            transaction_kind="expense", category_id=self.expense_category, priority=10,
        )
        result = self.rules.apply_to_uncategorized()
        self.assertEqual(result["categorized"], 1)
        self.assertEqual(self.finance.transactions.get(transaction_id)["category_id"], self.expense_category)
        self.assertGreater(rule_id, 0)

    def test_rule_priority_uses_highest_priority_first(self):
        low_category = self.expense_category
        high_category = next(
            row["id"] for row in self.finance.categories.list(kind="expense")
            if row["id"] != low_category
        )
        transaction_id = self.finance.create_expense(
            self.checking, 2500, "2026-01-10", None, payee="ACME MARKET"
        )
        self.rules.create(
            name="General match", keyword="acme", match_field="any",
            transaction_kind="expense", category_id=low_category, priority=1,
        )
        self.rules.create(
            name="Specific match", keyword="acme market", match_field="payee",
            transaction_kind="expense", category_id=high_category, priority=10,
        )
        self.rules.apply_to_uncategorized()
        self.assertEqual(self.finance.transactions.get(transaction_id)["category_id"], high_category)

    def test_rule_does_not_overwrite_existing_category(self):
        transaction_id = self.finance.create_expense(
            self.checking, 2500, "2026-01-10", self.expense_category, payee="ACME MARKET"
        )
        other_category = next(
            row["id"] for row in self.finance.categories.list(kind="expense")
            if row["id"] != self.expense_category
        )
        self.rules.create(
            name="Market rule", keyword="acme", match_field="any",
            transaction_kind="expense", category_id=other_category,
        )
        self.assertEqual(self.rules.apply_to_uncategorized()["categorized"], 0)
        self.assertEqual(self.finance.transactions.get(transaction_id)["category_id"], self.expense_category)

    def test_rule_validates_category_kind(self):
        with self.assertRaises(ValueError):
            self.rules.create(
                name="Wrong kind", keyword="payroll", match_field="payee",
                transaction_kind="expense", category_id=self.income_category,
            )

    def test_archived_rule_is_not_applied(self):
        transaction_id = self.finance.create_expense(
            self.checking, 2500, "2026-01-10", None, payee="ACME MARKET"
        )
        rule_id = self.rules.create(
            name="Market rule", keyword="acme", match_field="any",
            transaction_kind="expense", category_id=self.expense_category,
        )
        self.rules.archive(rule_id)
        self.assertEqual(self.rules.apply_to_uncategorized()["categorized"], 0)
        self.assertIsNone(self.finance.transactions.get(transaction_id)["category_id"])


if __name__ == "__main__":
    unittest.main()
