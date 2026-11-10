# Automated Test Plan

Run all tests with:

```bash
python -m unittest discover -s tests -v
```

The tests create temporary database files and clean them up after each test class.

## Core finance tests

- Money conversion and rounding to minor units
- Income and expense balance effects
- Transfer effects between two accounts
- Same-account transfer rejection
- Invalid amount and invalid date rejection
- Budget utilization and remaining balance
- Recurring bill payment and due-date advancement
- Savings-goal contribution tracking
- Dashboard month totals

## CSV and backup tests

- Transaction export and preview
- Missing required CSV columns
- SQLite backup integrity
- Restore into a new database
- Receipt attachment validation, transaction-delete cascade, additive schema upgrade, and backup/restore

## Advanced finance tests

- Monthly recurrence anchor behavior and leap-year dates
- Recurring posting, skipping, end dates, and category validation
- Cash-flow projections for recurring schedules and bills
- Overdue forecast labeling and no ledger mutation
- Reconciliation balance matching and transfer sign handling
- Reconciliation close protection when a difference remains
- Preventing multiple open sessions for one account
- Preventing already reconciled transactions from appearing again
- Debt APR conversion, payment validation, amortization schedule, payment posting, and payoff caps
- Interest accrual by elapsed calendar months and same-month extra payments
- Investment buy/sell cash effects and weighted-average cost basis
- Rejecting sales greater than holdings and mismatched currencies
- Preventing edits/deletes of linked investment and reconciled transactions
- Net-worth calculation and dated snapshot upsert
- SQLite integrity and foreign-key checks

## Manual GUI smoke test

Because the automated test suite does not launch a graphical Qt session, perform this manual check after installing PyQt6:

1. Start the app with `python -m personalbank`.
2. Create checking, savings, and investment accounts.
3. Add income, expense, and transfer transactions.
4. Attach an image or PDF receipt to a transaction, open it, then remove it.
5. Create a monthly budget and recurring schedule.
6. Generate a cash-flow forecast and verify it does not add ledger transactions.
7. Start a reconciliation, check the relevant items, and close it when the difference reaches zero.
8. Create a debt plan, view its schedule, and record a payment.
9. Add a security, record a buy, update the manual price, and record a partial sale.
10. Save a net-worth snapshot.
11. Export transactions, create a backup, and run the database health check.
12. Close and reopen the app to confirm persistence.

## Expected limitations

PyQt6 must be installed to run the desktop UI. A Python syntax check does not replace a manual GUI test. The UI is not automatically exercised by the service-layer tests.
