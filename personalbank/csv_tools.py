from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

from .domain import to_minor_units, validate_date


EXPORT_COLUMNS = [
    "date", "type", "account", "transfer_account", "category", "amount",
    "payee", "description", "reference", "notes",
]


class CsvService:
    def __init__(self, finance):
        self.finance = finance

    def export_transactions(self, path: str | Path, start_date: str | None = None,
                            end_date: str | None = None) -> int:
        rows = self.finance.list_transactions(
            start_date=start_date, end_date=end_date, limit=10000
        )
        with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "date": row["occurred_on"],
                    "type": row["kind"],
                    "account": row["account_name"],
                    "transfer_account": row["transfer_account_name"] or "",
                    "category": row["category_name"] or "",
                    "amount": str(Decimal(int(row["amount_minor"])) / Decimal(100)),
                    "payee": row["payee"],
                    "description": row["description"],
                    "reference": row["reference"],
                    "notes": row["notes"],
                })
        return len(rows)

    def preview_import(self, path: str | Path) -> list[dict[str, str]]:
        with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            required = {"date", "type", "account", "amount"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError("CSV must include date, type, account, and amount columns.")
            return [dict(row) for row in reader]

    def import_transactions(self, path: str | Path, *, skip_invalid: bool = False) -> dict[str, Any]:
        rows = self.preview_import(path)
        return self.import_rows(rows, skip_invalid=skip_invalid)

    def import_rows(self, rows: list[dict[str, str]], *, skip_invalid: bool = False) -> dict[str, Any]:
        accounts = {row["name"].casefold(): int(row["id"]) for row in self.finance.accounts.list()}
        categories = {
            (row["name"].casefold(), row["kind"]): int(row["id"])
            for row in self.finance.categories.list()
        }
        imported, skipped, errors = 0, 0, []
        for line_number, row in enumerate(rows, start=2):
            try:
                kind = row["type"].strip().lower()
                occurred_on = validate_date(row["date"].strip())
                account_key = row["account"].strip().casefold()
                if account_key not in accounts:
                    raise ValueError(f"Unknown account: {row['account']}")
                account_id = accounts[account_key]
                amount_minor = to_minor_units(row["amount"])
                category_id = None
                category_name = row.get("category", "").strip()
                if category_name:
                    category_kind = "income" if kind == "income" else "expense"
                    category_id = categories.get((category_name.casefold(), category_kind))
                    if category_id is None:
                        raise ValueError(f"Unknown {category_kind} category: {category_name}")
                if kind == "income":
                    self.finance.create_income(
                        account_id, amount_minor, occurred_on, category_id,
                        row.get("payee", ""), row.get("description", ""),
                        row.get("reference", ""), row.get("notes", ""),
                    )
                elif kind == "expense":
                    self.finance.create_expense(
                        account_id, amount_minor, occurred_on, category_id,
                        row.get("payee", ""), row.get("description", ""),
                        row.get("reference", ""), row.get("notes", ""),
                    )
                elif kind == "transfer":
                    target_key = row.get("transfer_account", "").strip().casefold()
                    if target_key not in accounts:
                        raise ValueError("Transfer row requires a valid transfer_account.")
                    self.finance.create_transfer(
                        account_id, accounts[target_key], amount_minor, occurred_on,
                        row.get("description", ""), row.get("notes", ""),
                    )
                else:
                    raise ValueError(f"Unsupported transaction type: {kind}")
                imported += 1
            except Exception as exc:
                skipped += 1
                errors.append(f"Line {line_number}: {exc}")
                if not skip_invalid:
                    break
        return {"imported": imported, "skipped": skipped, "errors": errors}
