from __future__ import annotations

from decimal import Decimal
from PyQt6.QtCore import QLocale


def money(minor_units: int, currency: str = "USD") -> str:
    amount = Decimal(int(minor_units)) / Decimal(100)
    try:
        return QLocale().toCurrencyString(float(amount), currency)
    except Exception:
        return f"{currency} {amount:,.2f}"


def signed_money(minor_units: int, currency: str = "USD") -> str:
    prefix = "+" if minor_units > 0 else ""
    return prefix + money(minor_units, currency)


def humanize(value: str) -> str:
    return value.replace("_", " ").title()
