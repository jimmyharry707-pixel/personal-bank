# Personal finance productivity features

## Subscription manager

Subscriptions are local reminders and expense templates. A subscription can store a vendor, amount, currency, billing frequency, next renewal date, optional trial end, cancellation deadline, category, payment account, website, and notes.

The monthly and annual equivalent totals normalize weekly, biweekly, monthly, quarterly, and yearly prices. These are planning estimates, not forecasts of actual cash movements. If active subscriptions use more than one currency, the combined monthly and annual cards display a mixed-currency warning rather than adding unlike amounts.

When the user records a renewal, the app verifies that the subscription is active and due, requires a linked active payment account, creates one ordinary expense transaction, advances the next renewal date using the calendar recurrence helper, and records the renewal in the audit log. No payment is submitted. Price history preserves initial and later price changes with effective dates.

## Tax recordkeeping

A transaction can have one tax annotation. The annotation contains tax year, treatment, tax category, deductible percentage, and notes.

Supported treatments include deductible expense, non-deductible expense, tax payment, taxable income, tax-exempt income, capital gain, and other.

The service checks that income treatments are assigned to income and expense treatments to expenses. A deductible percentage is applied only to deductible expenses. Annual summaries show tagged gross income, tagged taxable income, tagged deductible expenses, tax payments, classified transaction count, and unclassified income/expense counts.

The annual CSV export contains transaction-level annotations. These values are user-entered classifications. The app does not decide whether a cost is deductible, estimate tax liability, or generate a tax return.

## Auto-categorization

A rule contains a name, keyword, target field (payee, description, or either), transaction type, category, and priority.

Rules are processed from highest priority to lowest. Matching is case-insensitive substring matching. Only transactions with no category are eligible. Existing category assignments are never overwritten. The user must explicitly click Apply rules before any transaction is changed. Each update is included in the local audit log.

## Database upgrade

Version 1.2 adds the `subscriptions`, `subscription_price_history`, `transaction_tax_records`, and `categorization_rules` tables. The schema uses additive `CREATE TABLE IF NOT EXISTS` statements, so existing account and transaction records remain in place.
