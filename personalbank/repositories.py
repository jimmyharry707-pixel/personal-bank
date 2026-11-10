from __future__ import annotations

import sqlite3
from typing import Any

from .db import Database
from .domain import now_iso


class BaseRepository:
    def __init__(self, db: Database):
        self.db = db

    def audit(self, connection: sqlite3.Connection, entity: str, entity_id: int | None,
              action: str, details: str = "") -> None:
        connection.execute(
            "INSERT INTO audit_log(entity, entity_id, action, details, created_at) VALUES(?, ?, ?, ?, ?)",
            (entity, entity_id, action, details, now_iso()),
        )


class AccountRepository(BaseRepository):
    def list(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM accounts"
        if not include_inactive:
            sql += " WHERE is_active = 1"
        return self.db.fetch_all(sql + " ORDER BY name COLLATE NOCASE")

    def get(self, account_id: int) -> sqlite3.Row | None:
        return self.db.fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,))

    def create(self, name: str, kind: str, currency: str, opening_balance_minor: int,
               credit_limit_minor: int = 0) -> int:
        with self.db.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO accounts(name, kind, currency, opening_balance_minor,
                   credit_limit_minor, created_at) VALUES(?, ?, ?, ?, ?, ?)""",
                (name.strip(), kind, currency.upper(), opening_balance_minor,
                 credit_limit_minor, now_iso()),
            )
            account_id = int(cursor.lastrowid)
            self.audit(connection, "account", account_id, "create", name.strip())
            return account_id

    def update(self, account_id: int, **fields: Any) -> None:
        allowed = {"name", "kind", "currency", "opening_balance_minor", "credit_limit_minor", "is_active"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if "name" in values:
            values["name"] = str(values["name"]).strip()
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.db.transaction() as connection:
            connection.execute(
                f"UPDATE accounts SET {assignments} WHERE id = ?",
                (*values.values(), account_id),
            )
            self.audit(connection, "account", account_id, "update", ",".join(values.keys()))

    def archive(self, account_id: int) -> None:
        with self.db.transaction() as connection:
            connection.execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (account_id,))
            self.audit(connection, "account", account_id, "archive")


class CategoryRepository(BaseRepository):
    def list(self, kind: str | None = None, include_inactive: bool = False) -> list[sqlite3.Row]:
        clauses, params = [], []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if not include_inactive:
            clauses.append("is_active = 1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return self.db.fetch_all(
            "SELECT * FROM categories" + where + " ORDER BY kind, name COLLATE NOCASE",
            tuple(params),
        )

    def create(self, name: str, kind: str, color: str = "#64748b") -> int:
        return self.db.execute(
            "INSERT INTO categories(name, kind, color) VALUES(?, ?, ?)",
            (name.strip(), kind, color),
        )

    def update(self, category_id: int, name: str, color: str) -> None:
        self.db.execute(
            "UPDATE categories SET name = ?, color = ? WHERE id = ?",
            (name.strip(), color, category_id),
        )

    def archive(self, category_id: int) -> None:
        self.db.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (category_id,))


class TransactionRepository(BaseRepository):
    def list(self, start_date: str | None = None, end_date: str | None = None,
             account_id: int | None = None, kind: str | None = None,
             search: str = "", limit: int = 1000) -> list[sqlite3.Row]:
        clauses, params = [], []
        if start_date:
            clauses.append("t.occurred_on >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("t.occurred_on <= ?")
            params.append(end_date)
        if account_id:
            clauses.append("(t.account_id = ? OR t.transfer_account_id = ?)")
            params.extend([account_id, account_id])
        if kind:
            clauses.append("t.kind = ?")
            params.append(kind)
        if search.strip():
            pattern = f"%{search.strip()}%"
            clauses.append("(t.payee LIKE ? OR t.description LIKE ? OR t.reference LIKE ? OR t.notes LIKE ?)")
            params.extend([pattern] * 4)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 10000)))
        return self.db.fetch_all(
            """SELECT t.*, a.name AS account_name, ta.name AS transfer_account_name,
                      c.name AS category_name
               FROM transactions t
               JOIN accounts a ON a.id = t.account_id
               LEFT JOIN accounts ta ON ta.id = t.transfer_account_id
               LEFT JOIN categories c ON c.id = t.category_id"""
            + where + " ORDER BY t.occurred_on DESC, t.id DESC LIMIT ?",
            tuple(params),
        )

    def get(self, transaction_id: int) -> sqlite3.Row | None:
        return self.db.fetch_one("SELECT * FROM transactions WHERE id = ?", (transaction_id,))

    def create(self, *, account_id: int, transfer_account_id: int | None,
               category_id: int | None, kind: str, amount_minor: int,
               occurred_on: str, payee: str = "", description: str = "",
               reference: str = "", notes: str = "") -> int:
        timestamp = now_iso()
        with self.db.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO transactions(
                    account_id, transfer_account_id, category_id, kind, amount_minor,
                    occurred_on, payee, description, reference, notes, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, transfer_account_id, category_id, kind, amount_minor,
                 occurred_on, payee.strip(), description.strip(), reference.strip(),
                 notes.strip(), timestamp, timestamp),
            )
            transaction_id = int(cursor.lastrowid)
            self.audit(connection, "transaction", transaction_id, "create", kind)
            return transaction_id

    def update(self, transaction_id: int, **fields: Any) -> None:
        allowed = {
            "account_id", "transfer_account_id", "category_id", "kind", "amount_minor",
            "occurred_on", "payee", "description", "reference", "notes",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        values["updated_at"] = now_iso()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.db.transaction() as connection:
            connection.execute(
                f"UPDATE transactions SET {assignments} WHERE id = ?",
                (*values.values(), transaction_id),
            )
            self.audit(connection, "transaction", transaction_id, "update")

    def delete(self, transaction_id: int) -> None:
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            self.audit(connection, "transaction", transaction_id, "delete")


class BudgetRepository(BaseRepository):
    def list(self, month: str) -> list[sqlite3.Row]:
        return self.db.fetch_all(
            """SELECT b.*, c.name AS category_name, c.color AS category_color
               FROM budgets b JOIN categories c ON c.id = b.category_id
               WHERE b.month = ? ORDER BY c.name COLLATE NOCASE""",
            (month,),
        )

    def upsert(self, category_id: int, month: str, limit_minor: int) -> int:
        with self.db.transaction() as connection:
            connection.execute(
                """INSERT INTO budgets(category_id, month, limit_minor) VALUES(?, ?, ?)
                   ON CONFLICT(category_id, month) DO UPDATE SET limit_minor = excluded.limit_minor""",
                (category_id, month, limit_minor),
            )
            row = connection.execute(
                "SELECT id FROM budgets WHERE category_id = ? AND month = ?",
                (category_id, month),
            ).fetchone()
            budget_id = int(row["id"])
            self.audit(connection, "budget", budget_id, "upsert", month)
            return budget_id

    def delete(self, budget_id: int) -> None:
        self.db.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))


class BillRepository(BaseRepository):
    def list(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = """SELECT b.*, c.name AS category_name, a.name AS account_name
                 FROM bills b LEFT JOIN categories c ON c.id = b.category_id
                 LEFT JOIN accounts a ON a.id = b.account_id"""
        if not include_inactive:
            sql += " WHERE b.active = 1"
        return self.db.fetch_all(sql + " ORDER BY b.next_due_date, b.name")

    def create(self, *, name: str, amount_minor: int, due_day: int,
               category_id: int | None, account_id: int | None,
               frequency: str, auto_post: bool, next_due_date: str,
               notes: str = "") -> int:
        return self.db.execute(
            """INSERT INTO bills(name, amount_minor, due_day, category_id, account_id,
               frequency, auto_post, next_due_date, notes)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.strip(), amount_minor, due_day, category_id, account_id,
             frequency, int(auto_post), next_due_date, notes.strip()),
        )

    def update(self, bill_id: int, **fields: Any) -> None:
        allowed = {
            "name", "amount_minor", "due_day", "category_id", "account_id",
            "frequency", "auto_post", "active", "next_due_date", "notes",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.db.execute(
            f"UPDATE bills SET {assignments} WHERE id = ?",
            (*values.values(), bill_id),
        )

    def delete(self, bill_id: int) -> None:
        self.db.execute("DELETE FROM bills WHERE id = ?", (bill_id,))


class GoalRepository(BaseRepository):
    def list(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM savings_goals"
        if not include_inactive:
            sql += " WHERE active = 1"
        return self.db.fetch_all(sql + " ORDER BY active DESC, name COLLATE NOCASE")

    def create(self, name: str, target_minor: int, target_date: str | None, notes: str) -> int:
        return self.db.execute(
            "INSERT INTO savings_goals(name, target_minor, target_date, notes) VALUES(?, ?, ?, ?)",
            (name.strip(), target_minor, target_date, notes.strip()),
        )

    def update(self, goal_id: int, **fields: Any) -> None:
        allowed = {"name", "target_minor", "target_date", "notes", "active"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.db.execute(
            f"UPDATE savings_goals SET {assignments} WHERE id = ?",
            (*values.values(), goal_id),
        )

    def add_contribution(self, goal_id: int, amount_minor: int) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE savings_goals SET current_minor = current_minor + ? WHERE id = ?",
                (amount_minor, goal_id),
            )
            self.audit(connection, "goal", goal_id, "contribution", str(amount_minor))

    def delete(self, goal_id: int) -> None:
        self.db.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            """INSERT INTO settings(key, value) VALUES(?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
