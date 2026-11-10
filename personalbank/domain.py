from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"
    LOAN = "loan"
    OTHER = "other"


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class CategoryType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class Frequency(str, Enum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


def to_minor_units(value: str | int | float | Decimal) -> int:
    """Convert an entered monetary amount to integer cents."""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Enter a valid monetary amount.") from exc
    if not amount.is_finite():
        raise ValueError("Amount must be a finite number.")
    return int(amount * 100)


def from_minor_units(value: int) -> Decimal:
    return (Decimal(int(value)) / Decimal(100)).quantize(Decimal("0.01"))


def validate_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc
    return parsed.isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def month_iso(value: str) -> str:
    try:
        parsed = date.fromisoformat(value + "-01")
    except (TypeError, ValueError) as exc:
        raise ValueError("Month must use YYYY-MM format.") from exc
    return parsed.strftime("%Y-%m")
