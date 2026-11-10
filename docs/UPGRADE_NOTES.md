# Upgrade Notes

## Version 1.1.0 — Advanced personal finance expansion

The schema version is now 2. The initializer adds the following tables if they do not already exist:

- `recurring_transactions`
- `reconciliation_sessions`
- `reconciliation_items`
- `reconciled_transactions`
- `debt_plans`
- `debt_payments`
- `investment_securities`
- `investment_trades`
- `net_worth_snapshots`

The existing accounts, categories, transactions, budgets, bills, savings goals, settings, and audit log tables remain in place. Existing records are not rewritten by the additive schema initialization.

### Existing installation

1. Close the application.
2. Create a copy of `personalbank.sqlite3` using the application's backup feature or a safe filesystem copy while the app is closed.
3. Replace the source folder with the updated project files.
4. Install any updated requirements.
5. Start the application. New tables are created automatically.
6. Run **Activity log → Run database health check**.

If startup fails, restore the copy of the original database and retain the error message for troubleshooting.

### New ledger protections

Transactions that have been reconciled or are linked to debt payments or investment trades cannot be edited or deleted through the ordinary transaction controls. This protects dependent records from becoming inconsistent.

### Important calculation changes

Debt payments now accrue estimated monthly interest according to the calendar months elapsed since the previous payment. An additional payment in the same calendar month does not charge another monthly interest period.
