from __future__ import annotations

import calendar
import json
import sqlite3
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .domain import Frequency, now_iso, today_iso, validate_date


VALID_FREQUENCIES = {item.value for item in Frequency}
LIABILITY_ACCOUNT_TYPES = {"credit_card", "loan"}
CASH_ACCOUNT_TYPES = {"checking", "savings", "cash"}


def add_months(value: date, months: int, anchor_day: int | None = None) -> date:
    """Advance a date by calendar months without drifting at month ends."""
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    desired_day = anchor_day or value.day
    day = min(max(1, int(desired_day)), calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance_date(value: str, frequency: str, anchor_day: int | None = None) -> str:
    current = date.fromisoformat(validate_date(value))
    if frequency == "weekly":
        result = current + timedelta(days=7)
    elif frequency == "biweekly":
        result = current + timedelta(days=14)
    elif frequency == "monthly":
        result = add_months(current, 1, anchor_day)
    elif frequency == "quarterly":
        result = add_months(current, 3, anchor_day)
    elif frequency == "yearly":
        result = add_months(current, 12, anchor_day)
    else:
        raise ValueError("Unsupported recurrence frequency.")
    return result.isoformat()


def rounded_division(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("The divisor must be positive.")
    return (int(numerator) + denominator // 2) // denominator


def _validate_account(finance, account_id: int, allowed_kinds: set[str] | None = None):
    account = finance.accounts.get(int(account_id))
    if not account or not account["is_active"]:
        raise ValueError("Choose an active account.")
    if allowed_kinds and account["kind"] not in allowed_kinds:
        allowed = ", ".join(sorted(allowed_kinds))
        raise ValueError(f"Choose an account with one of these types: {allowed}.")
    return account


def _validate_category(finance, category_id: int | None, kind: str) -> None:
    if category_id is None:
        return
    category = finance.db.fetch_one("SELECT * FROM categories WHERE id = ?", (int(category_id),))
    if not category or not category["is_active"] or category["kind"] != kind:
        raise ValueError(f"Choose an active {kind} category.")


def _insert_transaction(
    connection: sqlite3.Connection,
    *,
    account_id: int,
    kind: str,
    amount_minor: int,
    occurred_on: str,
    category_id: int | None = None,
    payee: str = "",
    description: str = "",
    reference: str = "",
    notes: str = "",
) -> int:
    timestamp = now_iso()
    cursor = connection.execute(
        """INSERT INTO transactions(
            account_id, transfer_account_id, category_id, kind, amount_minor,
            occurred_on, payee, description, reference, notes, created_at, updated_at
        ) VALUES(?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_id, category_id, kind, int(amount_minor), occurred_on,
         payee.strip(), description.strip(), reference.strip(), notes.strip(),
         timestamp, timestamp),
    )
    transaction_id = int(cursor.lastrowid)
    connection.execute(
        """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
           VALUES('transaction', ?, 'create', ?, ?)""",
        (transaction_id, f"{kind}: {description or payee}", timestamp),
    )
    return transaction_id


class RecurringTransactionService:
    """User-confirmed recurring income and expense templates."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    def create(
        self,
        *,
        name: str,
        kind: str,
        account_id: int,
        category_id: int | None,
        amount_minor: int,
        frequency: str,
        next_due_date: str,
        end_date: str | None = None,
        payee: str = "",
        description: str = "",
        notes: str = "",
    ) -> int:
        if not name.strip():
            raise ValueError("Schedule name is required.")
        if kind not in {"income", "expense"}:
            raise ValueError("Recurring transaction type must be income or expense.")
        if int(amount_minor) <= 0:
            raise ValueError("Recurring amount must be greater than zero.")
        if frequency not in VALID_FREQUENCIES:
            raise ValueError("Choose a supported recurrence frequency.")
        account = _validate_account(self.finance, account_id)
        _validate_category(self.finance, category_id, kind)
        next_due_date = validate_date(next_due_date)
        if end_date:
            end_date = validate_date(end_date)
            if end_date < next_due_date:
                raise ValueError("The end date cannot be earlier than the next due date.")
        due_day = date.fromisoformat(next_due_date).day
        return self.db.execute(
            """INSERT INTO recurring_transactions(
                name, kind, account_id, category_id, amount_minor, payee,
                description, frequency, anchor_day, next_due_date, end_date,
                notes, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.strip(), kind, account["id"], category_id, int(amount_minor),
             payee.strip(), description.strip(), frequency, due_day,
             next_due_date, end_date, notes.strip(), now_iso()),
        )

    def list(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = """SELECT r.*, a.name AS account_name, c.name AS category_name
                 FROM recurring_transactions r
                 JOIN accounts a ON a.id = r.account_id
                 LEFT JOIN categories c ON c.id = r.category_id"""
        if not include_inactive:
            sql += " WHERE r.active = 1"
        return self.db.fetch_all(sql + " ORDER BY r.active DESC, r.next_due_date, r.name")

    def due(self, through_date: str | None = None) -> list[sqlite3.Row]:
        through_date = validate_date(through_date or today_iso())
        return self.db.fetch_all(
            """SELECT * FROM recurring_transactions
               WHERE active = 1 AND next_due_date <= ?
               ORDER BY next_due_date, name""",
            (through_date,),
        )

    def get(self, recurring_id: int) -> sqlite3.Row | None:
        return self.db.fetch_one(
            "SELECT * FROM recurring_transactions WHERE id = ?", (int(recurring_id),)
        )

    def post(self, recurring_id: int, posted_on: str | None = None) -> int:
        posted_on = validate_date(posted_on or today_iso())
        with self.db.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM recurring_transactions WHERE id = ? AND active = 1",
                (int(recurring_id),),
            ).fetchone()
            if not row:
                raise ValueError("Active recurring schedule was not found.")
            account = connection.execute(
                "SELECT is_active FROM accounts WHERE id = ?", (int(row["account_id"]),)
            ).fetchone()
            if not account or not account["is_active"]:
                raise ValueError("The recurring schedule's account is archived. Update the schedule before posting.")
            if row["category_id"] is not None:
                category = connection.execute(
                    "SELECT is_active, kind FROM categories WHERE id = ?", (int(row["category_id"]),)
                ).fetchone()
                if not category or not category["is_active"] or category["kind"] != row["kind"]:
                    raise ValueError("The recurring schedule's category is archived or no longer valid.")
            if posted_on < row["next_due_date"]:
                raise ValueError("This recurring item is not due yet.")
            next_due = advance_date(row["next_due_date"], row["frequency"], row["anchor_day"])
            active = int(not row["end_date"] or next_due <= row["end_date"])
            transaction_id = _insert_transaction(
                connection,
                account_id=int(row["account_id"]),
                kind=row["kind"],
                amount_minor=int(row["amount_minor"]),
                occurred_on=posted_on,
                category_id=row["category_id"],
                payee=row["payee"],
                description=row["description"] or f"Recurring: {row['name']}",
                notes=row["notes"],
            )
            connection.execute(
                """UPDATE recurring_transactions
                   SET next_due_date = ?, last_posted_on = ?, active = ? WHERE id = ?""",
                (next_due, posted_on, active, int(recurring_id)),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('recurring_transaction', ?, 'post', ?, ?)""",
                (int(recurring_id), f"transaction_id={transaction_id}", now_iso()),
            )
            return transaction_id

    def skip(self, recurring_id: int) -> str:
        with self.db.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM recurring_transactions WHERE id = ? AND active = 1",
                (int(recurring_id),),
            ).fetchone()
            if not row:
                raise ValueError("Active recurring schedule was not found.")
            next_due = advance_date(row["next_due_date"], row["frequency"], row["anchor_day"])
            active = int(not row["end_date"] or next_due <= row["end_date"])
            connection.execute(
                "UPDATE recurring_transactions SET next_due_date = ?, active = ? WHERE id = ?",
                (next_due, active, int(recurring_id)),
            )
            return next_due

    def archive(self, recurring_id: int) -> None:
        self.db.execute(
            "UPDATE recurring_transactions SET active = 0 WHERE id = ?", (int(recurring_id),)
        )


class ReconciliationService:
    """Statement reconciliation with explicit cleared-item selection."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    def open_session(self, account_id: int) -> sqlite3.Row | None:
        return self.db.fetch_one(
            """SELECT * FROM reconciliation_sessions
               WHERE account_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1""",
            (int(account_id),),
        )

    def start_session(
        self,
        account_id: int,
        statement_date: str,
        statement_balance_minor: int,
        notes: str = "",
    ) -> int:
        account = _validate_account(self.finance, account_id)
        statement_date = validate_date(statement_date)
        with self.db.transaction() as connection:
            open_row = connection.execute(
                """SELECT id FROM reconciliation_sessions
                   WHERE account_id = ? AND status = 'open' LIMIT 1""",
                (int(account_id),),
            ).fetchone()
            if open_row:
                raise ValueError("Close or discard the existing open reconciliation first.")
            previous = connection.execute(
                """SELECT statement_date, statement_balance_minor
                   FROM reconciliation_sessions
                   WHERE account_id = ? AND status = 'closed'
                   ORDER BY statement_date DESC, id DESC LIMIT 1""",
                (int(account_id),),
            ).fetchone()
            if previous and statement_date <= previous["statement_date"]:
                raise ValueError("The new statement date must be after the last closed statement.")
            opening_balance = (
                int(previous["statement_balance_minor"])
                if previous else int(account["opening_balance_minor"])
            )
            cursor = connection.execute(
                """INSERT INTO reconciliation_sessions(
                    account_id, statement_date, opening_balance_minor,
                    statement_balance_minor, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)""",
                (int(account_id), statement_date, opening_balance,
                 int(statement_balance_minor), notes.strip(), now_iso()),
            )
            session_id = int(cursor.lastrowid)
            candidates = connection.execute(
                """SELECT t.id FROM transactions t
                   WHERE (t.account_id = ? OR t.transfer_account_id = ?)
                     AND t.occurred_on <= ?
                     AND NOT EXISTS (
                       SELECT 1 FROM reconciled_transactions rt
                       WHERE rt.transaction_id = t.id
                     )
                   ORDER BY t.occurred_on, t.id""",
                (int(account_id), int(account_id), statement_date),
            ).fetchall()
            connection.executemany(
                "INSERT INTO reconciliation_items(session_id, transaction_id) VALUES(?, ?)",
                [(session_id, int(row["id"])) for row in candidates],
            )
            return session_id

    def items(self, session_id: int) -> list[dict[str, Any]]:
        session = self.db.fetch_one(
            "SELECT * FROM reconciliation_sessions WHERE id = ?", (int(session_id),)
        )
        if not session:
            raise ValueError("Reconciliation session was not found.")
        rows = self.db.fetch_all(
            """SELECT ri.cleared, t.*, a.name AS account_name,
                      ta.name AS transfer_account_name, c.name AS category_name
               FROM reconciliation_items ri
               JOIN transactions t ON t.id = ri.transaction_id
               JOIN accounts a ON a.id = t.account_id
               LEFT JOIN accounts ta ON ta.id = t.transfer_account_id
               LEFT JOIN categories c ON c.id = t.category_id
               WHERE ri.session_id = ? ORDER BY t.occurred_on, t.id""",
            (int(session_id),),
        )
        result = []
        account_id = int(session["account_id"])
        for row in rows:
            effect = self._account_effect(row, account_id)
            result.append({**dict(row), "signed_amount_minor": effect})
        return result

    @staticmethod
    def _account_effect(transaction: Any, account_id: int) -> int:
        amount = int(transaction["amount_minor"])
        kind = transaction["kind"]
        if kind == "income":
            return amount if int(transaction["account_id"]) == account_id else 0
        if kind == "expense":
            return -amount if int(transaction["account_id"]) == account_id else 0
        if kind == "transfer":
            if int(transaction["account_id"]) == account_id:
                return -amount
            if transaction["transfer_account_id"] is not None and int(transaction["transfer_account_id"]) == account_id:
                return amount
        if kind == "adjustment":
            sign = -1 if "adjustment_sign:-1" in str(transaction["notes"]) else 1
            return amount * sign if int(transaction["account_id"]) == account_id else 0
        return 0

    def set_cleared(self, session_id: int, transaction_id: int, cleared: bool) -> None:
        with self.db.transaction() as connection:
            session = connection.execute(
                "SELECT status FROM reconciliation_sessions WHERE id = ?", (int(session_id),)
            ).fetchone()
            if not session or session["status"] != "open":
                raise ValueError("Only an open reconciliation can be changed.")
            cursor = connection.execute(
                """UPDATE reconciliation_items SET cleared = ?
                   WHERE session_id = ? AND transaction_id = ?""",
                (int(bool(cleared)), int(session_id), int(transaction_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError("Transaction is not part of this reconciliation.")

    def summary(self, session_id: int) -> dict[str, int | str]:
        session = self.db.fetch_one(
            "SELECT * FROM reconciliation_sessions WHERE id = ?", (int(session_id),)
        )
        if not session:
            raise ValueError("Reconciliation session was not found.")
        cleared_total = sum(
            int(item["signed_amount_minor"])
            for item in self.items(session_id) if item["cleared"]
        )
        calculated = int(session["opening_balance_minor"]) + cleared_total
        statement = int(session["statement_balance_minor"])
        return {
            "status": session["status"],
            "opening_balance_minor": int(session["opening_balance_minor"]),
            "cleared_total_minor": cleared_total,
            "calculated_balance_minor": calculated,
            "statement_balance_minor": statement,
            "difference_minor": statement - calculated,
        }

    def close_session(self, session_id: int) -> None:
        with self.db.transaction() as connection:
            session = connection.execute(
                "SELECT * FROM reconciliation_sessions WHERE id = ?", (int(session_id),)
            ).fetchone()
            if not session or session["status"] != "open":
                raise ValueError("Open reconciliation was not found.")
            rows = connection.execute(
                """SELECT ri.transaction_id FROM reconciliation_items ri
                   WHERE ri.session_id = ? AND ri.cleared = 1""",
                (int(session_id),),
            ).fetchall()
            cleared_ids = [int(row["transaction_id"]) for row in rows]
            if cleared_ids:
                connection.executemany(
                    """INSERT INTO reconciled_transactions(transaction_id, session_id, reconciled_at)
                       VALUES(?, ?, ?)""",
                    [(transaction_id, int(session_id), now_iso()) for transaction_id in cleared_ids],
                )
            # Recheck the balance within the same write transaction.
            session_balance = int(session["opening_balance_minor"])
            items = connection.execute(
                """SELECT t.*, ri.cleared FROM reconciliation_items ri
                   JOIN transactions t ON t.id = ri.transaction_id
                   WHERE ri.session_id = ? AND ri.cleared = 1""",
                (int(session_id),),
            ).fetchall()
            for item in items:
                session_balance += self._account_effect(item, int(session["account_id"]))
            difference = int(session["statement_balance_minor"]) - session_balance
            if difference != 0:
                raise ValueError(f"Cannot close: reconciliation difference is {difference} minor units.")
            connection.execute(
                "UPDATE reconciliation_sessions SET status = 'closed', closed_at = ? WHERE id = ?",
                (now_iso(), int(session_id)),
            )

    def discard_open_session(self, session_id: int) -> None:
        with self.db.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM reconciliation_sessions WHERE id = ? AND status = 'open'",
                (int(session_id),),
            )
            if cursor.rowcount != 1:
                raise ValueError("Open reconciliation was not found.")

    def history(self, account_id: int | None = None) -> list[sqlite3.Row]:
        if account_id:
            return self.db.fetch_all(
                """SELECT r.*, a.name AS account_name FROM reconciliation_sessions r
                   JOIN accounts a ON a.id = r.account_id WHERE r.account_id = ?
                   ORDER BY r.statement_date DESC, r.id DESC""",
                (int(account_id),),
            )
        return self.db.fetch_all(
            """SELECT r.*, a.name AS account_name FROM reconciliation_sessions r
               JOIN accounts a ON a.id = r.account_id ORDER BY r.statement_date DESC, r.id DESC"""
        )


class DebtService:
    """Manual debt register and fixed-rate monthly payoff projections."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    @staticmethod
    def monthly_interest(principal_minor: int, apr_basis_points: int) -> int:
        # APR is stored in basis points: 1,250 means 12.50% annually.
        return rounded_division(int(principal_minor) * int(apr_basis_points), 120_000)

    def create_plan(
        self,
        *,
        name: str,
        creditor: str,
        principal_minor: int,
        apr_basis_points: int,
        minimum_payment_minor: int,
        payment_account_id: int,
        due_day: int,
        start_date: str,
        notes: str = "",
    ) -> int:
        if not name.strip():
            raise ValueError("Debt name is required.")
        if principal_minor <= 0:
            raise ValueError("Starting principal must be greater than zero.")
        if apr_basis_points < 0:
            raise ValueError("APR cannot be negative.")
        if minimum_payment_minor <= 0:
            raise ValueError("Minimum payment must be greater than zero.")
        if not 1 <= int(due_day) <= 31:
            raise ValueError("Due day must be between 1 and 31.")
        start_date = validate_date(start_date)
        _validate_account(self.finance, payment_account_id, CASH_ACCOUNT_TYPES)
        interest = self.monthly_interest(principal_minor, apr_basis_points)
        if minimum_payment_minor <= interest:
            raise ValueError("Minimum payment must be greater than the first month's interest.")
        return self.db.execute(
            """INSERT INTO debt_plans(
                name, creditor, original_principal_minor, principal_minor,
                apr_basis_points, minimum_payment_minor, payment_account_id,
                due_day, start_date, notes, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.strip(), creditor.strip(), int(principal_minor), int(principal_minor),
             int(apr_basis_points), int(minimum_payment_minor), int(payment_account_id),
             int(due_day), start_date, notes.strip(), now_iso()),
        )

    def list_plans(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = """SELECT d.*, a.name AS payment_account_name
                 FROM debt_plans d JOIN accounts a ON a.id = d.payment_account_id"""
        if not include_inactive:
            sql += " WHERE d.active = 1"
        return self.db.fetch_all(sql + " ORDER BY d.active DESC, d.name")

    def get_plan(self, debt_plan_id: int) -> sqlite3.Row | None:
        return self.db.fetch_one("SELECT * FROM debt_plans WHERE id = ?", (int(debt_plan_id),))

    def schedule(self, debt_plan_id: int, extra_payment_minor: int = 0, max_months: int = 600) -> list[dict[str, int | str]]:
        plan = self.get_plan(debt_plan_id)
        if not plan:
            raise ValueError("Debt plan was not found.")
        if extra_payment_minor < 0:
            raise ValueError("Extra payment cannot be negative.")
        balance = int(plan["principal_minor"])
        apr = int(plan["apr_basis_points"])
        payment_target = int(plan["minimum_payment_minor"]) + int(extra_payment_minor)
        last_payment = self.db.fetch_one(
            "SELECT payment_date FROM debt_payments WHERE debt_plan_id = ? ORDER BY payment_date DESC, id DESC LIMIT 1",
            (int(debt_plan_id),),
        )
        schedule_anchor = last_payment["payment_date"] if last_payment else plan["start_date"]
        current_date = date.fromisoformat(schedule_anchor)
        rows = []
        total_interest = 0
        for period in range(1, max(1, min(int(max_months), 1200)) + 1):
            if balance <= 0:
                break
            current_date = add_months(current_date, 1, int(plan["due_day"]))
            interest = self.monthly_interest(balance, apr)
            if payment_target <= interest:
                raise ValueError(
                    "The scheduled payment does not cover monthly interest. Increase the payment."
                )
            payment = min(balance + interest, payment_target)
            principal_paid = min(balance, payment - interest)
            closing = max(0, balance - principal_paid)
            total_interest += interest
            rows.append({
                "period": period,
                "date": current_date.isoformat(),
                "opening_minor": balance,
                "interest_minor": interest,
                "payment_minor": payment,
                "principal_minor": principal_paid,
                "closing_minor": closing,
            })
            balance = closing
        return rows

    def record_payment(
        self,
        debt_plan_id: int,
        payment_minor: int | None = None,
        payment_date: str | None = None,
        notes: str = "",
    ) -> dict[str, int]:
        payment_date = validate_date(payment_date or today_iso())
        with self.db.transaction() as connection:
            plan = connection.execute(
                "SELECT * FROM debt_plans WHERE id = ?",
                (int(debt_plan_id),),
            ).fetchone()
            if not plan:
                raise ValueError("Debt plan was not found.")
            balance = int(plan["principal_minor"])
            if balance <= 0:
                raise ValueError("This debt is already paid off.")
            if payment_date < plan["start_date"]:
                raise ValueError("Payment date cannot be earlier than the debt start date.")
            last_payment = connection.execute(
                """SELECT payment_date FROM debt_payments WHERE debt_plan_id = ?
                   ORDER BY payment_date DESC, id DESC LIMIT 1""",
                (int(debt_plan_id),),
            ).fetchone()
            reference_date = date.fromisoformat(
                last_payment["payment_date"] if last_payment else plan["start_date"]
            )
            target_date = date.fromisoformat(payment_date)
            if target_date < reference_date:
                raise ValueError("Payment date cannot be earlier than the previous payment.")
            elapsed_months = (target_date.year - reference_date.year) * 12 + target_date.month - reference_date.month
            if elapsed_months < 0:
                raise ValueError("Payment date cannot be earlier than the previous payment.")
            interest = 0
            accrued_balance = balance
            for _ in range(elapsed_months):
                period_interest = self.monthly_interest(accrued_balance, int(plan["apr_basis_points"]))
                interest += period_interest
                accrued_balance += period_interest
            requested = int(payment_minor if payment_minor is not None else plan["minimum_payment_minor"])
            if requested <= interest:
                raise ValueError(
                    f"Payment must exceed accrued interest ({interest} minor units)."
                )
            actual_payment = min(requested, accrued_balance)
            principal_paid = min(accrued_balance, actual_payment - interest)
            account_id = int(plan["payment_account_id"])
            account = connection.execute(
                "SELECT is_active, kind FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if not account or not account["is_active"] or account["kind"] not in CASH_ACCOUNT_TYPES:
                raise ValueError("The debt plan's payment account is unavailable. Update the debt plan before paying.")
            transaction_id = _insert_transaction(
                connection,
                account_id=account_id,
                kind="expense",
                amount_minor=actual_payment,
                occurred_on=payment_date,
                payee=plan["creditor"] or plan["name"],
                description=f"Debt payment: {plan['name']}",
                notes=notes,
            )
            connection.execute(
                """INSERT INTO debt_payments(
                    debt_plan_id, transaction_id, payment_minor, interest_minor,
                    principal_minor, payment_date, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(debt_plan_id), transaction_id, actual_payment, interest,
                 principal_paid, payment_date, notes.strip(), now_iso()),
            )
            remaining = balance - principal_paid
            connection.execute(
                "UPDATE debt_plans SET principal_minor = ?, active = ? WHERE id = ?",
                (remaining, int(remaining > 0 and bool(plan["active"])), int(debt_plan_id)),
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('debt_plan', ?, 'payment', ?, ?)""",
                (int(debt_plan_id), f"transaction_id={transaction_id}; principal={principal_paid}", now_iso()),
            )
            return {
                "transaction_id": transaction_id,
                "payment_minor": actual_payment,
                "interest_minor": interest,
                "principal_minor": principal_paid,
                "remaining_minor": remaining,
            }

    def payment_history(self, debt_plan_id: int) -> list[sqlite3.Row]:
        return self.db.fetch_all(
            """SELECT * FROM debt_payments WHERE debt_plan_id = ?
               ORDER BY payment_date DESC, id DESC""",
            (int(debt_plan_id),),
        )

    def archive(self, debt_plan_id: int) -> None:
        self.db.execute(
            "UPDATE debt_plans SET active = 0 WHERE id = ?", (int(debt_plan_id),)
        )


class InvestmentService:
    """Manual holdings and trade ledger using weighted-average cost basis."""

    QUANTITY_SCALE = 1_000_000

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db

    def create_security(
        self, symbol: str, name: str, asset_type: str = "stock", currency: str = "USD"
    ) -> int:
        symbol = symbol.strip().upper()
        if not symbol or len(symbol) > 20:
            raise ValueError("Enter a valid security symbol (1–20 characters).")
        if not name.strip():
            raise ValueError("Security name is required.")
        if not currency or len(currency.strip()) != 3 or not currency.isalpha():
            raise ValueError("Currency must be a three-letter code.")
        allowed = {"stock", "etf", "mutual_fund", "bond", "crypto", "other"}
        if asset_type not in allowed:
            raise ValueError("Choose a supported asset type.")
        return self.db.execute(
            """INSERT INTO investment_securities(symbol, name, asset_type, currency, created_at)
               VALUES(?, ?, ?, ?, ?)""",
            (symbol, name.strip(), asset_type, currency.upper(), now_iso()),
        )

    def securities(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM investment_securities"
        if not include_inactive:
            sql += " WHERE active = 1"
        return self.db.fetch_all(sql + " ORDER BY symbol")

    def update_price(self, security_id: int, price_minor: int) -> None:
        if price_minor < 0:
            raise ValueError("Market price cannot be negative.")
        existing = self.db.fetch_one(
            "SELECT id FROM investment_securities WHERE id = ?", (int(security_id),)
        )
        if not existing:
            raise ValueError("Security was not found.")
        self.db.execute(
            """UPDATE investment_securities
               SET last_price_minor = ?, price_updated_at = ? WHERE id = ?""",
            (int(price_minor), now_iso(), int(security_id)),
        )

    def _holdings_for_pair(self, account_id: int, security_id: int) -> dict[str, int]:
        trades = self.db.fetch_all(
            """SELECT side, quantity_micros, price_minor, commission_minor, gross_minor
               FROM investment_trades WHERE investment_account_id = ? AND security_id = ?
               ORDER BY trade_date, id""",
            (int(account_id), int(security_id)),
        )
        quantity = 0
        cost_basis = 0
        realized = 0
        for trade in trades:
            qty = int(trade["quantity_micros"])
            gross = int(trade["gross_minor"])
            commission = int(trade["commission_minor"])
            if trade["side"] == "buy":
                quantity += qty
                cost_basis += gross + commission
            else:
                if qty > quantity:
                    raise ValueError("Investment ledger contains a sale greater than holdings.")
                proceeds = gross - commission
                removed_cost = rounded_division(cost_basis * qty, quantity)
                realized += proceeds - removed_cost
                quantity -= qty
                cost_basis -= removed_cost
        return {"quantity_micros": quantity, "cost_basis_minor": cost_basis, "realized_minor": realized}

    def record_trade(
        self,
        *,
        investment_account_id: int,
        security_id: int,
        side: str,
        quantity_micros: int,
        price_minor: int,
        commission_minor: int = 0,
        trade_date: str | None = None,
        notes: str = "",
    ) -> dict[str, int]:
        if side not in {"buy", "sell"}:
            raise ValueError("Trade side must be buy or sell.")
        if quantity_micros <= 0 or price_minor <= 0:
            raise ValueError("Quantity and price must be greater than zero.")
        if commission_minor < 0:
            raise ValueError("Commission cannot be negative.")
        trade_date = validate_date(trade_date or today_iso())
        account = _validate_account(self.finance, investment_account_id, {"investment"})
        security = self.db.fetch_one(
            "SELECT * FROM investment_securities WHERE id = ? AND active = 1", (int(security_id),)
        )
        if not security:
            raise ValueError("Active security was not found.")
        if account["currency"] != security["currency"]:
            raise ValueError("Investment account and security must use the same currency.")
        gross = rounded_division(int(quantity_micros) * int(price_minor), self.QUANTITY_SCALE)
        if gross <= 0:
            raise ValueError("Trade value is too small for the selected quantity and price.")
        holding = self._holdings_for_pair(int(investment_account_id), int(security_id))
        if side == "sell" and quantity_micros > holding["quantity_micros"]:
            raise ValueError("You cannot sell more shares than are currently held.")
        if side == "sell" and gross <= commission_minor:
            raise ValueError("Sale proceeds must be greater than the commission.")
        cash_amount = gross + commission_minor if side == "buy" else gross - commission_minor
        if side == "buy":
            available_cash = self.finance.account_balance(int(investment_account_id))
            if cash_amount > available_cash:
                raise ValueError(
                    f"Insufficient investment-account cash. Available: {available_cash} minor units."
                )
        description = f"Investment {side}: {quantity_micros / self.QUANTITY_SCALE:g} {security['symbol']}"
        with self.db.transaction() as connection:
            transaction_id = _insert_transaction(
                connection,
                account_id=int(investment_account_id),
                kind="expense" if side == "buy" else "income",
                amount_minor=cash_amount,
                occurred_on=trade_date,
                payee=security["symbol"],
                description=description,
                notes=notes,
            )
            cursor = connection.execute(
                """INSERT INTO investment_trades(
                    investment_account_id, security_id, side, quantity_micros,
                    price_minor, commission_minor, gross_minor, transaction_id,
                    trade_date, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(investment_account_id), int(security_id), side,
                 int(quantity_micros), int(price_minor), int(commission_minor),
                 gross, transaction_id, trade_date, notes.strip(), now_iso()),
            )
            trade_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('investment_trade', ?, ?, ?, ?)""",
                (trade_id, side, description, now_iso()),
            )
        return {"trade_id": trade_id, "transaction_id": transaction_id,
                "gross_minor": gross, "cash_amount_minor": cash_amount}

    def holdings(self) -> list[dict[str, Any]]:
        pairs = self.db.fetch_all(
            """SELECT DISTINCT it.investment_account_id, it.security_id,
                      a.name AS account_name, s.symbol, s.name AS security_name,
                      s.currency, s.last_price_minor, s.price_updated_at
               FROM investment_trades it
               JOIN accounts a ON a.id = it.investment_account_id
               JOIN investment_securities s ON s.id = it.security_id
               ORDER BY a.name, s.symbol"""
        )
        result = []
        for pair in pairs:
            holding = self._holdings_for_pair(pair["investment_account_id"], pair["security_id"])
            if holding["quantity_micros"] <= 0:
                continue
            market_value = rounded_division(
                holding["quantity_micros"] * int(pair["last_price_minor"]), self.QUANTITY_SCALE
            )
            result.append({
                **dict(pair), **holding,
                "market_value_minor": market_value,
                "unrealized_minor": market_value - holding["cost_basis_minor"],
                "average_cost_minor": rounded_division(
                    holding["cost_basis_minor"] * self.QUANTITY_SCALE,
                    holding["quantity_micros"],
                ),
            })
        return result

    def trades(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.db.fetch_all(
            """SELECT it.*, a.name AS account_name, s.symbol, s.name AS security_name
               FROM investment_trades it
               JOIN accounts a ON a.id = it.investment_account_id
               JOIN investment_securities s ON s.id = it.security_id
               ORDER BY it.trade_date DESC, it.id DESC LIMIT ?""",
            (max(1, min(int(limit), 5000)),),
        )

    def summary(self) -> dict[str, int]:
        holdings = self.holdings()
        all_pairs = self.db.fetch_all(
            "SELECT DISTINCT investment_account_id, security_id FROM investment_trades"
        )
        realized_total = sum(
            self._holdings_for_pair(row["investment_account_id"], row["security_id"])["realized_minor"]
            for row in all_pairs
        )
        return {
            "market_value_minor": sum(int(row["market_value_minor"]) for row in holdings),
            "cost_basis_minor": sum(int(row["cost_basis_minor"]) for row in holdings),
            "unrealized_minor": sum(int(row["unrealized_minor"]) for row in holdings),
            "realized_minor": realized_total,
        }


class NetWorthService:
    """Point-in-time personal net-worth calculation and snapshots."""

    def __init__(self, finance, investments: InvestmentService | None = None):
        self.finance = finance
        self.db = finance.db
        self.investments = investments or InvestmentService(finance)

    def current_position(self) -> dict[str, Any]:
        accounts = []
        for account in self.finance.accounts.list(include_inactive=True):
            accounts.append({
                "id": int(account["id"]),
                "name": account["name"],
                "kind": account["kind"],
                "currency": account["currency"],
                "is_active": int(account["is_active"]),
                "balance_minor": self.finance._account_balance_from_row(account),
            })
        assets = 0
        liabilities = 0
        account_details = []
        for account in accounts:
            balance = int(account["balance_minor"])
            if account["kind"] in LIABILITY_ACCOUNT_TYPES:
                liabilities += max(0, -balance)
                assets += max(0, balance)
            else:
                assets += max(0, balance)
                liabilities += max(0, -balance)
            account_details.append({**account, "balance_minor": balance})
        investment_summary = self.investments.summary()
        assets += int(investment_summary["market_value_minor"])
        debts = self.db.fetch_all(
            "SELECT id, name, principal_minor FROM debt_plans WHERE principal_minor > 0"
        )
        debt_total = sum(int(row["principal_minor"]) for row in debts)
        liabilities += debt_total
        return {
            "assets_minor": assets,
            "liabilities_minor": liabilities,
            "net_worth_minor": assets - liabilities,
            "accounts": account_details,
            "investment_market_value_minor": int(investment_summary["market_value_minor"]),
            "debts": [dict(row) for row in debts],
            "debt_total_minor": debt_total,
        }

    def save_snapshot(self, snapshot_date: str | None = None, notes: str = "") -> int:
        snapshot_date = validate_date(snapshot_date or today_iso())
        position = self.current_position()
        details = {
            "accounts": position["accounts"],
            "debts": position["debts"],
            "investment_market_value_minor": position["investment_market_value_minor"],
        }
        with self.db.transaction() as connection:
            connection.execute(
                """INSERT INTO net_worth_snapshots(
                    snapshot_date, assets_minor, liabilities_minor, net_worth_minor,
                    details_json, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date) DO UPDATE SET
                    assets_minor = excluded.assets_minor,
                    liabilities_minor = excluded.liabilities_minor,
                    net_worth_minor = excluded.net_worth_minor,
                    details_json = excluded.details_json,
                    notes = excluded.notes""",
                (snapshot_date, position["assets_minor"], position["liabilities_minor"],
                 position["net_worth_minor"], json.dumps(details, default=str),
                 notes.strip(), now_iso()),
            )
            row = connection.execute(
                "SELECT id FROM net_worth_snapshots WHERE snapshot_date = ?", (snapshot_date,)
            ).fetchone()
            snapshot_id = int(row["id"])
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('net_worth_snapshot', ?, 'save', ?, ?)""",
                (snapshot_id, snapshot_date, now_iso()),
            )
            return snapshot_id

    def snapshots(self, limit: int = 120) -> list[sqlite3.Row]:
        return self.db.fetch_all(
            "SELECT * FROM net_worth_snapshots ORDER BY snapshot_date DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        )

    def delete_snapshot(self, snapshot_id: int) -> None:
        self.db.execute("DELETE FROM net_worth_snapshots WHERE id = ?", (int(snapshot_id),))


class MaintenanceService:
    """Local database health checks and audit-log browsing."""

    def __init__(self, db):
        self.db = db

    def integrity_report(self) -> dict[str, Any]:
        connection = self.db.connect()
        try:
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
            foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            tables = connection.execute(
                """SELECT name FROM sqlite_master WHERE type = 'table'
                   AND name NOT LIKE 'sqlite_%' ORDER BY name"""
            ).fetchall()
            counts = {}
            for row in tables:
                table = row["name"]
                # Table names originate from sqlite_master, not user input.
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            return {
                "integrity": [str(row[0]) for row in integrity_rows],
                "foreign_key_issues": [tuple(row) for row in foreign_key_rows],
                "table_counts": counts,
                "database_path": str(self.db.path),
            }
        finally:
            connection.close()

    def audit_entries(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.db.fetch_all(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 5000)),),
        )


class CashFlowForecastService:
    """Project future recurring entries and bill reminders without posting them."""

    def __init__(self, finance):
        self.finance = finance
        self.db = finance.db
        self.recurring = RecurringTransactionService(finance)

    def _account_balance_at(self, account_id: int, as_of: str) -> int:
        account = self.finance.accounts.get(int(account_id))
        if not account:
            raise ValueError("Account was not found.")
        rows = self.db.fetch_all(
            """SELECT kind, amount_minor, account_id, transfer_account_id, notes
               FROM transactions
               WHERE (account_id = ? OR transfer_account_id = ?) AND occurred_on <= ?
               ORDER BY occurred_on, id""",
            (int(account_id), int(account_id), as_of),
        )
        balance = int(account["opening_balance_minor"])
        for row in rows:
            amount = int(row["amount_minor"])
            if row["kind"] == "income" and int(row["account_id"]) == int(account_id):
                balance += amount
            elif row["kind"] == "expense" and int(row["account_id"]) == int(account_id):
                balance -= amount
            elif row["kind"] == "transfer":
                if int(row["account_id"]) == int(account_id):
                    balance -= amount
                elif row["transfer_account_id"] is not None and int(row["transfer_account_id"]) == int(account_id):
                    balance += amount
            elif row["kind"] == "adjustment" and int(row["account_id"]) == int(account_id):
                balance += amount * (-1 if "adjustment_sign:-1" in str(row["notes"]) else 1)
        return balance

    def project(self, days: int = 90, as_of: str | None = None) -> dict[str, Any]:
        if not 1 <= int(days) <= 3650:
            raise ValueError("Forecast horizon must be between 1 and 3,650 days.")
        as_of = validate_date(as_of or today_iso())
        start = date.fromisoformat(as_of)
        end = start + timedelta(days=int(days))
        end_iso = end.isoformat()
        balances = {
            int(account["id"]): self._account_balance_at(int(account["id"]), as_of)
            for account in self.finance.accounts.list()
        }
        account_names = {
            int(account["id"]): account["name"] for account in self.finance.accounts.list()
        }
        events: list[dict[str, Any]] = []

        for row in self.recurring.list():
            due = date.fromisoformat(row["next_due_date"])
            anchor = int(row["anchor_day"])
            while due <= end:
                if row["end_date"] and due.isoformat() > row["end_date"]:
                    break
                overdue = due < start
                projected_date = start if overdue else due
                events.append({
                    "date": projected_date.isoformat(),
                    "due_date": due.isoformat(),
                    "source_type": "recurring",
                    "source_id": int(row["id"]),
                    "name": row["name"],
                    "kind": row["kind"],
                    "amount_minor": int(row["amount_minor"]),
                    "account_id": int(row["account_id"]),
                    "account_name": account_names.get(int(row["account_id"]), "Archived account"),
                    "overdue": overdue,
                })
                due = date.fromisoformat(advance_date(due.isoformat(), row["frequency"], anchor))

        bills = self.finance.bills.list()
        for row in bills:
            due = date.fromisoformat(row["next_due_date"])
            anchor = int(row["due_day"])
            while due <= end:
                overdue = due < start
                projected_date = start if overdue else due
                account_id = int(row["account_id"]) if row["account_id"] else None
                events.append({
                    "date": projected_date.isoformat(),
                    "due_date": due.isoformat(),
                    "source_type": "bill",
                    "source_id": int(row["id"]),
                    "name": row["name"],
                    "kind": "expense",
                    "amount_minor": int(row["amount_minor"]),
                    "account_id": account_id,
                    "account_name": account_names.get(account_id, "Not assigned") if account_id else "Not assigned",
                    "overdue": overdue,
                })
                due = date.fromisoformat(advance_date(due.isoformat(), row["frequency"], anchor))

        events.sort(key=lambda item: (item["date"], item["due_date"], item["name"].casefold()))
        projected_income = 0
        projected_expenses = 0
        for event in events:
            amount = int(event["amount_minor"])
            if event["kind"] == "income":
                projected_income += amount
                sign = 1
            else:
                projected_expenses += amount
                sign = -1
            account_id = event["account_id"]
            if account_id is not None and account_id in balances:
                balances[account_id] += sign * amount
            event["projected_balance_minor"] = balances.get(account_id) if account_id is not None else None

        return {
            "as_of": as_of,
            "end_date": end_iso,
            "days": int(days),
            "projected_income_minor": projected_income,
            "projected_expenses_minor": projected_expenses,
            "projected_net_minor": projected_income - projected_expenses,
            "events": events,
            "ending_balances": [
                {"account_id": account_id, "account_name": account_names[account_id],
                 "balance_minor": balance}
                for account_id, balance in balances.items()
            ],
        }
