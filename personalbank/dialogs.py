from __future__ import annotations

from datetime import date
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QSpinBox, QTextEdit, QDoubleSpinBox, QVBoxLayout,
)

from .domain import to_minor_units, today_iso


class BaseDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(430)
        self.form = QFormLayout()
        self.root = QVBoxLayout(self)
        self.root.addLayout(self.form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.root.addWidget(self.buttons)

    def add_text(self, label: str, value: str = "") -> QLineEdit:
        widget = QLineEdit(value)
        self.form.addRow(label, widget)
        return widget

    def add_amount(self, label: str, value: float = 0.0) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(2)
        widget.setMaximum(999999999.99)
        widget.setMinimum(0.0)
        widget.setValue(value)
        self.form.addRow(label, widget)
        return widget

    def add_combo(self, label: str, options: list[tuple[str, object]]) -> QComboBox:
        widget = QComboBox()
        for text, data in options:
            widget.addItem(text, data)
        self.form.addRow(label, widget)
        return widget

    def add_date(self, label: str, value: str | None = None) -> QDateEdit:
        widget = QDateEdit()
        widget.setCalendarPopup(True)
        widget.setDisplayFormat("yyyy-MM-dd")
        chosen = date.fromisoformat(value or today_iso())
        widget.setDate(chosen)
        self.form.addRow(label, widget)
        return widget

    def add_notes(self, label: str = "Notes") -> QTextEdit:
        widget = QTextEdit()
        widget.setMaximumHeight(80)
        self.form.addRow(label, widget)
        return widget


class AccountDialog(BaseDialog):
    def __init__(self, parent=None, account=None, currency="USD"):
        super().__init__("Account", parent)
        self.name = self.add_text("Account name", account["name"] if account else "")
        self.kind = self.add_combo("Type", [
            ("Checking", "checking"), ("Savings", "savings"), ("Cash", "cash"),
            ("Credit card", "credit_card"), ("Investment", "investment"),
            ("Loan", "loan"), ("Other", "other"),
        ])
        self.currency = self.add_text("Currency (ISO code)", account["currency"] if account else currency)
        self.opening = self.add_amount(
            "Opening balance", (int(account["opening_balance_minor"]) / 100) if account else 0.0
        )
        self.limit = self.add_amount(
            "Credit limit", (int(account["credit_limit_minor"]) / 100) if account else 0.0
        )
        if account:
            self.kind.setCurrentIndex(max(0, self.kind.findData(account["kind"])))

    def values(self):
        return {
            "name": self.name.text().strip(),
            "kind": self.kind.currentData(),
            "currency": self.currency.text().strip().upper(),
            "opening_balance_minor": to_minor_units(self.opening.value()),
            "credit_limit_minor": to_minor_units(self.limit.value()),
        }


class TransactionDialog(BaseDialog):
    def __init__(self, parent, accounts, categories, default_currency="USD"):
        super().__init__("Add transaction", parent)
        self.kind = self.add_combo("Type", [
            ("Expense", "expense"), ("Income", "income"), ("Transfer", "transfer")
        ])
        self.account = self.add_combo("Account", [(a["name"], int(a["id"])) for a in accounts])
        self.target = self.add_combo("Transfer to", [(a["name"], int(a["id"])) for a in accounts])
        self.category = self.add_combo("Category", [("None", None)] + [
            (c["name"], int(c["id"])) for c in categories
        ])
        self.amount = self.add_amount("Amount")
        self.when = self.add_date("Date")
        self.payee = self.add_text("Payee")
        self.description = self.add_text("Description")
        self.reference = self.add_text("Reference")
        self.notes = self.add_notes()
        self.kind.currentIndexChanged.connect(self._update_fields)
        self._update_fields()

    def _update_fields(self):
        is_transfer = self.kind.currentData() == "transfer"
        self.target.setVisible(is_transfer)
        self.category.setVisible(not is_transfer)
        target_label = self.form.labelForField(self.target)
        category_label = self.form.labelForField(self.category)
        if target_label:
            target_label.setVisible(is_transfer)
        if category_label:
            category_label.setVisible(not is_transfer)

    def values(self):
        return {
            "kind": self.kind.currentData(),
            "account_id": int(self.account.currentData()),
            "transfer_account_id": int(self.target.currentData()),
            "category_id": self.category.currentData(),
            "amount_minor": to_minor_units(self.amount.value()),
            "occurred_on": self.when.date().toString("yyyy-MM-dd"),
            "payee": self.payee.text().strip(),
            "description": self.description.text().strip(),
            "reference": self.reference.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class BudgetDialog(BaseDialog):
    def __init__(self, parent, categories, month: str):
        super().__init__("Set monthly budget", parent)
        self.category = self.add_combo("Expense category", [
            (c["name"], int(c["id"])) for c in categories
        ])
        self.month = self.add_text("Month (YYYY-MM)", month)
        self.amount = self.add_amount("Budget amount")

    def values(self):
        return int(self.category.currentData()), self.month.text().strip(), to_minor_units(self.amount.value())


class BillDialog(BaseDialog):
    def __init__(self, parent, accounts, categories):
        super().__init__("Add recurring bill", parent)
        self.name = self.add_text("Bill name")
        self.amount = self.add_amount("Amount")
        self.due_day = QSpinBox()
        self.due_day.setRange(1, 31)
        self.due_day.setValue(1)
        self.form.addRow("Day of month", self.due_day)
        self.category = self.add_combo("Category", [("None", None)] + [
            (c["name"], int(c["id"])) for c in categories
        ])
        self.account = self.add_combo("Pay from", [("Not assigned", None)] + [
            (a["name"], int(a["id"])) for a in accounts
        ])
        self.frequency = self.add_combo("Frequency", [
            ("Weekly", "weekly"), ("Every two weeks", "biweekly"),
            ("Monthly", "monthly"), ("Quarterly", "quarterly"), ("Yearly", "yearly"),
        ])
        self.next_due = self.add_date("Next due date")
        self.notes = self.add_notes()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "amount_minor": to_minor_units(self.amount.value()),
            "due_day": self.due_day.value(),
            "category_id": self.category.currentData(),
            "account_id": self.account.currentData(),
            "frequency": self.frequency.currentData(),
            "auto_post": False,
            "next_due_date": self.next_due.date().toString("yyyy-MM-dd"),
            "notes": self.notes.toPlainText().strip(),
        }


class GoalDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__("Create savings goal", parent)
        self.name = self.add_text("Goal name")
        self.target = self.add_amount("Target amount")
        self.target_date = self.add_date("Target date")
        self.notes = self.add_notes()

    def values(self):
        return (
            self.name.text().strip(),
            to_minor_units(self.target.value()),
            self.target_date.date().toString("yyyy-MM-dd"),
            self.notes.toPlainText().strip(),
        )


class ContributionDialog(BaseDialog):
    def __init__(self, parent, goal_name: str):
        super().__init__(f"Add to {goal_name}", parent)
        self.amount = self.add_amount("Contribution amount")

    def values(self):
        return to_minor_units(self.amount.value())
