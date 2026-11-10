# PersonalBank User Guide

## First launch

On first launch, PersonalBank creates its application folder and SQLite database automatically. The app starts with standard income and expense categories. No account or transaction data is created for you.

## Set up accounts

Open **Accounts** and select **Add account**. Create one record for each account you want to track, such as checking, savings, cash, a credit card, a loan, or an investment account.

Enter an opening balance that represents the balance on the day you begin tracking. If you are entering historical transactions, use an opening balance dated before those transactions.

For credit cards and loans, use a negative opening balance to represent an amount owed. For example, $500 owed is entered as -500.00. Review `FINANCIAL_RULES.md` before entering liability accounts.

## Record activity

Open **Transactions** and select **Add transaction**.

- Use **Income** for salary, interest, refunds recorded as income, or other inflows.
- Use **Expense** for purchases, bills, fees, and other outflows.
- Use **Transfer** when moving money between two tracked accounts.

Transfers do not count as income or expenses in the cash-flow report. They only move the amount between the selected accounts.

Select an existing transaction and choose **Edit selected** to correct a normal income, expense, or transfer. Reconciled transactions and transactions linked to debt or investment records are protected from editing and deletion. Balance adjustments are not editable in the current UI.

Select a transaction and choose **Receipts** to attach PDF, PNG, JPG, WEBP, or GIF files up to 25 MB. Attachments are stored in the local database, included in database backups, and removed when their transaction is deleted. **Open selected** writes a temporary copy and opens it with the operating system's default application.

## Categories and budgets

Use **Categories** to create income and expense labels. Archived categories remain attached to historical transactions but are not offered for new entries.

In **Budgets**, choose a month in `YYYY-MM` format, then select **Set budget**. Choose an expense category and amount. Actual spending is calculated from expense transactions assigned to that category and month.

A category can have one budget per month. Setting the same category and month again updates its limit.

## Bills

Add a recurring bill with its amount, due day, frequency, and next due date. Assign a payment account to enable **Record payment**.

Recording a payment creates an expense transaction and advances the bill's next due date. It does not contact the biller or submit a real payment.

## Recurring transactions

Use **Recurring** for income or expenses that repeat on a schedule. The schedule can be weekly, every two weeks, monthly, quarterly, or yearly. Select **Post selected** to create a ledger transaction after confirming. Use **Skip occurrence** to move the schedule forward without creating a transaction.

Recurring entries are never posted automatically in the background.

## Cash-flow forecast

Use **Cash flow forecast** to estimate upcoming income and expenses from active recurring schedules and bills. Choose a horizon from 7 to 3,650 days. Overdue items are marked separately.

The forecast is read-only. It does not create transactions or reserve account funds. Forecast totals are estimates and may differ from actual amounts.

## Scenario planner

Create a scenario for one account, choose its start date and a horizon of up to 60 months, then add one-time or monthly income and expense assumptions. Monthly assumptions can end early or continue through the full horizon. The planner compares your assumptions with the selected account's baseline of active bills and recurring schedules, and shows projected closing balances and any first month below zero.

Select multiple scenarios with Ctrl-click or Shift-click and choose **Compare selected**. Scenarios must use the same account, start date, and horizon. Use **Duplicate** to create a named copy with its assumptions, or **Export projection** to save the selected monthly comparison as CSV. Scenario assumptions are hypothetical and do not change transactions, budgets, or account balances.

## Bank reconciliation

Open **Reconciliation**, choose an account, and start a session with the statement ending date and ending balance. Check the transactions that appear on the statement. The summary shows the calculated cleared balance and remaining difference.

Close the session only when the difference is zero. Transactions marked as cleared in a closed session are protected and will not be offered for reconciliation again. Unchecked transactions remain outstanding for later statements.

## Debt planner

Create a debt plan with the current principal, APR, minimum payment, due day, and payment account. Use **View payoff schedule** to see an estimated amortization table.

Use **Record payment** to enter a payment. The application estimates monthly interest, creates an expense transaction in the payment account, and reduces the debt balance by the principal portion. The interest calculation is an estimate; compare it with the lender's statement.

Choose **Compare payoff strategies** to compare minimum payments, snowball (lowest balance first), and avalanche (highest APR first). Enter an optional extra monthly amount to see estimated payoff time, interest, total paid, and month-by-month balances. Snowball and avalanche roll minimum payments freed by paid-off debts into the next target. All debt plans in a comparison must use the same currency. This is a read-only estimate and does not record payments.

## Investments

Create an account with type **Investment**. Add a security with its ticker, name, asset type, and currency. Record buys and sells manually. The application updates the investment account cash ledger and the share position.

Enter a market price using **Update selected price**. The portfolio calculates market value, weighted-average cost basis, realized gain/loss, and unrealized gain/loss. Prices are manual; no market quote is fetched.

## Savings goals

Create a goal with a target amount and optional target date. Select it and use **Add contribution** to update its progress.

Goal contributions are progress records only. They do not automatically create account transfers. If you move money into a savings account, record that transfer separately.

## Net worth

The **Net worth** page estimates assets, liabilities, and net worth from all tracked account balances (including archived accounts), manually priced investment holdings, and outstanding debt plans (including archived plans). Save a snapshot to preserve the values for a date. Saving again for the same date updates the existing snapshot.

Avoid recording the same liability in both a negative account and a debt plan. Keep tracked values in one currency if you want meaningful combined totals.

## Reports

The Reports page shows monthly income and expense totals for the selected year and a category breakdown of expenses. The dashboard shows current-month metrics. These reports use posted transactions, not forecast events.

## CSV export

Export creates a CSV file containing transaction date, type, account, category, amount, payee, description, reference, and notes. The file uses UTF-8 with a byte-order mark to improve compatibility with spreadsheet software.

## CSV import

The importer expects `date`, `type`, `account`, and `amount` columns. Optional columns include `transfer_account`, `category`, `payee`, `description`, `reference`, and `notes`.

Account and category names must match existing records. The import preview displays the number of rows before import. Invalid rows can be skipped, and the import result lists the first errors.

Review an imported file before relying on it. Importing the same file twice creates duplicate transactions; this version does not perform bank-statement duplicate matching.

For bank statements, use **Review statement matches** on the Transactions page. The review checks date, account, type, amount, and transfer destination, then scores reference and payee agreement. Possible ledger matches and repeated rows within the file are unchecked by default; unmatched valid rows are selected. Review the candidates, adjust the checkboxes as needed, and confirm the import. Matching is a heuristic, not a guarantee: always review the statement and never assume a suggested match is correct.

## Backups and restores

Use **Create database backup** to save a copy of the SQLite database. Create backups regularly and before importing a large CSV file.

Use **Restore from backup** to replace the current database. Restoring is destructive to the current local database. Keep a separate backup of the current file before restoring if you may need it.

## Activity log and health check

The Activity log page lists local changes that are written by the application. Run the database health check to execute SQLite integrity and foreign-key checks.

## Privacy

The database is stored on your computer. The application does not upload it. The database is not encrypted by the app, so protect your operating-system account and use full-disk encryption where available. Backups contain the same sensitive information and should be stored privately.
