from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .advanced import advance_date
from .domain import now_iso, today_iso, validate_date


VALID_TREATMENTS = {
    "deductible_expense",
    "non_deductible_expense",
    "tax_payment",
    "taxable_income",
    "tax_exempt_income",
    "capital_gain",
    "other",
}
VALID_RULE_FIELDS = {"payee", "description", "any"}


def _rounded_ratio(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("Denominator must be positive.")
    return (int(numerator) + denominator // 2) // denominator


class SubscriptionService:
    """Track recurring subscriptions and manually confirm renewal expenses."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    @staticmethod
    def monthly_equivalent(amount_minor: int, frequency: str) -> int:
        multipliers = {
            "weekly": (52, 12),
            "biweekly": (26, 12),
            "monthly": (1, 1),
            "quarterly": (1, 3),
            "yearly": (1, 12),
        }
        if frequency not in multipliers:
            raise ValueError("Unsupported subscription frequency.")
        numerator, denominator = multipliers[frequency]
        return _rounded_ratio(int(amount_minor) * numerator, denominator)

    @staticmethod
    def annual_equivalent(amount_minor: int, frequency: str) -> int:
        multipliers = {
            "weekly": (52, 1),
            "biweekly": (26, 1),
            "monthly": (12, 1),
            "quarterly": (4, 1),
            "yearly": (1, 1),
        }
        if frequency not in multipliers:
            raise ValueError("Unsupported subscription frequency.")
        numerator, denominator = multipliers[frequency]
        return _rounded_ratio(int(amount_minor) * numerator, denominator)

    def create(
        self, *, name: str, vendor: str = "", amount_minor: int,
        currency: str = "USD", frequency: str, next_renewal_date: str,
        category_id: int | None = None, account_id: int | None = None,
        trial_end_date: str | None = None, cancel_by_date: str | None = None,
        website_url: str = "", notes: str = "",
    ) -> int:
        name = name.strip()
        currency = currency.strip().upper()
        if not name:
            raise ValueError("Subscription name is required.")
        if amount_minor <= 0:
            raise ValueError("Subscription price must be greater than zero.")
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("Currency must be a three-letter code.")
        if frequency not in {"weekly", "biweekly", "monthly", "quarterly", "yearly"}:
            raise ValueError("Choose a supported billing frequency.")
        next_renewal_date = validate_date(next_renewal_date)
        if trial_end_date:
            trial_end_date = validate_date(trial_end_date)
        if cancel_by_date:
            cancel_by_date = validate_date(cancel_by_date)
        if trial_end_date and trial_end_date < next_renewal_date:
            raise ValueError("Trial end date cannot be before the next renewal date.")
        if cancel_by_date and cancel_by_date > next_renewal_date:
            raise ValueError("Cancellation deadline should be on or before the next renewal.")
        if website_url and not website_url.lower().startswith(("https://", "http://")):
            raise ValueError("Website URL must start with http:// or https://.")
        if account_id is not None:
            account = self.finance.accounts.get(int(account_id))
            if not account or not account["is_active"]:
                raise ValueError("Choose an active payment account.")
            if account["currency"].upper() != currency:
                raise ValueError("Subscription currency must match the selected account currency.")
        if category_id is not None:
            category = self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))
            if not category or not category["is_active"] or category["kind"] != "expense":
                raise ValueError("Choose an active expense category.")
        timestamp = now_iso()
        with self.db.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO subscriptions(
                    name, vendor, amount_minor, currency, frequency, next_renewal_date,
                    category_id, account_id, trial_end_date, cancel_by_date, website_url,
                    notes, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, vendor.strip(), int(amount_minor), currency, frequency,
                 next_renewal_date, category_id, account_id, trial_end_date,
                 cancel_by_date, website_url.strip(), notes.strip(), timestamp, timestamp),
            )
            subscription_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO subscription_price_history(
                    subscription_id, old_amount_minor, new_amount_minor, effective_date,
                    recorded_at, notes
                ) VALUES(?, NULL, ?, ?, ?, ?)""",
                (subscription_id, int(amount_minor), today_iso(), timestamp, "Initial price"),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('subscription', ?, 'create', ?, ?)""",
                (subscription_id, name, timestamp),
            )
            return subscription_id

    def list(self, include_inactive: bool = False) -> list[Any]:
        sql = """SELECT s.*, c.name AS category_name, a.name AS account_name
                 FROM subscriptions s
                 LEFT JOIN categories c ON c.id = s.category_id
                 LEFT JOIN accounts a ON a.id = s.account_id"""
        if not include_inactive:
            sql += " WHERE s.active = 1"
        return self.db.fetch_all(sql + " ORDER BY s.active DESC, s.next_renewal_date, s.name COLLATE NOCASE")

    def get(self, subscription_id: int):
        return self.db.fetch_one("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,))

    def due(self, through_date: str | None = None) -> list[Any]:
        through_date = validate_date(through_date or today_iso())
        return self.db.fetch_all(
            """SELECT * FROM subscriptions
               WHERE active = 1 AND next_renewal_date <= ?
               ORDER BY next_renewal_date, name COLLATE NOCASE""",
            (through_date,),
        )

    def summary(self) -> dict[str, Any]:
        rows = self.list()
        currencies = sorted({str(row["currency"]).upper() for row in rows})
        mixed_currency = len(currencies) > 1
        # Do not add different currencies together without an exchange rate.
        if mixed_currency:
            monthly = 0
            annual = 0
        else:
            monthly = sum(
                self.monthly_equivalent(int(row["amount_minor"]), row["frequency"])
                for row in rows
            )
            annual = sum(
                self.annual_equivalent(int(row["amount_minor"]), row["frequency"])
                for row in rows
            )
        return {
            "active_count": len(rows),
            "monthly_equivalent_minor": monthly,
            "annual_equivalent_minor": annual,
            "currency_mixed": mixed_currency,
            "currencies": currencies,
        }

    def update_price(
        self, subscription_id: int, amount_minor: int,
        effective_date: str | None = None, notes: str = "",
    ) -> None:
        if amount_minor <= 0:
            raise ValueError("Subscription price must be greater than zero.")
        effective_date = validate_date(effective_date or today_iso())
        row = self.get(subscription_id)
        if not row:
            raise ValueError("Subscription was not found.")
        old_amount = int(row["amount_minor"])
        if old_amount == int(amount_minor):
            return
        timestamp = now_iso()
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE subscriptions SET amount_minor = ?, updated_at = ? WHERE id = ?",
                (int(amount_minor), timestamp, subscription_id),
            )
            connection.execute(
                """INSERT INTO subscription_price_history(
                    subscription_id, old_amount_minor, new_amount_minor, effective_date,
                    recorded_at, notes
                ) VALUES(?, ?, ?, ?, ?, ?)""",
                (subscription_id, old_amount, int(amount_minor), effective_date,
                 timestamp, notes.strip()),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('subscription', ?, 'price_change', ?, ?)""",
                (subscription_id, f"{old_amount}->{amount_minor}", timestamp),
            )

    def price_history(self, subscription_id: int) -> list[Any]:
        return self.db.fetch_all(
            """SELECT * FROM subscription_price_history
               WHERE subscription_id = ? ORDER BY effective_date DESC, id DESC""",
            (subscription_id,),
        )

    def record_renewal(self, subscription_id: int, paid_on: str | None = None) -> int:
        row = self.get(subscription_id)
        if not row or not row["active"]:
            raise ValueError("Active subscription was not found.")
        if not row["account_id"]:
            raise ValueError("Assign a payment account before recording a renewal.")
        paid_on = validate_date(paid_on or today_iso())
        if paid_on < row["next_renewal_date"]:
            raise ValueError("This renewal is not due yet. Change the next renewal date if needed.")
        transaction_id = self.finance.create_expense(
            account_id=int(row["account_id"]),
            amount_minor=int(row["amount_minor"]),
            occurred_on=paid_on,
            category_id=row["category_id"],
            payee=row["vendor"] or row["name"],
            description=f"Subscription renewal: {row['name']}",
            notes=f"subscription_id:{subscription_id}",
        )
        next_date = advance_date(
            row["next_renewal_date"], row["frequency"],
            date.fromisoformat(row["next_renewal_date"]).day,
        )
        timestamp = now_iso()
        with self.db.transaction() as connection:
            connection.execute(
                """UPDATE subscriptions SET next_renewal_date = ?, last_renewed_on = ?,
                   updated_at = ? WHERE id = ?""",
                (next_date, paid_on, timestamp, subscription_id),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('subscription', ?, 'renewal', ?, ?)""",
                (subscription_id, f"transaction:{transaction_id}", timestamp),
            )
        return transaction_id

    def archive(self, subscription_id: int) -> None:
        if not self.get(subscription_id):
            raise ValueError("Subscription was not found.")
        self.db.execute(
            "UPDATE subscriptions SET active = 0, updated_at = ? WHERE id = ?",
            (now_iso(), subscription_id),
        )


class TaxService:
    """Attach user-defined tax labels to income and expense transactions."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    def tag_transaction(
        self, transaction_id: int, treatment: str, tax_category: str,
        deductible_basis_points: int = 0, notes: str = "",
    ) -> None:
        if treatment not in VALID_TREATMENTS:
            raise ValueError("Choose a supported tax treatment.")
        tax_category = tax_category.strip()
        if not tax_category:
            raise ValueError("Tax category is required.")
        basis_points = int(deductible_basis_points)
        if not 0 <= basis_points <= 10000:
            raise ValueError("Deductible percentage must be between 0 and 100.")
        transaction = self.finance.transactions.get(transaction_id)
        if not transaction:
            raise ValueError("Transaction was not found.")
        kind = transaction["kind"]
        expense_treatments = {"deductible_expense", "non_deductible_expense", "tax_payment"}
        income_treatments = {"taxable_income", "tax_exempt_income", "capital_gain"}
        if treatment in expense_treatments and kind != "expense":
            raise ValueError("This tax treatment can only be used for an expense.")
        if treatment in income_treatments and kind != "income":
            raise ValueError("This tax treatment can only be used for income.")
        if treatment != "deductible_expense":
            basis_points = 0
        timestamp = now_iso()
        tax_year = int(transaction["occurred_on"][:4])
        with self.db.transaction() as connection:
            connection.execute(
                """INSERT INTO transaction_tax_records(
                    transaction_id, tax_year, treatment, tax_category,
                    deductible_basis_points, notes, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    tax_year = excluded.tax_year,
                    treatment = excluded.treatment,
                    tax_category = excluded.tax_category,
                    deductible_basis_points = excluded.deductible_basis_points,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at""",
                (transaction_id, tax_year, treatment, tax_category, basis_points,
                 notes.strip(), timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('tax_record', ?, 'upsert', ?, ?)""",
                (transaction_id, f"{tax_year}:{treatment}:{tax_category}", timestamp),
            )

    def records(self, tax_year: int) -> list[Any]:
        return self.db.fetch_all(
            """SELECT r.*, t.occurred_on, t.kind, t.amount_minor, t.payee,
                      t.description, a.name AS account_name
               FROM transaction_tax_records r
               JOIN transactions t ON t.id = r.transaction_id
               JOIN accounts a ON a.id = t.account_id
               WHERE r.tax_year = ?
               ORDER BY t.occurred_on DESC, t.id DESC""",
            (int(tax_year),),
        )

    def summary(self, tax_year: int) -> dict[str, int]:
        year = str(int(tax_year))
        row = self.db.fetch_one(
            """SELECT
                 COALESCE(SUM(CASE WHEN t.kind = 'income' THEN t.amount_minor ELSE 0 END), 0) AS gross_income,
                 COALESCE(SUM(CASE WHEN r.treatment IN ('taxable_income', 'capital_gain')
                                   THEN t.amount_minor ELSE 0 END), 0) AS taxable_income,
                 COALESCE(SUM(CASE WHEN r.treatment = 'deductible_expense'
                                   THEN (t.amount_minor * r.deductible_basis_points + 5000) / 10000
                                   ELSE 0 END), 0) AS deductible_expenses,
                 COALESCE(SUM(CASE WHEN r.treatment = 'tax_payment'
                                   THEN t.amount_minor ELSE 0 END), 0) AS tax_payments,
                 COUNT(*) AS classified_count
               FROM transaction_tax_records r
               JOIN transactions t ON t.id = r.transaction_id
               WHERE r.tax_year = ?""",
            (int(tax_year),),
        )
        unclassified = self.db.fetch_one(
            """SELECT
                 SUM(CASE WHEN t.kind = 'income' THEN 1 ELSE 0 END) AS income_count,
                 SUM(CASE WHEN t.kind = 'expense' THEN 1 ELSE 0 END) AS expense_count
               FROM transactions t
               LEFT JOIN transaction_tax_records r ON r.transaction_id = t.id
               WHERE substr(t.occurred_on, 1, 4) = ? AND r.transaction_id IS NULL
                 AND t.kind IN ('income', 'expense')""",
            (year,),
        )
        gross_income = self.db.fetch_one(
            """SELECT COALESCE(SUM(amount_minor), 0) AS total
               FROM transactions
               WHERE kind = 'income' AND substr(occurred_on, 1, 4) = ?""",
            (year,),
        )
        return {
            "gross_income_minor": int(gross_income["total"] or 0),
            "taxable_income_minor": int(row["taxable_income"] or 0),
            "deductible_expenses_minor": int(row["deductible_expenses"] or 0),
            "tax_payments_minor": int(row["tax_payments"] or 0),
            "classified_count": int(row["classified_count"] or 0),
            "unclassified_income_count": int(unclassified["income_count"] or 0),
            "unclassified_expense_count": int(unclassified["expense_count"] or 0),
        }

    def delete_tag(self, transaction_id: int) -> None:
        self.db.execute(
            "DELETE FROM transaction_tax_records WHERE transaction_id = ?",
            (int(transaction_id),),
        )

    def export_csv(self, path: str | Path, tax_year: int) -> int:
        rows = self.records(tax_year)
        columns = [
            "date", "tax_year", "type", "account", "payee", "description",
            "amount", "treatment", "tax_category", "deductible_percent",
            "deductible_amount", "notes",
        ]
        with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                deductible = _rounded_ratio(
                    int(row["amount_minor"]) * int(row["deductible_basis_points"]), 10000
                )
                writer.writerow({
                    "date": row["occurred_on"],
                    "tax_year": row["tax_year"],
                    "type": row["kind"],
                    "account": row["account_name"],
                    "payee": row["payee"],
                    "description": row["description"],
                    "amount": str(Decimal(int(row["amount_minor"])) / Decimal(100)),
                    "treatment": row["treatment"],
                    "tax_category": row["tax_category"],
                    "deductible_percent": int(row["deductible_basis_points"]) / 100,
                    "deductible_amount": str(Decimal(deductible) / Decimal(100)),
                    "notes": row["notes"],
                })
        return len(rows)


class CategorizationRuleService:
    """Apply explicit keyword rules to uncategorized income and expenses."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    def create(
        self, *, name: str, keyword: str, match_field: str,
        transaction_kind: str, category_id: int, priority: int = 100,
    ) -> int:
        name, keyword = name.strip(), keyword.strip()
        if not name:
            raise ValueError("Rule name is required.")
        if not keyword:
            raise ValueError("Keyword is required.")
        if match_field not in VALID_RULE_FIELDS:
            raise ValueError("Choose payee, description, or any field.")
        if transaction_kind not in {"income", "expense"}:
            raise ValueError("Rules can target income or expense transactions.")
        category = self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))
        if not category or not category["is_active"] or category["kind"] != transaction_kind:
            raise ValueError(f"Choose an active {transaction_kind} category.")
        return self.db.execute(
            """INSERT INTO categorization_rules(
                name, keyword, match_field, transaction_kind, category_id, priority, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (name, keyword, match_field, transaction_kind, category_id,
             int(priority), now_iso()),
        )

    def list(self, include_inactive: bool = False) -> list[Any]:
        sql = """SELECT r.*, c.name AS category_name
                 FROM categorization_rules r
                 JOIN categories c ON c.id = r.category_id"""
        if not include_inactive:
            sql += " WHERE r.active = 1"
        return self.db.fetch_all(
            sql + " ORDER BY r.priority DESC, r.id ASC"
        )

    @staticmethod
    def _matches(rule: Any, transaction: Any) -> bool:
        keyword = str(rule["keyword"]).casefold()
        payee = str(transaction["payee"] or "").casefold()
        description = str(transaction["description"] or "").casefold()
        if rule["match_field"] == "payee":
            haystack = payee
        elif rule["match_field"] == "description":
            haystack = description
        else:
            haystack = f"{payee}\n{description}"
        return keyword in haystack

    def apply_to_uncategorized(self, limit: int = 10000) -> dict[str, Any]:
        rules = self.list()
        transactions = self.db.fetch_all(
            """SELECT * FROM transactions
               WHERE category_id IS NULL AND kind IN ('income', 'expense')
               ORDER BY occurred_on, id LIMIT ?""",
            (max(1, min(int(limit), 50000)),),
        )
        categorized = 0
        unmatched = 0
        matches: list[dict[str, Any]] = []
        timestamp = now_iso()
        with self.db.transaction() as connection:
            for transaction in transactions:
                selected = next(
                    (
                        rule for rule in rules
                        if rule["transaction_kind"] == transaction["kind"]
                        and self._matches(rule, transaction)
                    ),
                    None,
                )
                if not selected:
                    unmatched += 1
                    continue
                connection.execute(
                    "UPDATE transactions SET category_id = ?, updated_at = ? WHERE id = ? AND category_id IS NULL",
                    (int(selected["category_id"]), timestamp, int(transaction["id"])),
                )
                connection.execute(
                    """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                       VALUES('transaction', ?, 'auto_categorize', ?, ?)""",
                    (int(transaction["id"]), f"rule:{selected['id']}:{selected['name']}", timestamp),
                )
                categorized += 1
                matches.append({
                    "transaction_id": int(transaction["id"]),
                    "rule_id": int(selected["id"]),
                    "rule_name": selected["name"],
                    "category_name": selected["category_name"],
                })
        return {
            "categorized": categorized,
            "unmatched": unmatched,
            "examined": len(transactions),
            "matches": matches,
        }

    def archive(self, rule_id: int) -> None:
        row = self.db.fetch_one("SELECT id FROM categorization_rules WHERE id = ?", (rule_id,))
        if not row:
            raise ValueError("Categorization rule was not found.")
        self.db.execute("UPDATE categorization_rules SET active = 0 WHERE id = ?", (rule_id,))
