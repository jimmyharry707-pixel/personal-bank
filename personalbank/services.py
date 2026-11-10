from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from .db import Database
from .domain import (
    AccountType, CategoryType, Frequency, TransactionType, month_iso,
    now_iso, today_iso, validate_date,
)
from .repositories import (
    AccountRepository, BillRepository, BudgetRepository, CategoryRepository,
    GoalRepository, SettingsRepository, TransactionRepository,
)


class FinanceService:
    """Application service coordinating repositories and finance rules."""

    def __init__(self, db: Database):
        self.db = db
        self.accounts = AccountRepository(db)
        self.categories = CategoryRepository(db)
        self.transactions = TransactionRepository(db)
        self.budgets = BudgetRepository(db)
        self.bills = BillRepository(db)
        self.goals = GoalRepository(db)
        self.settings = SettingsRepository(db)

    # Accounts
    def create_account(self, name: str, kind: str, currency: str = "USD",
                       opening_balance_minor: int = 0, credit_limit_minor: int = 0) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Account name is required.")
        if kind not in {item.value for item in AccountType}:
            raise ValueError("Choose a supported account type.")
        if not currency or len(currency.strip()) != 3 or not currency.isalpha():
            raise ValueError("Currency must be a three-letter code.")
        if credit_limit_minor < 0:
            raise ValueError("Credit limit cannot be negative.")
        return self.accounts.create(
            name, kind, currency.upper(), int(opening_balance_minor), int(credit_limit_minor)
        )

    def update_account(self, account_id: int, **fields: Any) -> None:
        if "name" in fields and not str(fields["name"]).strip():
            raise ValueError("Account name is required.")
        if "credit_limit_minor" in fields and int(fields["credit_limit_minor"]) < 0:
            raise ValueError("Credit limit cannot be negative.")
        self.accounts.update(account_id, **fields)

    def archive_account(self, account_id: int) -> None:
        if not self.accounts.get(account_id):
            raise ValueError("Account was not found.")
        self.accounts.archive(account_id)

    def account_balance(self, account_id: int) -> int:
        account = self.accounts.get(account_id)
        if not account:
            raise ValueError("Account was not found.")
        return self._account_balance_from_row(account)

    def _account_balance_from_row(self, account: Any) -> int:
        rows = self.db.fetch_all(
            """SELECT kind, amount_minor, account_id, transfer_account_id, notes
               FROM transactions WHERE account_id = ? OR transfer_account_id = ?""",
            (account["id"], account["id"]),
        )
        balance = int(account["opening_balance_minor"])
        for row in rows:
            amount = int(row["amount_minor"])
            kind = row["kind"]
            if kind == TransactionType.INCOME.value:
                balance += amount
            elif kind == TransactionType.EXPENSE.value:
                balance -= amount
            elif kind == TransactionType.TRANSFER.value:
                if int(row["account_id"]) == int(account["id"]):
                    balance -= amount
                else:
                    balance += amount
            elif kind == TransactionType.ADJUSTMENT.value:
                sign = -1 if "adjustment_sign:-1" in str(row["notes"]) else 1
                balance += amount * sign
        return balance

    def account_balances(self) -> list[dict[str, Any]]:
        result = []
        for account in self.accounts.list():
            result.append({
                "id": account["id"],
                "name": account["name"],
                "kind": account["kind"],
                "currency": account["currency"],
                "balance_minor": self._account_balance_from_row(account),
            })
        return result

    # Categories
    def create_category(self, name: str, kind: str, color: str = "#64748b") -> int:
        if not name.strip():
            raise ValueError("Category name is required.")
        if kind not in {CategoryType.INCOME.value, CategoryType.EXPENSE.value}:
            raise ValueError("Category type must be income or expense.")
        import re
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Color must be a six-digit hex color such as #64748b.")
        return self.categories.create(name, kind, color)

    # Transactions
    def create_income(self, account_id: int, amount_minor: int, occurred_on: str,
                      category_id: int | None = None, payee: str = "",
                      description: str = "", reference: str = "", notes: str = "") -> int:
        return self._create_transaction(
            account_id=account_id, transfer_account_id=None, category_id=category_id,
            kind=TransactionType.INCOME.value, amount_minor=amount_minor,
            occurred_on=occurred_on, payee=payee, description=description,
            reference=reference, notes=notes,
        )

    def create_expense(self, account_id: int, amount_minor: int, occurred_on: str,
                       category_id: int | None = None, payee: str = "",
                       description: str = "", reference: str = "", notes: str = "") -> int:
        return self._create_transaction(
            account_id=account_id, transfer_account_id=None, category_id=category_id,
            kind=TransactionType.EXPENSE.value, amount_minor=amount_minor,
            occurred_on=occurred_on, payee=payee, description=description,
            reference=reference, notes=notes,
        )

    def create_transfer(self, from_account_id: int, to_account_id: int,
                        amount_minor: int, occurred_on: str,
                        description: str = "", notes: str = "") -> int:
        if from_account_id == to_account_id:
            raise ValueError("A transfer must use two different accounts.")
        self._require_account(from_account_id)
        self._require_account(to_account_id)
        return self._create_transaction(
            account_id=from_account_id, transfer_account_id=to_account_id,
            category_id=None, kind=TransactionType.TRANSFER.value,
            amount_minor=amount_minor, occurred_on=occurred_on,
            description=description or "Account transfer", notes=notes,
        )

    def create_adjustment(self, account_id: int, signed_amount_minor: int,
                          occurred_on: str, description: str = "Balance adjustment") -> int:
        if signed_amount_minor == 0:
            raise ValueError("Adjustment cannot be zero.")
        self._require_account(account_id)
        sign_note = "adjustment_sign:1" if signed_amount_minor > 0 else "adjustment_sign:-1"
        return self._create_transaction(
            account_id=account_id, transfer_account_id=None, category_id=None,
            kind=TransactionType.ADJUSTMENT.value,
            amount_minor=abs(int(signed_amount_minor)), occurred_on=occurred_on,
            description=description.strip() or "Balance adjustment", notes=sign_note,
        )

    def _create_transaction(self, *, account_id: int, transfer_account_id: int | None,
                             category_id: int | None, kind: str, amount_minor: int,
                             occurred_on: str, payee: str = "", description: str = "",
                             reference: str = "", notes: str = "") -> int:
        self._require_account(account_id)
        if amount_minor <= 0:
            raise ValueError("Transaction amount must be greater than zero.")
        occurred_on = validate_date(occurred_on)
        if category_id is not None:
            category = self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))
            if not category or not category["is_active"]:
                raise ValueError("Choose an active category.")
            expected = "income" if kind == "income" else "expense" if kind == "expense" else None
            if expected and category["kind"] != expected:
                raise ValueError(f"Choose an {expected} category.")
        if transfer_account_id is not None:
            self._require_account(transfer_account_id)
        return self.transactions.create(
            account_id=account_id, transfer_account_id=transfer_account_id,
            category_id=category_id, kind=kind, amount_minor=int(amount_minor),
            occurred_on=occurred_on, payee=payee, description=description,
            reference=reference, notes=notes,
        )

    def _require_account(self, account_id: int) -> Any:
        account = self.accounts.get(account_id)
        if not account or not account["is_active"]:
            raise ValueError("Choose an active account.")
        return account

    def update_transaction(
        self,
        transaction_id: int,
        *,
        account_id: int,
        transfer_account_id: int | None,
        category_id: int | None,
        kind: str,
        amount_minor: int,
        occurred_on: str,
        payee: str = "",
        description: str = "",
        reference: str = "",
        notes: str = "",
    ) -> None:
        existing = self.transactions.get(int(transaction_id))
        if not existing:
            raise ValueError("Transaction was not found.")
        protected = self.db.fetch_one(
            """SELECT 1 FROM reconciled_transactions WHERE transaction_id = ?
               UNION ALL SELECT 1 FROM debt_payments WHERE transaction_id = ?
               UNION ALL SELECT 1 FROM investment_trades WHERE transaction_id = ?
               UNION ALL SELECT 1 FROM reconciliation_items ri
                 JOIN reconciliation_sessions rs ON rs.id = ri.session_id
                 WHERE ri.transaction_id = ? AND rs.status = 'open'
               LIMIT 1""",
            (int(transaction_id), int(transaction_id), int(transaction_id), int(transaction_id)),
        )
        if protected:
            raise ValueError("This transaction is reconciled or linked to a debt/investment record and cannot be edited.")
        if kind not in {
            TransactionType.INCOME.value,
            TransactionType.EXPENSE.value,
            TransactionType.TRANSFER.value,
        }:
            raise ValueError("Only income, expense, and transfer transactions can be edited here.")
        if int(amount_minor) <= 0:
            raise ValueError("Transaction amount must be greater than zero.")
        occurred_on = validate_date(occurred_on)
        self._require_account(int(account_id))
        if kind == TransactionType.TRANSFER.value:
            if transfer_account_id is None:
                raise ValueError("Choose a destination account for the transfer.")
            if int(account_id) == int(transfer_account_id):
                raise ValueError("A transfer must use two different accounts.")
            self._require_account(int(transfer_account_id))
            category_id = None
        else:
            transfer_account_id = None
            if category_id is not None:
                category = self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (int(category_id),))
                expected = "income" if kind == TransactionType.INCOME.value else "expense" if kind == TransactionType.EXPENSE.value else None
                if not category or not category["is_active"] or (expected and category["kind"] != expected):
                    raise ValueError(f"Choose an active {expected or 'valid'} category.")
        self.transactions.update(
            int(transaction_id), account_id=int(account_id),
            transfer_account_id=int(transfer_account_id) if transfer_account_id is not None else None,
            category_id=int(category_id) if category_id is not None else None,
            kind=kind, amount_minor=int(amount_minor), occurred_on=occurred_on,
            payee=payee, description=description, reference=reference, notes=notes,
        )

    def delete_transaction(self, transaction_id: int) -> None:
        if not self.transactions.get(transaction_id):
            raise ValueError("Transaction was not found.")
        protected = self.db.fetch_one(
            """SELECT 1 FROM reconciled_transactions WHERE transaction_id = ?
               UNION ALL SELECT 1 FROM debt_payments WHERE transaction_id = ?
               UNION ALL SELECT 1 FROM investment_trades WHERE transaction_id = ?
               UNION ALL SELECT 1 FROM reconciliation_items ri
                 JOIN reconciliation_sessions rs ON rs.id = ri.session_id
                 WHERE ri.transaction_id = ? AND rs.status = 'open'
               LIMIT 1""",
            (int(transaction_id), int(transaction_id), int(transaction_id), int(transaction_id)),
        )
        if protected:
            raise ValueError("This transaction is reconciled or linked to a debt/investment record and cannot be deleted.")
        self.transactions.delete(transaction_id)

    def list_transactions(self, **filters: Any) -> list[Any]:
        return self.transactions.list(**filters)

    # Budgets
    def set_budget(self, category_id: int, month: str, limit_minor: int) -> int:
        month = month_iso(month)
        category = self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))
        if not category or not category["is_active"] or category["kind"] != "expense":
            raise ValueError("Budgets can only be assigned to active expense categories.")
        if limit_minor < 0:
            raise ValueError("Budget limit cannot be negative.")
        return self.budgets.upsert(category_id, month, int(limit_minor))

    def budget_status(self, month: str) -> list[dict[str, Any]]:
        month = month_iso(month)
        result = []
        for budget in self.budgets.list(month):
            spent = self.db.fetch_one(
                """SELECT COALESCE(SUM(amount_minor), 0) AS total
                   FROM transactions
                   WHERE category_id = ? AND kind = 'expense'
                     AND substr(occurred_on, 1, 7) = ?""",
                (budget["category_id"], month),
            )["total"]
            limit_minor = int(budget["limit_minor"])
            spent_minor = int(spent or 0)
            result.append({
                "id": budget["id"],
                "category_id": budget["category_id"],
                "category_name": budget["category_name"],
                "color": budget["category_color"],
                "limit_minor": limit_minor,
                "spent_minor": spent_minor,
                "remaining_minor": limit_minor - spent_minor,
                "percent": (spent_minor / limit_minor * 100) if limit_minor else 0.0,
            })
        return result

    # Bills
    def create_bill(self, *, name: str, amount_minor: int, due_day: int,
                    category_id: int | None, account_id: int | None,
                    frequency: str, auto_post: bool, next_due_date: str,
                    notes: str = "") -> int:
        if not name.strip():
            raise ValueError("Bill name is required.")
        if amount_minor <= 0:
            raise ValueError("Bill amount must be greater than zero.")
        if not 1 <= int(due_day) <= 31:
            raise ValueError("Due day must be between 1 and 31.")
        if frequency not in {item.value for item in Frequency}:
            raise ValueError("Choose a supported bill frequency.")
        validate_date(next_due_date)
        if account_id:
            self._require_account(account_id)
        if category_id:
            category = self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))
            if not category or not category["is_active"] or category["kind"] != "expense":
                raise ValueError("Choose an active expense category for the bill.")
        return self.bills.create(
            name=name, amount_minor=amount_minor, due_day=due_day,
            category_id=category_id, account_id=account_id, frequency=frequency,
            auto_post=auto_post, next_due_date=next_due_date, notes=notes,
        )

    def pay_bill(self, bill_id: int, paid_on: str | None = None) -> int:
        paid_on = validate_date(paid_on or today_iso())
        with self.db.transaction() as connection:
            bill = connection.execute(
                "SELECT * FROM bills WHERE id = ? AND active = 1", (int(bill_id),)
            ).fetchone()
            if not bill:
                raise ValueError("Active bill was not found.")
            if not bill["account_id"]:
                raise ValueError("Assign an account to this bill before recording payment.")
            account = connection.execute(
                "SELECT is_active FROM accounts WHERE id = ?", (int(bill["account_id"]),)
            ).fetchone()
            if not account or not account["is_active"]:
                raise ValueError("The bill's payment account is archived. Update the bill before paying it.")
            if bill["category_id"] is not None:
                category = connection.execute(
                    "SELECT is_active, kind FROM categories WHERE id = ?", (int(bill["category_id"]),)
                ).fetchone()
                if not category or not category["is_active"] or category["kind"] != "expense":
                    raise ValueError("The bill's category is archived or invalid. Update the bill before paying it.")
            timestamp = now_iso()
            cursor = connection.execute(
                """INSERT INTO transactions(
                    account_id, transfer_account_id, category_id, kind, amount_minor,
                    occurred_on, payee, description, reference, notes, created_at, updated_at
                ) VALUES(?, NULL, ?, 'expense', ?, ?, ?, ?, '', ?, ?, ?)""",
                (int(bill["account_id"]), bill["category_id"], int(bill["amount_minor"]),
                 paid_on, bill["name"], f"Bill payment: {bill['name']}",
                 bill["notes"], timestamp, timestamp),
            )
            transaction_id = int(cursor.lastrowid)
            next_date = self._next_due_date(bill["next_due_date"], bill["frequency"])
            connection.execute(
                "UPDATE bills SET next_due_date = ? WHERE id = ?",
                (next_date, int(bill_id)),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('transaction', ?, 'create', ?, ?)""",
                (transaction_id, f"expense: bill payment {bill['name']}", timestamp),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('bill', ?, 'payment', ?, ?)""",
                (int(bill_id), f"transaction_id={transaction_id}; next_due={next_date}", timestamp),
            )
            return transaction_id

    def _next_due_date(self, current: str, frequency: str) -> str:
        due = date.fromisoformat(current)
        if frequency == Frequency.WEEKLY.value:
            return (due + timedelta(days=7)).isoformat()
        if frequency == Frequency.BIWEEKLY.value:
            return (due + timedelta(days=14)).isoformat()
        if frequency == Frequency.QUARTERLY.value:
            months = 3
        elif frequency == Frequency.YEARLY.value:
            months = 12
        else:
            months = 1
        month_index = due.month - 1 + months
        year = due.year + month_index // 12
        month = month_index % 12 + 1
        day = min(due.day, calendar.monthrange(year, month)[1])
        return date(year, month, day).isoformat()

    # Savings goals
    def create_goal(self, name: str, target_minor: int, target_date: str | None = None,
                    notes: str = "") -> int:
        if not name.strip():
            raise ValueError("Goal name is required.")
        if target_minor <= 0:
            raise ValueError("Goal target must be greater than zero.")
        if target_date:
            validate_date(target_date)
        return self.goals.create(name, target_minor, target_date, notes)

    def contribute_to_goal(self, goal_id: int, amount_minor: int) -> None:
        if amount_minor <= 0:
            raise ValueError("Contribution must be greater than zero.")
        goal = self.db.fetch_one("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        if not goal:
            raise ValueError("Savings goal was not found.")
        self.goals.add_contribution(goal_id, int(amount_minor))

    # Reports
    def dashboard_summary(self, month: str | None = None) -> dict[str, int]:
        month = month or today_iso()[:7]
        month = month_iso(month)
        totals = self.db.fetch_one(
            """SELECT
               COALESCE(SUM(CASE WHEN t.kind = 'income' THEN t.amount_minor ELSE 0 END), 0) AS income,
               COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN t.amount_minor ELSE 0 END), 0) AS expenses
               FROM transactions t
               WHERE substr(t.occurred_on, 1, 7) = ?
                 AND NOT EXISTS (
                   SELECT 1 FROM investment_trades it WHERE it.transaction_id = t.id
                 )""",
            (month,),
        )
        balances = self.account_balances()
        return {
            "total_balance": sum(item["balance_minor"] for item in balances),
            "income": int(totals["income"]),
            "expenses": int(totals["expenses"]),
            "net": int(totals["income"]) - int(totals["expenses"]),
        }

    def monthly_cashflow(self, year: int) -> list[dict[str, int]]:
        rows = self.db.fetch_all(
            """SELECT substr(t.occurred_on, 1, 7) AS month,
               SUM(CASE WHEN t.kind = 'income' THEN t.amount_minor ELSE 0 END) AS income,
               SUM(CASE WHEN t.kind = 'expense' THEN t.amount_minor ELSE 0 END) AS expenses
               FROM transactions t
               WHERE substr(t.occurred_on, 1, 4) = ?
                 AND NOT EXISTS (
                   SELECT 1 FROM investment_trades it WHERE it.transaction_id = t.id
                 )
               GROUP BY substr(t.occurred_on, 1, 7) ORDER BY month""",
            (str(year),),
        )
        by_month = {row["month"]: row for row in rows}
        result = []
        for month in range(1, 13):
            key = f"{year}-{month:02d}"
            row = by_month.get(key)
            result.append({
                "month": key,
                "income": int(row["income"] or 0) if row else 0,
                "expenses": int(row["expenses"] or 0) if row else 0,
            })
        return result

    def spending_by_category(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        validate_date(start_date)
        validate_date(end_date)
        rows = self.db.fetch_all(
            """SELECT c.id, c.name, c.color, COALESCE(SUM(t.amount_minor), 0) AS total
               FROM categories c LEFT JOIN transactions t
                 ON t.category_id = c.id AND t.kind = 'expense'
                AND t.occurred_on BETWEEN ? AND ?
               WHERE c.kind = 'expense' AND c.is_active = 1
               GROUP BY c.id ORDER BY total DESC, c.name""",
            (start_date, end_date),
        )
        return [
            {"category_id": row["id"], "category_name": row["name"],
             "color": row["color"], "total_minor": int(row["total"])}
            for row in rows if int(row["total"]) > 0
        ]

    def recent_activity(self, limit: int = 8) -> list[Any]:
        return self.transactions.list(limit=limit)

    def due_bills(self, through_date: str | None = None) -> list[Any]:
        through_date = through_date or (date.today() + timedelta(days=30)).isoformat()
        return self.db.fetch_all(
            """SELECT * FROM bills WHERE active = 1 AND next_due_date <= ?
               ORDER BY next_due_date LIMIT 100""",
            (through_date,),
        )
