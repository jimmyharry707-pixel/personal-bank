from __future__ import annotations

from decimal import Decimal


def money(minor_units: int, currency: str = "USD") -> str:
    amount = Decimal(int(minor_units)) / Decimal(100)
    return f"{currency.upper()} {amount:,.2f}"


def signed_money(minor_units: int, currency: str = "USD") -> str:
    prefix = "+" if minor_units > 0 else ""
    return prefix + money(minor_units, currency)


def humanize(value: str) -> str:
    return value.replace("_", " ").title()
