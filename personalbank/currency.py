from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .domain import now_iso


class CurrencyValuationService:
    """Manual exchange rates and current-valuation reporting."""

    def __init__(self, finance, investments=None):
        self.finance = finance
        self.db = finance.db
        if investments is None:
            from .advanced import InvestmentService

            investments = InvestmentService(finance)
        self.investments = investments

    @staticmethod
    def _currency(value: str) -> str:
        currency = str(value).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("Currency codes must contain three letters.")
        return currency

    def set_rate(
        self, from_currency: str, to_currency: str, rate: Decimal | str | int | float,
    ) -> None:
        source = self._currency(from_currency)
        target = self._currency(to_currency)
        if source == target:
            raise ValueError("Choose two different currencies.")
        try:
            value = Decimal(str(rate))
        except (InvalidOperation, ValueError):
            raise ValueError("Enter a valid exchange rate.") from None
        if not value.is_finite() or value <= 0 or value > Decimal("1000000000"):
            raise ValueError("Exchange rate must be greater than zero and at most 1,000,000,000.")
        timestamp = now_iso()
        with self.db.transaction() as connection:
            connection.execute(
                """INSERT INTO exchange_rates(from_currency, to_currency, rate, updated_at)
                   VALUES(?, ?, ?, ?)
                   ON CONFLICT(from_currency, to_currency) DO UPDATE SET
                       rate = excluded.rate, updated_at = excluded.updated_at""",
                (source, target, format(value, "f"), timestamp),
            )
            row = connection.execute(
                """SELECT id FROM exchange_rates
                   WHERE from_currency = ? AND to_currency = ?""",
                (source, target),
            ).fetchone()
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('exchange_rate', ?, 'set', ?, ?)""",
                (int(row["id"]), f"{source}->{target}:{format(value, 'f')}", timestamp),
            )

    def rates(self, to_currency: str | None = None) -> list[Any]:
        if to_currency is None:
            return self.db.fetch_all(
                "SELECT * FROM exchange_rates ORDER BY to_currency, from_currency"
            )
        target = self._currency(to_currency)
        return self.db.fetch_all(
            """SELECT * FROM exchange_rates WHERE to_currency = ?
               ORDER BY from_currency""",
            (target,),
        )

    def delete_rate(self, from_currency: str, to_currency: str) -> None:
        source = self._currency(from_currency)
        target = self._currency(to_currency)
        timestamp = now_iso()
        with self.db.transaction() as connection:
            row = connection.execute(
                """SELECT id FROM exchange_rates
                   WHERE from_currency = ? AND to_currency = ?""",
                (source, target),
            ).fetchone()
            if not row:
                return
            connection.execute(
                "DELETE FROM exchange_rates WHERE id = ?", (int(row["id"]),)
            )
            connection.execute(
                """INSERT INTO audit_log(entity, entity_id, action, details, created_at)
                   VALUES('exchange_rate', ?, 'delete', ?, ?)""",
                (int(row["id"]), f"{source}->{target}", timestamp),
            )

    def rate(self, from_currency: str, to_currency: str) -> Decimal | None:
        source = self._currency(from_currency)
        target = self._currency(to_currency)
        if source == target:
            return Decimal(1)
        row = self.db.fetch_one(
            "SELECT rate FROM exchange_rates WHERE from_currency = ? AND to_currency = ?",
            (source, target),
        )
        if row:
            return Decimal(row["rate"])
        inverse = self.db.fetch_one(
            "SELECT rate FROM exchange_rates WHERE from_currency = ? AND to_currency = ?",
            (target, source),
        )
        return Decimal(1) / Decimal(inverse["rate"]) if inverse else None

    def convert_minor(
        self, amount_minor: int, from_currency: str, to_currency: str,
    ) -> int | None:
        rate = self.rate(from_currency, to_currency)
        if rate is None:
            return None
        converted = Decimal(int(amount_minor)) * rate
        return int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def available_currencies(self) -> list[str]:
        rows = self.db.fetch_all(
            """SELECT currency FROM accounts
               UNION SELECT currency FROM investment_securities
               ORDER BY currency"""
        )
        currencies = {str(row["currency"]).upper() for row in rows}
        debt_rows = self.db.fetch_all(
            """SELECT DISTINCT a.currency FROM debt_plans d
               JOIN accounts a ON a.id = d.payment_account_id"""
        )
        currencies.update(str(row["currency"]).upper() for row in debt_rows)
        currencies.update(
            str(row["currency"]).upper()
            for row in self.db.fetch_all("SELECT DISTINCT currency FROM subscriptions")
        )
        currencies.update(
            str(row["from_currency"]).upper()
            for row in self.db.fetch_all("SELECT from_currency FROM exchange_rates")
        )
        currencies.update(
            str(row["to_currency"]).upper()
            for row in self.db.fetch_all("SELECT to_currency FROM exchange_rates")
        )
        return sorted(currencies)

    def valuation(self, base_currency: str) -> dict[str, Any]:
        base = self._currency(base_currency)
        rows: list[dict[str, Any]] = []

        for account in self.finance.accounts.list(include_inactive=True):
            rows.append({
                "source_type": "account",
                "name": account["name"],
                "currency": str(account["currency"]).upper(),
                "amount_minor": int(self.finance._account_balance_from_row(account)),
                "account_kind": account["kind"],
            })

        for holding in self.investments.holdings():
            rows.append({
                "source_type": "investment",
                "name": f"{holding['symbol']} - {holding['account_name']}",
                "currency": str(holding["currency"]).upper(),
                "amount_minor": int(holding["market_value_minor"]),
                "account_kind": "investment_asset",
            })

        debts = self.db.fetch_all(
            """SELECT d.name, d.principal_minor, a.currency
               FROM debt_plans d JOIN accounts a ON a.id = d.payment_account_id
               WHERE d.principal_minor > 0 ORDER BY d.name COLLATE NOCASE"""
        )
        for debt in debts:
            rows.append({
                "source_type": "debt",
                "name": debt["name"],
                "currency": str(debt["currency"]).upper(),
                "amount_minor": int(debt["principal_minor"]),
                "account_kind": "debt_liability",
            })

        assets = 0
        liabilities = 0
        missing_currencies = set()
        valued_rows = []
        for row in rows:
            converted = self.convert_minor(row["amount_minor"], row["currency"], base)
            if converted is None:
                missing_currencies.add(row["currency"])
            else:
                kind = row["account_kind"]
                if row["source_type"] == "debt":
                    liabilities += max(0, converted)
                elif kind in {"credit_card", "loan"}:
                    liabilities += max(0, -converted)
                    assets += max(0, converted)
                else:
                    assets += max(0, converted)
                    liabilities += max(0, -converted)
            valued_rows.append({**row, "base_minor": converted})

        return {
            "base_currency": base,
            "assets_minor": assets,
            "liabilities_minor": liabilities,
            "net_worth_minor": assets - liabilities,
            "missing_currencies": sorted(missing_currencies),
            "complete": not missing_currencies,
            "rows": valued_rows,
        }