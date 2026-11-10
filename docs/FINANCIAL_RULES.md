# Financial Calculation Rules

This document describes the assumptions used by PersonalBank. These rules are intentionally explicit so that users can interpret the figures correctly.

## Monetary precision

- Monetary values are stored as signed integer minor units.
- The current application assumes two decimal places for display and input.
- `Decimal` is used when converting typed values to minor units.
- Database arithmetic uses integers wherever possible.
- A future currency-metadata feature is needed for currencies whose minor unit is not two decimal places.

For a two-decimal currency, 123.45 is stored as 12,345 minor units.

## Account balance convention

The balance of an account is its opening balance plus the effect of its transactions:

| Transaction         | Account effect |
| ------------------- | -------------: |
| Income              |       + amount |
| Expense             |       - amount |
| Transfer out        |       - amount |
| Transfer in         |       + amount |
| Positive adjustment |       + amount |
| Negative adjustment |       - amount |

The application does not prohibit negative balances. This is useful for recording overdrafts and liabilities, but users must enter the correct opening-balance sign.

For credit-card and loan accounts, record amounts owed as a negative balance. For example, a card with $800 owed can begin with an opening balance of -80,000 minor units. A purchase entered as an expense decreases the account balance further; a payment recorded as income increases it toward zero.

## Transfers

A transfer is one transaction with a source account and a destination account. The source balance decreases and the destination balance increases. Transfers are excluded from income and expense totals so they do not inflate cash-flow reports.

## Budgets

A budget is unique for an expense category and a calendar month. Actual spending is the sum of expense transactions assigned to that category with an occurrence date in that month. Transfers and income are excluded.

Budget utilization is `spent / limit * 100`. A zero limit produces 0% utilization in the current display.

## Recurrence and forecast

Recurring schedules preserve a monthly anchor day to avoid date drift. If the selected day does not exist in a month, the due date uses that month's last day, then returns to the anchor day in later months.

Forecasts include only active schedules and bills. A forecast event is an estimate, not a transaction. Forecasting never writes to the ledger.

## Financial scenarios

A scenario projects one selected account at a time for 1 to 60 calendar months. Its baseline includes the account's current balance on the start date and only active recurring schedules and bills assigned to that account. The baseline uses the same recurrence advancement and overdue handling as the cash-flow forecast.

Scenario assumptions are positive amounts in the account's currency. Income increases the projected balance; expenses decrease it. One-time assumptions affect only their selected month. Monthly assumptions repeat from their start month through the optional end month or the projection horizon. Scenario assumptions are not transactions, are excluded from actual budgets and reports, and are never posted to the ledger.

Scenario comparisons require the same account, start date, and horizon. They compare hypothetical ending balances to each scenario's baseline. The monthly closing balance is flagged when below zero; this is a planning warning, not a prediction or overdraft action.

## Reconciliation

A reconciliation starts from the account opening balance or the previous closed statement balance. The user selects transactions that appear on the statement. The calculated balance is the opening balance plus the signed effect of selected items.

A session can close only when:

`statement ending balance - calculated cleared balance = 0`

Closed items are marked as reconciled and are excluded from future reconciliation sessions. Uncleared items remain outstanding.

## Debt calculations

APR is stored in basis points, where 100 basis points equal 1%. The monthly rate is approximated as annual APR divided by 12.

Monthly interest is rounded to the nearest minor unit:

`monthly interest = outstanding balance * APR basis points / 120,000`

When a payment is recorded, the application estimates interest for each elapsed calendar month since the last payment date. Payments in the same calendar month do not accrue a second monthly charge. The payment first covers estimated accrued interest; the remainder reduces principal. Payments above the amount needed to clear the balance are capped.

The schedule assumes a constant APR and a fixed monthly payment. It is not a lender payoff quote and may differ from the lender's daily-interest method, compounding conventions, fees, and posting dates.

## Investment calculations

- Quantity is stored in millionths of a share.
- Unit price is stored in minor currency units per share.
- Gross trade value is rounded to the nearest minor unit.
- Buy cost basis includes commissions.
- Sell proceeds are reduced by commissions.
- Holdings use weighted-average cost basis.
- Realized gain/loss is net sale proceeds less the weighted-average cost removed from the holding.
- Unrealized gain/loss is manually priced market value less remaining cost basis.
- Investment buy and sell transactions remain in the transaction ledger but are excluded from household income/expense cash-flow totals. They represent movement between cash and invested assets rather than ordinary consumption or income.

The portfolio page does not calculate taxes or choose specific tax lots.

## Net worth

Assets include positive balances from all tracked accounts (including archived accounts) and manually priced investment holdings. Liabilities include negative account balances and all outstanding debt plans, including archived plans. Net worth equals assets minus liabilities.

The Currency Valuation page converts current account balances, manually priced investments, and outstanding debt plans to the selected base currency using user-entered rates. A rate means one source-currency unit equals the stated number of target-currency units. An inverse rate is used when only the reverse pair is stored; no multi-hop or online rates are inferred. Converted minor units are rounded half up. Missing-rate amounts are shown as missing and excluded from totals.

This report is a current estimate, not historical FX accounting. Transactions, cash-flow reports, budgets, and saved net-worth snapshots stay in their original currencies. Do not represent the same debt in both a negative liability account and a debt plan.

Dashboard cash-flow totals and historical category reports also remain unconverted. If they include more than one currency, interpret them as raw minor-unit totals rather than a meaningful combined amount.

## Reporting boundaries

- Monthly cash flow is based on recorded income and expense transactions, not forecasts.
- A bill reminder is not a payment until the user records it.
- A savings-goal contribution updates goal progress; it does not move account funds.
- An investment price update does not create a transaction.
- A debt plan does not contact a lender.
