from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Any


SCHEMA_VERSION = 5


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    kind TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    opening_balance_minor INTEGER NOT NULL DEFAULT 0,
    credit_limit_minor INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    color TEXT NOT NULL DEFAULT '#64748b',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE(name, kind)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    transfer_account_id INTEGER REFERENCES accounts(id),
    category_id INTEGER REFERENCES categories(id),
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense', 'transfer', 'adjustment')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    occurred_on TEXT NOT NULL,
    payee TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    reference TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transaction_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 26214400),
    content BLOB NOT NULL CHECK (length(content) = size_bytes),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    month TEXT NOT NULL,
    limit_minor INTEGER NOT NULL CHECK (limit_minor >= 0),
    UNIQUE(category_id, month)
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    category_id INTEGER REFERENCES categories(id),
    account_id INTEGER REFERENCES accounts(id),
    frequency TEXT NOT NULL,
    auto_post INTEGER NOT NULL DEFAULT 0 CHECK (auto_post IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    next_due_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_minor INTEGER NOT NULL CHECK (target_minor > 0),
    current_minor INTEGER NOT NULL DEFAULT 0 CHECK (current_minor >= 0),
    target_date TEXT,
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- Reusable income and expense schedules. Posting is always user-confirmed.
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER REFERENCES categories(id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    payee TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    frequency TEXT NOT NULL,
    anchor_day INTEGER NOT NULL DEFAULT 1 CHECK (anchor_day BETWEEN 1 AND 31),
    next_due_date TEXT NOT NULL,
    end_date TEXT,
    last_posted_on TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- Reconciliation sessions retain the bank statement balance and the items
-- explicitly checked by the user. Cleared transactions are linked separately.
CREATE TABLE IF NOT EXISTS reconciliation_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    statement_date TEXT NOT NULL,
    opening_balance_minor INTEGER NOT NULL,
    statement_balance_minor INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS reconciliation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES reconciliation_sessions(id) ON DELETE CASCADE,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    cleared INTEGER NOT NULL DEFAULT 0 CHECK (cleared IN (0, 1)),
    UNIQUE(session_id, transaction_id)
);
CREATE TABLE IF NOT EXISTS reconciled_transactions (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL REFERENCES reconciliation_sessions(id) ON DELETE CASCADE,
    reconciled_at TEXT NOT NULL
);

-- Debt plans are manual tracking records; they do not connect to lenders.
CREATE TABLE IF NOT EXISTS debt_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    creditor TEXT NOT NULL DEFAULT '',
    original_principal_minor INTEGER NOT NULL CHECK (original_principal_minor > 0),
    principal_minor INTEGER NOT NULL CHECK (principal_minor >= 0),
    apr_basis_points INTEGER NOT NULL DEFAULT 0 CHECK (apr_basis_points >= 0),
    minimum_payment_minor INTEGER NOT NULL CHECK (minimum_payment_minor > 0),
    payment_account_id INTEGER NOT NULL REFERENCES accounts(id),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    start_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS debt_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_plan_id INTEGER NOT NULL REFERENCES debt_plans(id),
    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
    payment_minor INTEGER NOT NULL CHECK (payment_minor > 0),
    interest_minor INTEGER NOT NULL CHECK (interest_minor >= 0),
    principal_minor INTEGER NOT NULL CHECK (principal_minor >= 0),
    payment_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- Prices are entered manually. No quote provider or trading connection exists.
CREATE TABLE IF NOT EXISTS investment_securities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    currency TEXT NOT NULL DEFAULT 'USD',
    last_price_minor INTEGER NOT NULL DEFAULT 0 CHECK (last_price_minor >= 0),
    price_updated_at TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS investment_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investment_account_id INTEGER NOT NULL REFERENCES accounts(id),
    security_id INTEGER NOT NULL REFERENCES investment_securities(id),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity_micros INTEGER NOT NULL CHECK (quantity_micros > 0),
    price_minor INTEGER NOT NULL CHECK (price_minor > 0),
    commission_minor INTEGER NOT NULL DEFAULT 0 CHECK (commission_minor >= 0),
    gross_minor INTEGER NOT NULL CHECK (gross_minor > 0),
    transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions(id),
    trade_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL UNIQUE,
    assets_minor INTEGER NOT NULL,
    liabilities_minor INTEGER NOT NULL,
    net_worth_minor INTEGER NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_currency TEXT NOT NULL CHECK (length(from_currency) = 3),
    to_currency TEXT NOT NULL CHECK (length(to_currency) = 3),
    rate TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (from_currency <> to_currency),
    UNIQUE(from_currency, to_currency)
);


-- Subscription contracts are reminders only; renewal posting is user-confirmed.
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT '',
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'biweekly', 'monthly', 'quarterly', 'yearly')),
    next_renewal_date TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    account_id INTEGER REFERENCES accounts(id),
    trial_end_date TEXT,
    cancel_by_date TEXT,
    website_url TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    last_renewed_on TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscription_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    old_amount_minor INTEGER,
    new_amount_minor INTEGER NOT NULL CHECK (new_amount_minor > 0),
    effective_date TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

-- Personal tax annotations are recordkeeping labels, not tax calculations/advice.
CREATE TABLE IF NOT EXISTS transaction_tax_records (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    tax_year INTEGER NOT NULL,
    treatment TEXT NOT NULL,
    tax_category TEXT NOT NULL,
    deductible_basis_points INTEGER NOT NULL DEFAULT 0
        CHECK (deductible_basis_points BETWEEN 0 AND 10000),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Keyword rules only categorize transactions that currently have no category.
CREATE TABLE IF NOT EXISTS categorization_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    match_field TEXT NOT NULL CHECK (match_field IN ('payee', 'description', 'any')),
    transaction_kind TEXT NOT NULL CHECK (transaction_kind IN ('income', 'expense')),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    priority INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_renewal ON subscriptions(active, next_renewal_date);
CREATE INDEX IF NOT EXISTS idx_subscription_price_history ON subscription_price_history(subscription_id, effective_date);
CREATE INDEX IF NOT EXISTS idx_tax_records_year ON transaction_tax_records(tax_year, treatment);
CREATE INDEX IF NOT EXISTS idx_categorization_rules_priority ON categorization_rules(active, priority DESC, id);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(occurred_on);
CREATE INDEX IF NOT EXISTS idx_transactions_account_date ON transactions(account_id, occurred_on);
CREATE INDEX IF NOT EXISTS idx_transactions_category_date ON transactions(category_id, occurred_on);
CREATE INDEX IF NOT EXISTS idx_transaction_attachments_transaction ON transaction_attachments(transaction_id, created_at);
CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month);
CREATE INDEX IF NOT EXISTS idx_bills_due ON bills(next_due_date, active);
CREATE INDEX IF NOT EXISTS idx_recurring_due ON recurring_transactions(next_due_date, active);
CREATE INDEX IF NOT EXISTS idx_reconciliation_account ON reconciliation_sessions(account_id, statement_date);
CREATE INDEX IF NOT EXISTS idx_debt_active ON debt_plans(active, name);
CREATE INDEX IF NOT EXISTS idx_investment_trade_security ON investment_trades(security_id, trade_date, id);
CREATE INDEX IF NOT EXISTS idx_investment_trade_account ON investment_trades(investment_account_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_net_worth_date ON net_worth_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_exchange_rates_pair ON exchange_rates(from_currency, to_currency);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._seed_defaults(connection)
            connection.commit()
        finally:
            connection.close()

    def _seed_defaults(self, connection: sqlite3.Connection) -> None:
        defaults = [
            ("Salary", "income", "#16a34a"),
            ("Interest", "income", "#0d9488"),
            ("Other income", "income", "#0891b2"),
            ("Housing", "expense", "#dc2626"),
            ("Groceries", "expense", "#ea580c"),
            ("Transport", "expense", "#d97706"),
            ("Utilities", "expense", "#ca8a04"),
            ("Healthcare", "expense", "#db2777"),
            ("Dining", "expense", "#9333ea"),
            ("Shopping", "expense", "#7c3aed"),
            ("Entertainment", "expense", "#2563eb"),
            ("Education", "expense", "#0284c7"),
            ("Insurance", "expense", "#475569"),
            ("Other expense", "expense", "#64748b"),
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO categories(name, kind, color) VALUES(?, ?, ?)",
            defaults,
        )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        connection = self.connect()
        try:
            return list(connection.execute(sql, params).fetchall())
        finally:
            connection.close()

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        connection = self.connect()
        try:
            return connection.execute(sql, params).fetchone()
        finally:
            connection.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, params)
            return int(cursor.lastrowid or 0)
