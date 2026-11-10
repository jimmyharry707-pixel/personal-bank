from __future__ import annotations

from datetime import date

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView, QAbstractItemView,
    QDialogButtonBox, QLabel,
)

from .dialogs import BaseDialog
from .domain import to_minor_units, today_iso


class RecurringDialog(BaseDialog):
    def __init__(self, parent, accounts, categories):
        super().__init__("Add recurring transaction", parent)
        self._categories = categories
        self.name = self.add_text("Schedule name")
        self.kind = self.add_combo("Transaction type", [("Expense", "expense"), ("Income", "income")])
        self.account = self.add_combo("Account", [(a["name"], int(a["id"])) for a in accounts])
        self.category = self.add_combo("Category", [("None", None)])
        self.amount = self.add_amount("Amount")
        self.frequency = self.add_combo("Frequency", [
            ("Weekly", "weekly"), ("Every two weeks", "biweekly"),
            ("Monthly", "monthly"), ("Quarterly", "quarterly"), ("Yearly", "yearly"),
        ])
        self.next_due = self.add_date("First due date")
        self.has_end_date = QCheckBox("Set an end date")
        self.form.addRow("", self.has_end_date)
        self.end_date = self.add_date("End date")
        self.payee = self.add_text("Payee")
        self.description = self.add_text("Description")
        self.notes = self.add_notes()
        self.kind.currentIndexChanged.connect(self._refresh_categories)
        self.has_end_date.toggled.connect(self._toggle_end_date)
        self._refresh_categories()
        self._toggle_end_date(False)

    def _refresh_categories(self):
        kind = self.kind.currentData()
        self.category.clear()
        self.category.addItem("None", None)
        for category in self._categories:
            if category["kind"] == kind:
                self.category.addItem(category["name"], int(category["id"]))

    def _toggle_end_date(self, enabled: bool):
        self.end_date.setEnabled(enabled)
        label = self.form.labelForField(self.end_date)
        if label:
            label.setEnabled(enabled)

    def values(self):
        return {
            "name": self.name.text().strip(),
            "kind": self.kind.currentData(),
            "account_id": int(self.account.currentData()),
            "category_id": self.category.currentData(),
            "amount_minor": to_minor_units(self.amount.value()),
            "frequency": self.frequency.currentData(),
            "next_due_date": self.next_due.date().toString("yyyy-MM-dd"),
            "end_date": self.end_date.date().toString("yyyy-MM-dd") if self.has_end_date.isChecked() else None,
            "payee": self.payee.text().strip(),
            "description": self.description.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class FinancialScenarioDialog(BaseDialog):
    def __init__(self, parent, accounts, scenario=None):
        super().__init__("Financial planning scenario", parent)
        self.name = self.add_text("Scenario name", scenario["name"] if scenario else "")
        account_options = [(a["name"], int(a["id"])) for a in accounts if a["is_active"]]
        self.account = self.add_combo("Forecast account", account_options)
        if scenario:
            self.account.setCurrentIndex(
                max(0, self.account.findData(int(scenario["account_id"])))
            )
        self.start_date = self.add_date(
            "Projection start date", scenario["start_date"] if scenario else None
        )
        self.horizon = QSpinBox()
        self.horizon.setRange(1, 60)
        self.horizon.setSuffix(" months")
        self.horizon.setValue(int(scenario["horizon_months"]) if scenario else 12)
        self.form.addRow("Projection horizon", self.horizon)
        self.notes = self.add_notes()
        if scenario:
            self.notes.setPlainText(scenario["notes"])

    def values(self):
        return {
            "name": self.name.text().strip(),
            "account_id": int(self.account.currentData()),
            "start_date": self.start_date.date().toString("yyyy-MM-dd"),
            "horizon_months": self.horizon.value(),
            "notes": self.notes.toPlainText().strip(),
        }


class ScenarioAdjustmentDialog(BaseDialog):
    def __init__(self, parent, horizon_months: int, adjustment=None):
        super().__init__("Scenario assumption", parent)
        self.horizon_months = int(horizon_months)
        self.name = self.add_text("Assumption name", adjustment["name"] if adjustment else "")
        self.kind = self.add_combo("Type", [
            ("Expense", "expense"), ("Income", "income"),
        ])
        self.cadence = self.add_combo("Schedule", [
            ("One-time", "one_time"), ("Monthly", "monthly"),
        ])
        self.amount = self.add_amount(
            "Amount", int(adjustment["amount_minor"]) / 100 if adjustment else 0.0
        )
        self.start_month = QSpinBox()
        self.start_month.setRange(1, self.horizon_months)
        self.start_month.setPrefix("Month ")
        self.start_month.setValue(int(adjustment["start_month"]) if adjustment else 1)
        self.form.addRow("Starts in", self.start_month)
        self.end_month = QSpinBox()
        self.end_month.setRange(0, self.horizon_months)
        self.end_month.setSpecialValueText("Through horizon")
        self.end_month.setPrefix("Month ")
        self.end_month.setValue(
            int(adjustment["end_month"])
            if adjustment and adjustment["end_month"] is not None else 0
        )
        self.form.addRow("Ends in", self.end_month)
        self.notes = self.add_notes()
        if adjustment:
            self.kind.setCurrentIndex(max(0, self.kind.findData(adjustment["kind"])))
            self.cadence.setCurrentIndex(max(0, self.cadence.findData(adjustment["cadence"])))
            self.notes.setPlainText(adjustment["notes"])
        self.cadence.currentIndexChanged.connect(self._sync_end_month)
        self._sync_end_month()

    def _sync_end_month(self):
        monthly = self.cadence.currentData() == "monthly"
        self.end_month.setEnabled(monthly)
        label = self.form.labelForField(self.end_month)
        if label:
            label.setEnabled(monthly)

    def values(self):
        return {
            "name": self.name.text().strip(),
            "kind": self.kind.currentData(),
            "cadence": self.cadence.currentData(),
            "amount_minor": to_minor_units(self.amount.value()),
            "start_month": self.start_month.value(),
            "end_month": self.end_month.value() or None,
            "notes": self.notes.toPlainText().strip(),
        }


class DebtPlanDialog(BaseDialog):
    def __init__(self, parent, accounts):
        super().__init__("Add debt plan", parent)
        self.name = self.add_text("Debt name")
        self.creditor = self.add_text("Creditor / lender")
        self.principal = self.add_amount("Current principal")
        self.apr = QDoubleSpinBox()
        self.apr.setRange(0, 100)
        self.apr.setDecimals(3)
        self.apr.setSuffix(" %")
        self.form.addRow("Annual interest rate", self.apr)
        self.minimum = self.add_amount("Monthly payment")
        self.account = self.add_combo("Pay from", [
            (a["name"], int(a["id"])) for a in accounts
            if a["kind"] in {"checking", "savings", "cash"}
        ])
        self.due_day = QSpinBox()
        self.due_day.setRange(1, 31)
        self.due_day.setValue(1)
        self.form.addRow("Payment due day", self.due_day)
        self.start_date = self.add_date("Plan start date")
        self.notes = self.add_notes()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "creditor": self.creditor.text().strip(),
            "principal_minor": to_minor_units(self.principal.value()),
            "apr_basis_points": int(round(self.apr.value() * 100)),
            "minimum_payment_minor": to_minor_units(self.minimum.value()),
            "payment_account_id": int(self.account.currentData()),
            "due_day": self.due_day.value(),
            "start_date": self.start_date.date().toString("yyyy-MM-dd"),
            "notes": self.notes.toPlainText().strip(),
        }


class DebtPaymentDialog(BaseDialog):
    def __init__(self, parent, debt_name: str, minimum_minor: int):
        super().__init__(f"Record payment — {debt_name}", parent)
        self.amount = self.add_amount("Total payment", minimum_minor / 100)
        self.payment_date = self.add_date("Payment date")
        self.notes = self.add_notes()

    def values(self):
        return {
            "payment_minor": to_minor_units(self.amount.value()),
            "payment_date": self.payment_date.date().toString("yyyy-MM-dd"),
            "notes": self.notes.toPlainText().strip(),
        }


class SecurityDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__("Add investment security", parent)
        self.symbol = self.add_text("Symbol / ticker")
        self.name = self.add_text("Security name")
        self.asset_type = self.add_combo("Asset type", [
            ("Stock", "stock"), ("ETF", "etf"), ("Mutual fund", "mutual_fund"),
            ("Bond", "bond"), ("Crypto", "crypto"), ("Other", "other"),
        ])
        self.currency = self.add_text("Currency", "USD")

    def values(self):
        return self.symbol.text(), self.name.text(), self.asset_type.currentData(), self.currency.text()


class TradeDialog(BaseDialog):
    def __init__(self, parent, accounts, securities):
        super().__init__("Record investment trade", parent)
        investment_accounts = [a for a in accounts if a["kind"] == "investment"]
        self.account = self.add_combo("Investment account", [
            (a["name"], int(a["id"])) for a in investment_accounts
        ])
        self.security = self.add_combo("Security", [
            (f"{s['symbol']} — {s['name']}", int(s["id"])) for s in securities
        ])
        self.side = self.add_combo("Action", [("Buy", "buy"), ("Sell", "sell")])
        self.quantity = QDoubleSpinBox()
        self.quantity.setDecimals(6)
        self.quantity.setRange(0.000001, 999999999)
        self.quantity.setValue(1.0)
        self.form.addRow("Quantity / shares", self.quantity)
        self.price = self.add_amount("Price per share")
        self.commission = self.add_amount("Commission / fees")
        self.trade_date = self.add_date("Trade date")
        self.notes = self.add_notes()

    def values(self):
        return {
            "investment_account_id": int(self.account.currentData()),
            "security_id": int(self.security.currentData()),
            "side": self.side.currentData(),
            "quantity_micros": int(round(self.quantity.value() * 1_000_000)),
            "price_minor": to_minor_units(self.price.value()),
            "commission_minor": to_minor_units(self.commission.value()),
            "trade_date": self.trade_date.date().toString("yyyy-MM-dd"),
            "notes": self.notes.toPlainText().strip(),
        }


class SecurityPriceDialog(BaseDialog):
    def __init__(self, parent, symbol: str, current_price_minor: int):
        super().__init__(f"Update market price — {symbol}", parent)
        self.price = self.add_amount("Current price per share", current_price_minor / 100)

    def values(self):
        return to_minor_units(self.price.value())


class ReconciliationStartDialog(BaseDialog):
    def __init__(self, parent, accounts):
        super().__init__("Start bank reconciliation", parent)
        self.account = self.add_combo("Account", [
            (a["name"], int(a["id"])) for a in accounts
        ])
        self.statement_date = self.add_date("Statement ending date")
        self.statement_balance = self.add_amount("Statement ending balance")
        self.notes = self.add_notes()

    def values(self):
        return (
            int(self.account.currentData()),
            self.statement_date.date().toString("yyyy-MM-dd"),
            to_minor_units(self.statement_balance.value()),
            self.notes.toPlainText().strip(),
        )


class NetWorthSnapshotDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__("Save net-worth snapshot", parent)
        self.snapshot_date = self.add_date("Snapshot date")
        self.notes = self.add_notes()

    def values(self):
        return self.snapshot_date.date().toString("yyyy-MM-dd"), self.notes.toPlainText().strip()


class CategoryDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__("Add category", parent)
        self.name = self.add_text("Category name")
        self.kind = self.add_combo("Category type", [("Expense", "expense"), ("Income", "income")])
        self.color = self.add_text("Color (hex)", "#64748b")

    def values(self):
        return self.name.text().strip(), self.kind.currentData(), self.color.text().strip()


class DebtScheduleDialog(QDialog):
    def __init__(self, parent, debt_name: str, rows, currency: str = "USD"):
        super().__init__(parent)
        self.setWindowTitle(f"Payoff schedule — {debt_name}")
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Projection assumes a fixed APR and the planned payment each month."))
        table = QTableWidget(len(rows), 7)
        table.setHorizontalHeaderLabels([
            "Period", "Date", "Opening balance", "Interest", "Payment", "Principal", "Closing balance"
        ])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row_index, row in enumerate(rows):
            values = [
                row["period"], row["date"], row["opening_minor"] / 100,
                row["interest_minor"] / 100, row["payment_minor"] / 100,
                row["principal_minor"] / 100, row["closing_minor"] / 100,
            ]
            for column, value in enumerate(values):
                if column >= 2:
                    value = f"{currency} {float(value):,.2f}"
                table.setItem(row_index, column, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class TransactionEditDialog(BaseDialog):
    """Edit a normal income, expense, or transfer transaction."""

    def __init__(self, parent, transaction, accounts, categories):
        super().__init__("Edit transaction", parent)
        self._categories = categories
        self.kind = self.add_combo("Type", [
            ("Expense", "expense"), ("Income", "income"), ("Transfer", "transfer")
        ])
        self.account = self.add_combo("Account", [
            (a["name"], int(a["id"])) for a in accounts
        ])
        self.target = self.add_combo("Transfer to", [
            (a["name"], int(a["id"])) for a in accounts
        ])
        self.category = self.add_combo("Category", [("None", None)])
        self.amount = self.add_amount("Amount", int(transaction["amount_minor"]) / 100)
        self.when = self.add_date("Date", transaction["occurred_on"])
        self.payee = self.add_text("Payee", transaction["payee"])
        self.description = self.add_text("Description", transaction["description"])
        self.reference = self.add_text("Reference", transaction["reference"])
        self.notes = self.add_notes()
        self.notes.setPlainText(transaction["notes"])
        self.kind.currentIndexChanged.connect(self._refresh_fields)
        self.kind.setCurrentIndex(max(0, self.kind.findData(transaction["kind"])))
        self.account.setCurrentIndex(max(0, self.account.findData(int(transaction["account_id"]))))
        if transaction["transfer_account_id"] is not None:
            self.target.setCurrentIndex(max(0, self.target.findData(int(transaction["transfer_account_id"]))))
        self._refresh_fields()
        if transaction["category_id"] is not None:
            self.category.setCurrentIndex(max(0, self.category.findData(int(transaction["category_id"]))))

    def _refresh_fields(self):
        kind = self.kind.currentData()
        is_transfer = kind == "transfer"
        self.target.setVisible(is_transfer)
        self.category.setVisible(not is_transfer)
        for widget in (self.target, self.category):
            label = self.form.labelForField(widget)
            if label:
                label.setVisible(widget.isVisible())
        self.category.clear()
        self.category.addItem("None", None)
        expected = "income" if kind == "income" else "expense"
        for category in self._categories:
            if category["kind"] == expected and category["is_active"]:
                self.category.addItem(category["name"], int(category["id"]))

    def values(self):
        return {
            "kind": self.kind.currentData(),
            "account_id": int(self.account.currentData()),
            "transfer_account_id": int(self.target.currentData()) if self.kind.currentData() == "transfer" else None,
            "category_id": self.category.currentData() if self.kind.currentData() != "transfer" else None,
            "amount_minor": to_minor_units(self.amount.value()),
            "occurred_on": self.when.date().toString("yyyy-MM-dd"),
            "payee": self.payee.text().strip(),
            "description": self.description.text().strip(),
            "reference": self.reference.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class SubscriptionDialog(BaseDialog):
    def __init__(self, parent, accounts, categories, currency="USD"):
        super().__init__("Add subscription", parent)
        self.name = self.add_text("Subscription name")
        self.vendor = self.add_text("Vendor")
        self.amount = self.add_amount("Price")
        self.currency = self.add_text("Currency", currency)
        self.frequency = self.add_combo("Billing frequency", [
            ("Weekly", "weekly"), ("Every two weeks", "biweekly"),
            ("Monthly", "monthly"), ("Quarterly", "quarterly"), ("Yearly", "yearly"),
        ])
        self.next_renewal = self.add_date("Next renewal")
        self.category = self.add_combo("Expense category", [("None", None)] + [
            (c["name"], int(c["id"])) for c in categories if c["kind"] == "expense"
        ])
        self.account = self.add_combo("Payment account", [("Not assigned", None)] + [
            (a["name"], int(a["id"])) for a in accounts
        ])
        self.trial_end = self.add_text("Trial end (YYYY-MM-DD, optional)")
        self.cancel_by = self.add_text("Cancel by (YYYY-MM-DD, optional)")
        self.website = self.add_text("Website URL")
        self.notes = self.add_notes()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "vendor": self.vendor.text().strip(),
            "amount_minor": to_minor_units(self.amount.value()),
            "currency": self.currency.text().strip().upper(),
            "frequency": self.frequency.currentData(),
            "next_renewal_date": self.next_renewal.date().toString("yyyy-MM-dd"),
            "category_id": self.category.currentData(),
            "account_id": self.account.currentData(),
            "trial_end_date": self.trial_end.text().strip() or None,
            "cancel_by_date": self.cancel_by.text().strip() or None,
            "website_url": self.website.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class SubscriptionPriceDialog(BaseDialog):
    def __init__(self, parent, subscription_name, current_amount_minor):
        super().__init__(f"Update price — {subscription_name}", parent)
        self.amount = self.add_amount("New price", current_amount_minor / 100)
        self.effective_date = self.add_date("Effective date")
        self.notes = self.add_text("Change note")

    def values(self):
        return (
            to_minor_units(self.amount.value()),
            self.effective_date.date().toString("yyyy-MM-dd"),
            self.notes.text().strip(),
        )


class SubscriptionHistoryDialog(QDialog):
    def __init__(self, parent, subscription_name, rows, currency="USD"):
        super().__init__(parent)
        self.setWindowTitle(f"Price history — {subscription_name}")
        self.resize(650, 360)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["Effective date", "Old price", "New price", "Notes"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for index, row in enumerate(rows):
            old = "—" if row["old_amount_minor"] is None else f"{currency} {int(row['old_amount_minor']) / 100:,.2f}"
            values = [
                row["effective_date"], old,
                f"{currency} {int(row['new_amount_minor']) / 100:,.2f}",
                row["notes"],
            ]
            for column, value in enumerate(values):
                table.setItem(index, column, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class TaxRecordDialog(BaseDialog):
    TREATMENTS = [
        ("Deductible expense", "deductible_expense"),
        ("Non-deductible expense", "non_deductible_expense"),
        ("Tax payment", "tax_payment"),
        ("Taxable income", "taxable_income"),
        ("Tax-exempt income", "tax_exempt_income"),
        ("Capital gain", "capital_gain"),
        ("Other", "other"),
    ]

    def __init__(self, parent, transactions):
        super().__init__("Classify transaction for tax records", parent)
        self.transaction = self.add_combo("Transaction", [
            (
                f"{row['occurred_on']} · {row['kind']} · "
                f"{row['payee'] or row['description'] or 'Transaction'} · "
                f"{int(row['amount_minor']) / 100:,.2f}",
                int(row["id"]),
            )
            for row in transactions
        ])
        self.treatment = self.add_combo("Treatment", self.TREATMENTS)
        self.category = self.add_text("Tax category")
        self.deductible = QDoubleSpinBox()
        self.deductible.setRange(0, 100)
        self.deductible.setDecimals(1)
        self.deductible.setSuffix(" %")
        self.deductible.setValue(100)
        self.form.addRow("Deductible share", self.deductible)
        self.notes = self.add_notes()
        self.treatment.currentIndexChanged.connect(self._update_deductible)
        self._update_deductible()

    def _update_deductible(self):
        enabled = self.treatment.currentData() == "deductible_expense"
        self.deductible.setEnabled(enabled)
        label = self.form.labelForField(self.deductible)
        if label:
            label.setEnabled(enabled)

    def values(self):
        return {
            "transaction_id": int(self.transaction.currentData()),
            "treatment": self.treatment.currentData(),
            "tax_category": self.category.text().strip(),
            "deductible_basis_points": int(round(self.deductible.value() * 100)),
            "notes": self.notes.toPlainText().strip(),
        }


class CategorizationRuleDialog(BaseDialog):
    def __init__(self, parent, categories):
        super().__init__("Add auto-categorization rule", parent)
        self.name = self.add_text("Rule name")
        self.keyword = self.add_text("Contains keyword")
        self.match_field = self.add_combo("Search field", [
            ("Payee", "payee"), ("Description", "description"), ("Either", "any")
        ])
        self.kind = self.add_combo("Transaction type", [
            ("Expense", "expense"), ("Income", "income")
        ])
        self.category = self.add_combo("Assign category", [])
        self.priority = QSpinBox()
        self.priority.setRange(-10000, 10000)
        self.priority.setValue(100)
        self.form.addRow("Priority (higher first)", self.priority)
        self._categories = categories
        self.kind.currentIndexChanged.connect(self._refresh_categories)
        self._refresh_categories()

    def _refresh_categories(self):
        kind = self.kind.currentData()
        self.category.clear()
        for category in self._categories:
            if category["kind"] == kind:
                self.category.addItem(category["name"], int(category["id"]))

    def values(self):
        return {
            "name": self.name.text().strip(),
            "keyword": self.keyword.text().strip(),
            "match_field": self.match_field.currentData(),
            "transaction_kind": self.kind.currentData(),
            "category_id": int(self.category.currentData()),
            "priority": self.priority.value(),
        }

