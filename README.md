# PersonalBank

PersonalBank is a local-only personal banking and financial management desktop application built with **Python**, **PyQt6**, and **SQLite**. It is designed for one person to manually maintain a useful picture of their accounts, spending, savings, debt, and investments.

It is a personal recordkeeping tool, not a bank, payment processor, brokerage, lender, or online banking client.

## What is included

### Core banking and budgeting

- Dashboard with current account balances, monthly income and expenses, net cash flow, category spending, and recent activity.
- Multiple local accounts: checking, savings, cash, credit card, investment, loan, and other.
- Income, expense, transfer, and balance-adjustment transactions.
- Transaction search, edit, delete, CSV import, and CSV export.
- Income and expense categories with archive support.
- Monthly category budgets with spent, remaining, and utilization values.
- Recurring bill reminders and manual payment recording.
- Monthly finance calendar for bill due dates, recurring transactions, and subscription renewals, with overdue items highlighted. The calendar is read-only.
- Savings goals and contribution tracking.

### Advanced finance management

- **Recurring transactions:** reusable income and expense templates with weekly, biweekly, monthly, quarterly, and yearly schedules. Posting always requires confirmation.
- **Cash-flow forecast:** projects active recurring schedules and bills over a selectable horizon. Overdue items are identified. Forecasts never post transactions.
- **Bank reconciliation:** compare an account ledger with a statement ending balance, select cleared transactions, and close only when the difference is zero.
- **Debt planner:** track principal, creditor, APR, minimum payment, payment history, and estimated amortization schedules. Recording a payment creates a corresponding local expense transaction.
- **Investment portfolio:** define securities, record buy/sell trades, enter market prices manually, and calculate holdings, weighted-average cost basis, realized gains, and unrealized gains/losses.
- **Net worth:** estimate assets and liabilities and preserve dated snapshots.
- **Activity log:** browse application audit events and run SQLite integrity and foreign-key checks.

### Personal finance productivity

- **Subscription manager:** track recurring services, trial-end dates, cancellation deadlines, renewal dates, and price history. Monthly and annual equivalent costs are calculated for planning.
- **Tax recordkeeping:** annotate income and expense transactions with user-defined tax treatments, categories, and deductible percentages. View annual summaries and export a tax-record CSV. This is not tax advice or a tax-return calculator.
- **Auto-categorization rules:** create keyword rules for payees or descriptions. Rules run only when explicitly requested and only on uncategorized income and expense transactions. Higher-priority rules win, and existing categories are never overwritten.

### Local data management

- SQLite database with foreign keys, indexes, write-ahead logging, and transaction boundaries.
- Monetary amounts stored as integer minor units rather than binary floating-point values.
- Database backup and restore.
- Currency display preference.
- No server, cloud account, API key, or internet connection is required to use the app.

## Requirements

- Python 3.10 or newer
- PyQt6 6.6 or newer

## Run from source

```bash
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python -m personalbank
```

On Windows, you can also run `install_windows.bat` once and then start the app with `run_windows.bat`. On macOS/Linux, after creating `.venv` and installing requirements, use `./run_unix.sh`.

The first launch creates the SQLite database and seeds standard income and expense categories. No accounts or sample transactions are created automatically.

## Run automated tests

```bash
python -m unittest discover -s tests -v
python scripts/check_project.py
```

The test suite uses temporary SQLite databases and does not touch your personal database.

## Local data locations

By default, PersonalBank stores files under the current user's home directory:

```text
~/.personalbank/
├── personalbank.sqlite3
└── settings.json
```

The database location can be changed in the application configuration file before starting the app. The database is created automatically if it does not exist.

## Project structure

```text
PersonalBank/
├── personalbank/
│   ├── __main__.py             # Application entry point
│   ├── config.py               # User preferences and local paths
│   ├── db.py                   # SQLite schema, initialization, connections
│   ├── domain.py               # Enums, date and money helpers
│   ├── repositories.py         # Core data access layer
│   ├── services.py             # Core account and transaction rules
│   ├── advanced.py             # Forecast, reconciliation, debt, investment, net worth\n│   ├── productivity.py         # Subscriptions, tax annotations, categorization rules
│   ├── dialogs.py              # Core PyQt dialogs
│   ├── advanced_dialogs.py     # Advanced PyQt dialogs
│   ├── ui.py                   # Main window and application pages
│   ├── charts.py               # Dependency-free chart widgets
│   ├── csv_tools.py             # Transaction import and export
│   ├── backup.py                # SQLite backup and restore
│   └── formatting.py           # Display formatting
├── scripts/
│   └── check_project.py
├── install_windows.bat
├── run_windows.bat
├── run_unix.sh
├── tests/
│   ├── test_finance.py
│   ├── test_csv_backup.py
│   └── test_advanced.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ADVANCED_FEATURES.md
│   ├── FINANCIAL_RULES.md
│   ├── SECURITY_AND_PRIVACY.md
│   ├── TEST_PLAN.md
│   ├── UPGRADE_NOTES.md
│   ├── DATA_DICTIONARY.md
│   └── USER_GUIDE.md
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Important limitations

- This app does not connect to financial institutions, download statements, initiate transfers, submit bill payments, or execute investment trades. Subscription renewals are also user-confirmed local expense entries.
- Investment prices are entered by the user. There is no live quote feed.
- Debt payoff schedules are estimates using a fixed APR and monthly compounding. They do not replace a lender's official payoff quote.
- The database is not encrypted by the application. Use operating-system account protection and full-disk encryption. Backups are also ordinary SQLite files.
- Combined totals assume one currency. The app does not perform foreign-exchange conversion. Avoid combining multiple currencies in a single net-worth total unless you convert them yourself before entering values.
- Net-worth calculations include all tracked account balances (including archived accounts), investment market value, and outstanding debt plans (including archived plans). Do not also enter the same debt as a negative liability account, or it will be counted twice.
- Credit-card and loan account balances use a negative-balance convention for amounts owed. See `docs/FINANCIAL_RULES.md`.
- Tax labels are personal annotations only. The tax center does not determine eligibility, calculate tax owed, prepare returns, or replace advice from a qualified tax professional.\n- This software is intended for personal tracking and planning, not official accounting, tax filing, investment advice, or regulatory reporting.

## Development notes

Keep UI code in `ui.py` and dialog modules. Put business rules in service classes, and keep SQL access in the database/repository layer. Add a test whenever a new financial rule is introduced.

For future schema changes, increment `SCHEMA_VERSION` and provide an upgrade path. The current schema initializer uses `CREATE TABLE IF NOT EXISTS` for additive tables. Destructive column changes require explicit migration code.

See `docs/ARCHITECTURE.md` for the application layers and `docs/TEST_PLAN.md` for validation coverage.
