# Data Dictionary

All monetary values are integer minor units. For a two-decimal currency, `12345` represents 123.45. The current application formats all values using a two-decimal assumption; currencies with zero or three minor-unit digits require a future currency-metadata enhancement.

## Core tables

### accounts

| Column                | Meaning                                                       |
| --------------------- | ------------------------------------------------------------- |
| id                    | Local account identifier                                      |
| name                  | User-defined display name                                     |
| kind                  | checking, savings, cash, credit_card, investment, loan, other |
| currency              | Three-letter currency code                                    |
| opening_balance_minor | Starting balance in minor units                               |
| credit_limit_minor    | Optional limit for credit products                            |
| is_active             | 1 active, 0 archived                                          |
| created_at            | ISO timestamp                                                 |

### categories

| Column    | Meaning                        |
| --------- | ------------------------------ |
| id        | Local category identifier      |
| name      | Category name                  |
| kind      | income or expense              |
| color     | Hex color for visual reporting |
| is_active | 1 active, 0 archived           |

### transactions

| Column              | Meaning                               |
| ------------------- | ------------------------------------- |
| id                  | Local transaction identifier          |
| account_id          | Primary account                       |
| transfer_account_id | Destination account for transfers     |
| category_id         | Optional income/expense category      |
| kind                | income, expense, transfer, adjustment |
| amount_minor        | Positive amount in minor units        |
| occurred_on         | ISO date                              |
| payee               | Merchant or payer                     |
| description         | Short explanation                     |
| reference           | User-supplied reference               |
| notes               | Additional notes                      |
| created_at          | Creation timestamp                    |
| updated_at          | Last update timestamp                 |

### transaction_attachments

| Column         | Meaning                                                              |
| -------------- | -------------------------------------------------------------------- |
| id             | Local attachment identifier                                          |
| transaction_id | Parent transaction; deleting the transaction deletes its attachments |
| filename       | Original file name                                                   |
| media_type     | MIME type guessed from the file extension                            |
| size_bytes     | Stored content size, from 1 byte to 25 MiB                           |
| content        | Receipt bytes stored as a SQLite BLOB                                |
| created_at     | Attachment timestamp                                                 |

### budgets

| Column      | Meaning                      |
| ----------- | ---------------------------- |
| id          | Budget identifier            |
| category_id | Expense category             |
| month       | YYYY-MM                      |
| limit_minor | Monthly limit in minor units |

### bills

| Column        | Meaning                                                        |
| ------------- | -------------------------------------------------------------- |
| id            | Bill identifier                                                |
| name          | Display name                                                   |
| amount_minor  | Expected amount                                                |
| due_day       | Calendar day, 1–31                                             |
| category_id   | Expense category                                               |
| account_id    | Payment account                                                |
| frequency     | weekly, biweekly, monthly, quarterly, yearly                   |
| auto_post     | Reserved legacy preference; payment remains manually confirmed |
| active        | 1 active, 0 archived                                           |
| next_due_date | Next expected due date                                         |
| notes         | Additional information                                         |

### savings_goals

| Column        | Meaning                |
| ------------- | ---------------------- |
| id            | Goal identifier        |
| name          | Goal name              |
| target_minor  | Target amount          |
| current_minor | Contributions recorded |
| target_date   | Optional target date   |
| notes         | Additional information |
| active        | 1 active, 0 archived   |

## Advanced tables

### recurring_transactions

| Column         | Meaning                                          |
| -------------- | ------------------------------------------------ |
| id             | Recurring template identifier                    |
| name           | Schedule label                                   |
| kind           | income or expense                                |
| account_id     | Account affected when posted                     |
| category_id    | Optional category of the matching type           |
| amount_minor   | Positive scheduled amount                        |
| payee          | Payee or payer                                   |
| description    | Transaction description                          |
| frequency      | weekly, biweekly, monthly, quarterly, yearly     |
| anchor_day     | Original calendar day for month-based recurrence |
| next_due_date  | Next scheduled occurrence                        |
| end_date       | Optional final date                              |
| last_posted_on | Date last posted                                 |
| active         | 1 active, 0 archived                             |
| notes          | Additional information                           |
| created_at     | Creation timestamp                               |

### reconciliation_sessions

Stores the account, statement date, opening balance, statement ending balance, status, notes, and timestamps for a reconciliation session.

### reconciliation_items

Maps candidate transactions to a reconciliation session and stores whether the user marked each item as cleared.

### reconciled_transactions

Maps each successfully cleared transaction to the closed reconciliation session that accepted it. The transaction ID is unique so a transaction cannot be reconciled twice.

### debt_plans

| Column                   | Meaning                                |
| ------------------------ | -------------------------------------- |
| id                       | Debt plan identifier                   |
| name                     | User-defined debt name                 |
| creditor                 | Lender or creditor label               |
| original_principal_minor | Initial principal entered              |
| principal_minor          | Current estimated outstanding balance  |
| apr_basis_points         | Annual percentage rate in basis points |
| minimum_payment_minor    | Planned minimum payment                |
| payment_account_id       | Cash account used for payments         |
| due_day                  | Monthly due day                        |
| start_date               | Plan start date                        |
| active                   | 1 active, 0 paid off or archived       |
| notes                    | Additional information                 |
| created_at               | Creation timestamp                     |

### debt_payments

Stores the payment transaction link, total payment, estimated interest portion, principal portion, payment date, and notes.

### investment_securities

| Column           | Meaning                                      |
| ---------------- | -------------------------------------------- |
| id               | Security identifier                          |
| symbol           | Unique symbol or ticker                      |
| name             | Security display name                        |
| asset_type       | stock, etf, mutual_fund, bond, crypto, other |
| currency         | Three-letter currency code                   |
| last_price_minor | Manually entered last price per share        |
| price_updated_at | Last manual quote timestamp                  |
| active           | 1 active, 0 archived                         |
| created_at       | Creation timestamp                           |

### investment_trades

Stores the investment account, security, buy/sell side, quantity in millionths of a share, unit price in minor units, commissions, gross value, linked transaction, trade date, and notes.

### net_worth_snapshots

Stores one point-in-time snapshot per date, including assets, liabilities, net worth, serialized detail, notes, and creation timestamp.

## Support tables

### settings

Key/value settings stored in the database for future application preferences.

### audit_log

Records create/update/archive/delete/payment actions performed by application code that opts into audit logging. This is a lightweight local activity record, not a tamper-proof security audit.

### schema_meta

Stores the current SQLite schema version.
