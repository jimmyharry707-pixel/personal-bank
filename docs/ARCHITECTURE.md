# Application Architecture

PersonalBank is a desktop application with a local SQLite persistence layer. It does not expose a network service.

## Layer overview

```text
┌───────────────────────────────────────────────────────┐
│                    PyQt6 MainWindow                    │
│ Dashboard · Accounts · Transactions · Currency · ...  │
└──────────────────────────┬────────────────────────────┘
                           │ user actions
┌──────────────────────────▼────────────────────────────┐
│                    Dialogs / Views                     │
│ Input validation · table selection · confirmation      │
└──────────────────────────┬────────────────────────────┘
                           │ service calls
┌──────────────────────────▼────────────────────────────┐
│                    Service Layer                       │
│ FinanceService · DebtService · InvestmentService       │
│ RecurringTransactionService · ForecastService          │
│ ReconciliationService · NetWorthService · Currency      │
│ FinancialScenarioService                                │
└──────────────────────────┬────────────────────────────┘
                           │ SQL / repository calls
┌──────────────────────────▼────────────────────────────┐
│                Repository / Database Layer             │
│ SQLite connection · schema · indexes · transactions    │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                  Local SQLite File                     │
└───────────────────────────────────────────────────────┘
```

## Entry point

`personalbank.__main__` creates the `QApplication`, loads configuration, initializes the database, constructs the core `FinanceService`, and opens `MainWindow`.

## UI layer

`ui.py` owns the main navigation and page composition. The dialog modules isolate forms that collect multiple values. UI callbacks should:

1. Read values from a dialog.
2. Call a service method.
3. Display validation errors returned by the service.
4. Refresh the affected views after success.

Financial rules should not be implemented only in button callbacks. They belong in service classes so they can be tested without launching Qt.

## Service layer

`FinanceService` handles the original account, category, transaction, budget, bill, goal, and reporting workflows. `advanced.py` contains services for recurring entries, forecasting, reconciliation, debt, investment holdings, net worth, and database maintenance.

Services validate values before persistence and use database transaction contexts when multiple records must change together. Examples include posting a recurring transaction, recording a debt payment, recording an investment trade, and closing a reconciliation.

## Persistence layer

`db.py` creates the SQLite schema and indexes. `Database.transaction()` opens a write transaction using `BEGIN IMMEDIATE`, commits on success, rolls back on exceptions, and closes the connection. Read helpers use short-lived connections.

The database enables foreign-key enforcement and WAL journaling. `SCHEMA_VERSION` records the current schema version. Schema updates should be additive where possible; structural changes require migrations.

## Data integrity choices

- Monetary values use integer minor units.
- Foreign keys link accounts, categories, trades, payments, reconciliation items, and transaction attachments.
- Transaction attachment content is stored as a size-limited SQLite BLOB, so ordinary database backups include it.
- Manual exchange rates are stored as decimal text and used only by the current currency valuation report.
- Saved financial scenarios and their assumptions are separate from ledger transactions; previews layer assumptions over the existing cash-flow forecast.
- `CHECK` constraints enforce positive transaction amounts and valid status values.
- Unique constraints prevent duplicate category names within a category type, duplicate monthly budgets for a category, duplicate security symbols, and duplicate net-worth snapshots for a date.
- Reconciled transactions and investment/debt-linked transactions are protected from ordinary edit/delete operations.

## Testing strategy

Business services use temporary databases in `unittest`. The UI is intentionally thin, which allows the important financial rules to be tested without a graphical session. See `TEST_PLAN.md`.

## Extension guidelines

When adding a feature:

1. Define its data model and monetary/date assumptions.
2. Add schema and indexes in `db.py`.
3. Add service methods with input validation and atomic writes.
4. Add tests for normal behavior, edge cases, and failure rollback.
5. Add dialogs and UI pages only after the service API is stable.
6. Update the data dictionary and financial rules documentation.

Avoid importing PyQt6 into service modules. The core logic should remain independently testable.
