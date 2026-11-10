# Advanced Feature Guide

This guide explains how the advanced pages behave and which records they create.

## Recurring transactions

A recurring template describes a planned income or expense. A template contains a name, transaction type, account, optional category, amount, recurrence frequency, first due date, optional end date, payee, and notes.

Supported frequencies are weekly, every two weeks, monthly, quarterly, and yearly. Monthly schedules retain their original day-of-month anchor. A schedule starting on January 31 therefore advances to February 28 (or 29 in a leap year) and then returns to March 31.

The **Post selected** action creates a normal transaction and advances the schedule. It does not send money or communicate with a bank. The **Skip occurrence** action advances the next due date without creating a transaction. Archived schedules remain in the database for reference.

A late schedule can be posted once per due occurrence. If several occurrences are overdue, post or skip each occurrence intentionally. This avoids silently creating a large batch of historical transactions.

## Cash-flow forecast

The forecast page combines active recurring templates and active bills. It shows the projected date, original due date, source, transaction type, account, amount, and projected account balance.

- The forecast horizon can be set from 7 to 3,650 days.
- Overdue schedule entries are shown on the forecast start date with their original due date retained.
- Events without a payment account are included in projected expense totals but do not affect an account balance.
- Forecast events are not written to the transaction ledger.
- The forecast assumes each listed bill or recurring entry occurs at its scheduled amount. It does not model variable bills, overdrafts, interest on deposit accounts, or changes in income.

Use the forecast as a planning aid, not as a guarantee of future cash availability.

## Bank reconciliation

To reconcile an account:

1. Open **Reconciliation** and select an account.
2. Choose **Start reconciliation**.
3. Enter the statement ending date and ending balance.
4. Check each transaction that appears on the bank statement.
5. Compare the calculated balance and difference shown above the table.
6. Close the session only when the difference is zero.

The first session starts from the account's opening balance. Later sessions start from the previous closed statement balance. Transactions explicitly cleared in a closed session are marked reconciled and are not offered again. Uncleared items remain available for a later statement.

Transfers are handled from the selected account's perspective: a transfer out is negative, and a transfer in is positive. A reconciliation session cannot be closed while its difference is non-zero.

If a session was started with the wrong statement balance or date, discard the open session and create it again. Discarding an open session does not delete transactions.

## Debt planner

A debt plan tracks a starting principal, current principal, creditor, APR, minimum monthly payment, payment account, due day, and start date.

APR is stored in basis points. For example, 12.50% is stored as 1,250 basis points. The payoff schedule applies a fixed APR and monthly compounding. It assumes the scheduled payment is made on time and does not model lender-specific fees, variable rates, promotional periods, or daily-balance calculations.

When a payment is recorded:

- Interest is estimated for the elapsed calendar months since the previous payment (or the plan start date).
- A second payment in the same calendar month does not add another monthly interest charge.
- The payment is capped at the amount needed to pay off the outstanding balance plus accrued interest.
- The payment creates an expense transaction in the selected cash account.
- The debt plan's outstanding balance is reduced by the principal portion.

The debt plan is a manual tracker. It does not verify a payment with the creditor. Compare the estimate with the lender's statement before making real payments.

## Investment portfolio

First create an account with type **Investment**, then add one or more securities. Each security has a symbol, name, asset type, currency, and manually entered last price.

A trade records:

- Investment account
- Security
- Buy or sell action
- Quantity, to six decimal places
- Price per share
- Commission and fees
- Trade date and notes

A buy creates an expense transaction in the investment account and adds shares to the position. A sell creates income in the investment account and reduces the position. Selling more shares than held is rejected.

Cost basis uses a weighted-average method. Buy commissions are included in cost basis. Sell commissions reduce sale proceeds. Realized gain/loss is calculated on the quantity sold; unrealized gain/loss is market value minus remaining cost basis.

Market prices are manual snapshots. Updating a price does not alter the trade ledger. There is no market data provider, broker connection, order routing, dividend reinvestment automation, tax-lot selection, or corporate-action processing.

## Net worth snapshots

The Net worth page estimates:

- Assets: positive balances in active non-liability accounts plus investment market value.
- Liabilities: negative account balances plus all outstanding debt plans, including archived plans.
- Net worth: assets minus liabilities.

Credit-card and loan accounts use negative balances for amounts owed. Other account types can also contribute a liability if their balance is negative.

Snapshots are saved by date. Saving another snapshot for the same date updates that date's existing record. Snapshot details preserve the account and debt values used for the calculation.

Archived accounts remain in the net-worth calculation because archiving hides an account from ordinary entry workflows but does not erase its value. Do not record the same liability both as a negative account balance and as a debt plan. Doing so counts it twice. Keep all included accounts and investments in one currency because the application does not convert foreign currencies.

## Categories

Categories are either income or expense. Budgets can only use expense categories. Archiving a category prevents it from being selected for new entries but keeps old transactions and reports intact.

Category names are unique within their type. For example, an income category and an expense category may share a display name, but two expense categories cannot have the same name.

## Activity log and database health

The activity log lists local changes that are recorded by the service and repository layers. It is useful for reviewing actions, but it is not a tamper-proof audit trail.

The database health check runs SQLite's `integrity_check` and `foreign_key_check`, then counts the tables. A healthy result is `integrity_check = ok` and no foreign-key issues.

Run a database backup before major imports, restores, or manual database maintenance.
