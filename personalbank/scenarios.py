from __future__ import annotations

import csv
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .advanced import CashFlowForecastService, add_months
from .domain import now_iso, validate_date


class FinancialScenarioService:
    """Saved what-if assumptions layered over an account cash-flow forecast."""

    MAX_HORIZON_MONTHS = 60
    MAX_COMPARISON_SCENARIOS = 5

    def __init__(self, finance, forecast: CashFlowForecastService | None = None):
        self.finance = finance
        self.db = finance.db
        self.forecast = forecast or CashFlowForecastService(finance)

    def create(
        self,
        *,
        name: str,
        account_id: int,
        start_date: str,
        horizon_months: int = 12,
        notes: str = "",
    ) -> int:
        name = str(name).strip()
        if not name:
            raise ValueError("Scenario name is required.")
        if len(name) > 100:
            raise ValueError("Scenario names must be 100 characters or fewer.")
        account = self.finance.accounts.get(int(account_id))
        if not account or not account["is_active"]:
            raise ValueError("Choose an active account for the scenario.")
        start_date = validate_date(start_date)
        horizon = int(horizon_months)
        if not 1 <= horizon <= self.MAX_HORIZON_MONTHS:
            raise ValueError("Scenario horizon must be between 1 and 60 months.")
        timestamp = now_iso()
        try:
            return self.db.execute(
                """INSERT INTO financial_scenarios(
                    name, account_id, start_date, horizon_months, notes, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (name, int(account_id), start_date, horizon, str(notes).strip(),
                 timestamp, timestamp),
            )
        except sqlite3.IntegrityError as exc:
            if "financial_scenarios.name" in str(exc):
                raise ValueError("A scenario with this name already exists.") from None
            raise

    def update(self, scenario_id: int, **fields: Any) -> None:
        scenario = self.get(scenario_id)
        if not scenario:
            raise ValueError("Scenario was not found.")
        allowed = {"name", "account_id", "start_date", "horizon_months", "notes"}
        changes = {key: value for key, value in fields.items() if key in allowed}
        if not changes:
            return
        if "name" in changes:
            name = str(changes["name"]).strip()
            if not name:
                raise ValueError("Scenario name is required.")
            if len(name) > 100:
                raise ValueError("Scenario names must be 100 characters or fewer.")
            changes["name"] = name
        if "account_id" in changes:
            account = self.finance.accounts.get(int(changes["account_id"]))
            if not account or not account["is_active"]:
                raise ValueError("Choose an active account for the scenario.")
            changes["account_id"] = int(changes["account_id"])
        if "start_date" in changes:
            changes["start_date"] = validate_date(changes["start_date"])
        if "horizon_months" in changes:
            horizon = int(changes["horizon_months"])
            if not 1 <= horizon <= self.MAX_HORIZON_MONTHS:
                raise ValueError("Scenario horizon must be between 1 and 60 months.")
            changes["horizon_months"] = horizon
        if "notes" in changes:
            changes["notes"] = str(changes["notes"]).strip()
        changes["updated_at"] = now_iso()
        assignments = ", ".join(f"{field} = ?" for field in changes)
        try:
            self.db.execute(
                f"UPDATE financial_scenarios SET {assignments} WHERE id = ?",
                (*changes.values(), int(scenario_id)),
            )
        except sqlite3.IntegrityError as exc:
            if "financial_scenarios.name" in str(exc):
                raise ValueError("A scenario with this name already exists.") from None
            raise

    def list(self) -> list[sqlite3.Row]:
        return self.db.fetch_all(
            """SELECT s.*, a.name AS account_name, a.currency AS currency
               FROM financial_scenarios s JOIN accounts a ON a.id = s.account_id
               ORDER BY s.name COLLATE NOCASE"""
        )

    def get(self, scenario_id: int) -> sqlite3.Row | None:
        return self.db.fetch_one(
            """SELECT s.*, a.name AS account_name, a.currency AS currency
               FROM financial_scenarios s JOIN accounts a ON a.id = s.account_id
               WHERE s.id = ?""",
            (int(scenario_id),),
        )

    def delete(self, scenario_id: int) -> None:
        if not self.get(scenario_id):
            raise ValueError("Scenario was not found.")
        self.db.execute(
            "DELETE FROM financial_scenarios WHERE id = ?", (int(scenario_id),)
        )

    def duplicate(self, scenario_id: int, name: str) -> int:
        source = self.get(scenario_id)
        if not source:
            raise ValueError("Scenario was not found.")
        copied_id = self.create(
            name=name,
            account_id=int(source["account_id"]),
            start_date=source["start_date"],
            horizon_months=int(source["horizon_months"]),
            notes=source["notes"],
        )
        for adjustment in self.adjustments(scenario_id):
            self.add_adjustment(
                copied_id,
                name=adjustment["name"],
                kind=adjustment["kind"],
                cadence=adjustment["cadence"],
                amount_minor=int(adjustment["amount_minor"]),
                start_month=int(adjustment["start_month"]),
                end_month=adjustment["end_month"],
                notes=adjustment["notes"],
            )
        return copied_id

    def adjustments(self, scenario_id: int) -> list[sqlite3.Row]:
        if not self.get(scenario_id):
            raise ValueError("Scenario was not found.")
        return self.db.fetch_all(
            """SELECT * FROM scenario_adjustments WHERE scenario_id = ?
               ORDER BY start_month, id""",
            (int(scenario_id),),
        )

    def add_adjustment(
        self,
        scenario_id: int,
        *,
        name: str,
        kind: str,
        cadence: str,
        amount_minor: int,
        start_month: int = 1,
        end_month: int | None = None,
        notes: str = "",
    ) -> int:
        scenario = self.get(scenario_id)
        if not scenario:
            raise ValueError("Scenario was not found.")
        name = str(name).strip()
        if not name:
            raise ValueError("Assumption name is required.")
        if len(name) > 100:
            raise ValueError("Assumption names must be 100 characters or fewer.")
        if kind not in {"income", "expense"}:
            raise ValueError("Assumption type must be income or expense.")
        if cadence not in {"one_time", "monthly"}:
            raise ValueError("Assumption cadence must be one-time or monthly.")
        amount = int(amount_minor)
        if amount <= 0:
            raise ValueError("Assumption amount must be greater than zero.")
        start = int(start_month)
        horizon = int(scenario["horizon_months"])
        if not 1 <= start <= horizon:
            raise ValueError(f"Start month must be between 1 and {horizon}.")
        end = int(end_month) if end_month is not None else None
        if cadence == "one_time":
            end = start
        elif end is not None and not start <= end <= horizon:
            raise ValueError(f"End month must be between {start} and {horizon}.")
        timestamp = now_iso()
        return self.db.execute(
            """INSERT INTO scenario_adjustments(
                scenario_id, name, kind, cadence, amount_minor,
                start_month, end_month, notes, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (int(scenario_id), name, kind, cadence, amount,
             start, end, str(notes).strip(), timestamp, timestamp),
        )

    def update_adjustment(self, adjustment_id: int, **fields: Any) -> None:
        row = self.db.fetch_one(
            "SELECT * FROM scenario_adjustments WHERE id = ?", (int(adjustment_id),)
        )
        if not row:
            raise ValueError("Scenario assumption was not found.")
        values = {
            "name": fields.get("name", row["name"]),
            "kind": fields.get("kind", row["kind"]),
            "cadence": fields.get("cadence", row["cadence"]),
            "amount_minor": fields.get("amount_minor", row["amount_minor"]),
            "start_month": fields.get("start_month", row["start_month"]),
            "end_month": fields.get("end_month", row["end_month"]),
            "notes": fields.get("notes", row["notes"]),
        }
        scenario = self.get(int(row["scenario_id"]))
        if not scenario:
            raise ValueError("Scenario was not found.")
        start = int(values["start_month"])
        horizon = int(scenario["horizon_months"])
        if values["cadence"] == "one_time":
            values["end_month"] = start
        elif values["end_month"] is not None:
            values["end_month"] = int(values["end_month"])
        self._validate_adjustment_values(values, horizon)
        values["name"] = str(values["name"]).strip()
        if not values["name"]:
            raise ValueError("Assumption name is required.")
        if len(values["name"]) > 100:
            raise ValueError("Assumption names must be 100 characters or fewer.")
        values["amount_minor"] = int(values["amount_minor"])
        values["start_month"] = start
        values["notes"] = str(values["notes"]).strip()
        values["updated_at"] = now_iso()
        assignments = ", ".join(f"{field} = ?" for field in values)
        self.db.execute(
            f"UPDATE scenario_adjustments SET {assignments} WHERE id = ?",
            (*values.values(), int(adjustment_id)),
        )

    @staticmethod
    def _validate_adjustment_values(values: dict[str, Any], horizon: int) -> None:
        if values["kind"] not in {"income", "expense"}:
            raise ValueError("Assumption type must be income or expense.")
        if values["cadence"] not in {"one_time", "monthly"}:
            raise ValueError("Assumption cadence must be one-time or monthly.")
        if int(values["amount_minor"]) <= 0:
            raise ValueError("Assumption amount must be greater than zero.")
        start = int(values["start_month"])
        if not 1 <= start <= horizon:
            raise ValueError(f"Start month must be between 1 and {horizon}.")
        end = values["end_month"]
        if end is not None and not start <= int(end) <= horizon:
            raise ValueError(f"End month must be between {start} and {horizon}.")

    def delete_adjustment(self, adjustment_id: int) -> None:
        existing = self.db.fetch_one(
            "SELECT id FROM scenario_adjustments WHERE id = ?", (int(adjustment_id),)
        )
        if not existing:
            raise ValueError("Scenario assumption was not found.")
        self.db.execute(
            "DELETE FROM scenario_adjustments WHERE id = ?", (int(adjustment_id),)
        )

    def preview(self, scenario_id: int) -> dict[str, Any]:
        scenario = self.get(scenario_id)
        if not scenario:
            raise ValueError("Scenario was not found.")
        start_date = date.fromisoformat(scenario["start_date"])
        first_month = start_date.replace(day=1)
        horizon = int(scenario["horizon_months"])
        exclusive_end = add_months(first_month, horizon)
        end_date = date.fromordinal(exclusive_end.toordinal() - 1)
        days = (end_date - start_date).days
        baseline = self.forecast.project(days=max(days, 1), as_of=start_date.isoformat())
        account_id = int(scenario["account_id"])
        account_events = [
            event for event in baseline["events"]
            if event["account_id"] == account_id
        ]
        adjustments = self.adjustments(scenario_id)
        months: list[dict[str, Any]] = []
        opening_balance = self.forecast._account_balance_at(account_id, start_date.isoformat())
        baseline_balance = opening_balance
        scenario_balance = opening_balance
        for month_index in range(1, horizon + 1):
            month_date = add_months(first_month, month_index - 1)
            month_key = month_date.strftime("%Y-%m")
            month_events = [
                event for event in account_events if event["date"][:7] == month_key
            ]
            baseline_income = sum(
                int(event["amount_minor"]) for event in month_events
                if event["kind"] == "income"
            )
            baseline_expenses = sum(
                int(event["amount_minor"]) for event in month_events
                if event["kind"] == "expense"
            )
            planned_income = 0
            planned_expenses = 0
            active_adjustments = []
            for adjustment in adjustments:
                if month_index < int(adjustment["start_month"]):
                    continue
                if adjustment["end_month"] is not None and month_index > int(adjustment["end_month"]):
                    continue
                if adjustment["cadence"] == "one_time" and month_index != int(adjustment["start_month"]):
                    continue
                amount = int(adjustment["amount_minor"])
                if adjustment["kind"] == "income":
                    planned_income += amount
                else:
                    planned_expenses += amount
                active_adjustments.append({
                    "id": int(adjustment["id"]),
                    "name": adjustment["name"],
                    "kind": adjustment["kind"],
                    "amount_minor": amount,
                })

            baseline_net = baseline_income - baseline_expenses
            scenario_income = baseline_income + planned_income
            scenario_expenses = baseline_expenses + planned_expenses
            scenario_net = scenario_income - scenario_expenses
            baseline_balance += baseline_net
            scenario_balance += scenario_net
            months.append({
                "month": month_key,
                "baseline_income_minor": baseline_income,
                "baseline_expenses_minor": baseline_expenses,
                "planned_income_minor": planned_income,
                "planned_expenses_minor": planned_expenses,
                "scenario_income_minor": scenario_income,
                "scenario_expenses_minor": scenario_expenses,
                "baseline_net_minor": baseline_net,
                "scenario_net_minor": scenario_net,
                "baseline_balance_minor": baseline_balance,
                "scenario_balance_minor": scenario_balance,
                "difference_minor": scenario_balance - baseline_balance,
                "below_zero": scenario_balance < 0,
                "adjustments": active_adjustments,
            })

        return {
            "scenario": dict(scenario),
            "currency": str(scenario["currency"]).upper(),
            "opening_balance_minor": opening_balance,
            "months": months,
            "ending_baseline_minor": baseline_balance,
            "ending_scenario_minor": scenario_balance,
            "ending_difference_minor": scenario_balance - baseline_balance,
            "first_negative_month": next(
                (month["month"] for month in months if month["below_zero"]), None
            ),
            "baseline_events": account_events,
        }

    def export_csv(self, scenario_id: int, path: str | Path) -> int:
        preview = self.preview(scenario_id)
        scenario = preview["scenario"]
        currency = preview["currency"]
        columns = [
            "scenario", "month", "currency", "baseline_income", "baseline_expenses",
            "planned_income", "planned_expenses", "scenario_income", "scenario_expenses",
            "baseline_closing_balance", "scenario_closing_balance", "difference",
            "below_zero", "assumptions",
        ]
        with Path(path).expanduser().open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for month in preview["months"]:
                writer.writerow({
                    "scenario": scenario["name"],
                    "month": month["month"],
                    "currency": currency,
                    "baseline_income": self._major_amount(month["baseline_income_minor"]),
                    "baseline_expenses": self._major_amount(month["baseline_expenses_minor"]),
                    "planned_income": self._major_amount(month["planned_income_minor"]),
                    "planned_expenses": self._major_amount(month["planned_expenses_minor"]),
                    "scenario_income": self._major_amount(month["scenario_income_minor"]),
                    "scenario_expenses": self._major_amount(month["scenario_expenses_minor"]),
                    "baseline_closing_balance": self._major_amount(month["baseline_balance_minor"]),
                    "scenario_closing_balance": self._major_amount(month["scenario_balance_minor"]),
                    "difference": self._major_amount(month["difference_minor"]),
                    "below_zero": month["below_zero"],
                    "assumptions": "; ".join(
                        f"{item['kind']}:{item['name']}:{self._major_amount(item['amount_minor'])}"
                        for item in month["adjustments"]
                    ),
                })
        return len(preview["months"])

    @staticmethod
    def _major_amount(amount_minor: int) -> str:
        return str(Decimal(int(amount_minor)) / Decimal(100))

    def compare(self, scenario_ids: list[int]) -> dict[str, Any]:
        ids = list(dict.fromkeys(int(item) for item in scenario_ids))
        if not 2 <= len(ids) <= self.MAX_COMPARISON_SCENARIOS:
            raise ValueError("Choose between two and five different scenarios to compare.")
        previews = [self.preview(scenario_id) for scenario_id in ids]
        first = previews[0]["scenario"]
        signature = (
            int(first["account_id"]), first["start_date"], int(first["horizon_months"]),
        )
        for preview in previews[1:]:
            item = preview["scenario"]
            if (
                int(item["account_id"]), item["start_date"], int(item["horizon_months"]),
            ) != signature:
                raise ValueError(
                    "Scenarios must use the same account, start date, and horizon to compare."
                )
        return {
            "currency": previews[0]["currency"],
            "scenarios": previews,
            "ending_balances": [
                {
                    "scenario_id": int(preview["scenario"]["id"]),
                    "name": preview["scenario"]["name"],
                    "ending_balance_minor": preview["ending_scenario_minor"],
                    "difference_minor": preview["ending_difference_minor"],
                    "first_negative_month": preview["first_negative_month"],
                }
                for preview in previews
            ],
        }