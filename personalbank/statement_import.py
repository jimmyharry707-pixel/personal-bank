from __future__ import annotations

from collections import defaultdict
from typing import Any

from .domain import to_minor_units, validate_date


class StatementMatchingService:
    """Review statement CSV rows against the local transaction ledger."""

    def __init__(self, finance, csv_service=None):
        self.finance = finance
        if csv_service is None:
            from .csv_tools import CsvService

            csv_service = CsvService(finance)
        self.csv_service = csv_service
        self._accounts_by_name = None
        self._categories_by_kind = None

    @staticmethod
    def _normalized_text(value: Any) -> str:
        return " ".join(str(value or "").casefold().split())

    def _parse_row(self, row: dict[str, str], line_number: int) -> dict[str, Any]:
        kind = str(row.get("type") or "").strip().casefold()
        if kind not in {"income", "expense", "transfer"}:
            raise ValueError(f"Unsupported transaction type: {kind or '(blank)'}")
        occurred_on = validate_date(str(row.get("date") or "").strip())
        account_name = str(row.get("account") or "").strip()
        account = self._accounts_by_name.get(account_name.casefold())
        if not account:
            raise ValueError(f"Unknown account: {account_name}")
        amount_minor = to_minor_units(str(row.get("amount") or ""))
        if amount_minor <= 0:
            raise ValueError("Transaction amount must be greater than zero.")

        transfer_name = str(row.get("transfer_account") or "").strip()
        transfer_account = None
        if kind == "transfer":
            transfer_account = self._accounts_by_name.get(transfer_name.casefold())
            if not transfer_account:
                raise ValueError("Transfer row requires a valid transfer_account.")
            if int(transfer_account["id"]) == int(account["id"]):
                raise ValueError("A transfer must use two different accounts.")

        category_name = str(row.get("category") or "").strip()
        if category_name:
            category_kind = "income" if kind == "income" else "expense"
            category_names = self._categories_by_kind[category_kind]
            if category_name.casefold() not in category_names:
                raise ValueError(f"Unknown {category_kind} category: {category_name}")

        return {
            "line_number": line_number,
            "occurred_on": occurred_on,
            "kind": kind,
            "account_id": int(account["id"]),
            "account_name": account["name"],
            "transfer_account_id": int(transfer_account["id"]) if transfer_account else None,
            "transfer_account_name": transfer_account["name"] if transfer_account else "",
            "amount_minor": amount_minor,
            "payee": str(row.get("payee") or "").strip(),
            "description": str(row.get("description") or "").strip(),
            "reference": str(row.get("reference") or "").strip(),
        }

    @staticmethod
    def _signature(parsed: dict[str, Any]) -> tuple[Any, ...]:
        return (
            parsed["occurred_on"], parsed["kind"], parsed["account_id"],
            parsed["transfer_account_id"], parsed["amount_minor"],
        )

    def _candidates(self, parsed: dict[str, Any]) -> list[dict[str, Any]]:
        existing = self.finance.list_transactions(
            start_date=parsed["occurred_on"],
            end_date=parsed["occurred_on"],
            account_id=parsed["account_id"],
            kind=parsed["kind"],
            limit=10000,
        )
        reference = self._normalized_text(parsed["reference"])
        payee = self._normalized_text(parsed["payee"])
        matches = []
        for item in existing:
            if int(item["account_id"]) != parsed["account_id"]:
                continue
            if int(item["amount_minor"]) != parsed["amount_minor"]:
                continue
            candidate_transfer = (
                int(item["transfer_account_id"])
                if item["transfer_account_id"] is not None else None
            )
            if candidate_transfer != parsed["transfer_account_id"]:
                continue
            candidate_reference = self._normalized_text(item["reference"])
            candidate_payee = self._normalized_text(item["payee"])
            score = 0.70
            if reference and candidate_reference == reference:
                score += 0.15
            if payee and candidate_payee == payee:
                score += 0.15
            matches.append({
                "transaction_id": int(item["id"]),
                "date": item["occurred_on"],
                "payee": item["payee"],
                "description": item["description"],
                "reference": item["reference"],
                "amount_minor": int(item["amount_minor"]),
                "confidence": score,
            })
        matches.sort(key=lambda item: (-item["confidence"], item["transaction_id"]))
        return matches[:3]

    def review(self, path: str) -> list[dict[str, Any]]:
        raw_rows = self.csv_service.preview_import(path)
        self._accounts_by_name = {
            account["name"].casefold(): account
            for account in self.finance.accounts.list()
        }
        self._categories_by_kind = {
            kind: {
                category["name"].casefold()
                for category in self.finance.categories.list(kind=kind)
            }
            for kind in ("income", "expense")
        }
        seen: dict[tuple[Any, ...], int] = {}
        results = []
        for line_number, raw in enumerate(raw_rows, start=2):
            result: dict[str, Any] = {
                "line_number": line_number,
                "raw": raw,
                "parsed": None,
                "valid": False,
                "error": "",
                "matches": [],
                "duplicate_in_file_line": None,
                "import_selected": False,
                "match_label": "",
            }
            try:
                parsed = self._parse_row(raw, line_number)
                result["parsed"] = parsed
                result["valid"] = True
                signature = self._signature(parsed)
                previous_line = seen.get(signature)
                if previous_line is not None:
                    result["duplicate_in_file_line"] = previous_line
                    result["match_label"] = f"Repeated in file (line {previous_line})"
                else:
                    seen[signature] = line_number
                    result["matches"] = self._candidates(parsed)
                    if result["matches"]:
                        confidence = result["matches"][0]["confidence"]
                        result["match_label"] = f"Possible match ({confidence:.0%})"
                    else:
                        result["import_selected"] = True
                        result["match_label"] = "No match"
            except Exception as exc:
                result["error"] = str(exc)
                result["match_label"] = "Invalid row"
            results.append(result)
        return results

    def import_selected(self, review_rows: list[dict[str, Any]]) -> dict[str, Any]:
        selected = [
            review["raw"] for review in review_rows
            if review["valid"] and review["import_selected"]
        ]
        if not selected:
            return {"imported": 0, "skipped": 0, "errors": [], "selected": 0}
        result = self.csv_service.import_rows(selected, skip_invalid=True)
        result["selected"] = len(selected)
        return result