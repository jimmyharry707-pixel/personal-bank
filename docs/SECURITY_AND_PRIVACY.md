# Security and Privacy Notes

PersonalBank is designed for local personal use. It has no server component and does not transmit account or transaction data to a remote service.

## What the application stores

The SQLite database may contain:

- Account names and account types
- Opening balances and current ledger activity
- Payees, descriptions, references, and notes
- Budget limits and recurring bill details
- Savings goals and contributions
- Debt balances, APRs, and payment records
- Investment symbols, trade quantities, prices, and fees
- Reconciliation statement balances and cleared-item choices
- Net-worth snapshots
- Local activity-log entries

Do not enter online banking passwords, full card numbers, PINs, security answers, or authentication codes. The application does not need these values.

## Local storage

The database is stored under the current user's home directory by default. It is an ordinary SQLite file and is not encrypted by this application. Anyone with access to the file can potentially read its contents.

Recommended precautions:

- Use a strong operating-system login password.
- Enable BitLocker, FileVault, or equivalent full-disk encryption.
- Keep the operating system and device security software updated.
- Store backups in a private, encrypted location.
- Do not email or share database and backup files casually.
- Avoid running the application from a shared or public computer profile.

## Backups and restores

Backups are standard SQLite database files. They contain the same personal financial information as the live database. Restore replaces the active database contents; create a separate backup before restoring if the current data may be needed.

## Audit log

The activity log is a convenience feature. It records actions that the application code explicitly writes to the log. It is not cryptographically signed, append-only at the operating-system level, or tamper-proof. A person with direct file access can modify the SQLite database.

## No external financial actions

The app does not connect to banks, brokerages, lenders, card networks, or payment services. A recorded transaction is a personal ledger entry only. It does not initiate a real-world payment or investment trade.
