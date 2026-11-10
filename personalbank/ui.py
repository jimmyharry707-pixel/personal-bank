from __future__ import annotations

import calendar
import json
import tempfile
from datetime import date

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor, QTextCharFormat
from PyQt6.QtWidgets import (
    QAbstractItemView, QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QFileDialog, QDialog, QInputDialog,
)

from .backup import BackupService
from .attachment_dialogs import ReceiptAttachmentDialog
from .attachments import ReceiptAttachmentService
from .charts import BarChart, HorizontalBars, ScenarioBalanceChart
from .csv_tools import CsvService
from .dialogs import (
    AccountDialog, BillDialog, BudgetDialog, ContributionDialog, GoalDialog,
    TransactionDialog,
)
from .domain import today_iso
from .formatting import humanize, money
from .advanced import (
    CashFlowForecastService, DebtService, InvestmentService, MaintenanceService,
    NetWorthService, ReconciliationService, RecurringTransactionService,
)
from .advanced_dialogs import (
    CategoryDialog, DebtPaymentDialog, DebtPlanDialog, DebtScheduleDialog,
    FinancialScenarioDialog, ScenarioAdjustmentDialog,
    NetWorthSnapshotDialog, ReconciliationStartDialog, RecurringDialog,
    SecurityDialog, SecurityPriceDialog, TradeDialog, TransactionEditDialog,
    SubscriptionDialog, SubscriptionPriceDialog, SubscriptionHistoryDialog,
    TaxRecordDialog, CategorizationRuleDialog,
)
from .productivity import (
    FinanceCalendarService, SubscriptionService, TaxService, CategorizationRuleService,
)
from .currency import CurrencyValuationService
from .scenarios import FinancialScenarioService


STYLE = """
QMainWindow, QWidget { background: #f8fafc; color: #0f172a; font-family: "Segoe UI", Arial; }
QLabel#pageTitle { font-size: 23px; font-weight: 700; color: #0f172a; }
QLabel#muted { color: #64748b; }
QFrame#sidebar { background: #111827; border: none; }
QPushButton#navButton {
    color: #cbd5e1; background: transparent; border: none; text-align: left;
    padding: 12px 15px; border-radius: 8px; font-size: 14px;
}
QPushButton#navButton:hover { background: #1f2937; color: white; }
QPushButton#navButton:checked { background: #2563eb; color: white; font-weight: 600; }
QPushButton#primary {
    color: white; background: #2563eb; border: none; border-radius: 7px;
    padding: 9px 15px; font-weight: 600;
}
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#secondary {
    color: #1e293b; background: white; border: 1px solid #cbd5e1;
    border-radius: 7px; padding: 8px 13px;
}
QLineEdit, QComboBox, QDateEdit, QSpinBox {
    background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 7px;
}
QTableWidget {
    background: white; border: 1px solid #e2e8f0; border-radius: 8px;
    gridline-color: #f1f5f9; selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
QHeaderView::section {
    background: #f1f5f9; color: #475569; padding: 9px; border: none;
    border-bottom: 1px solid #e2e8f0; font-weight: 600;
}
QFrame#card { background: white; border: 1px solid #e2e8f0; border-radius: 10px; }
QLabel#cardLabel { color: #64748b; font-size: 12px; }
QLabel#cardValue { color: #0f172a; font-size: 22px; font-weight: 700; }
"""

NAV_ITEMS = [
    ("Dashboard", "▦"), ("Accounts", "▣"), ("Transactions", "⇄"),
    ("Budgets", "◷"), ("Bills", "▤"), ("Calendar", "▦"), ("Recurring", "⟳"),
    ("Cash flow forecast", "⌁"), ("Reconciliation", "≋"), ("Debt planner", "↘"),
    ("Scenario planner", "↗"),
    ("Investments", "◈"), ("Savings goals", "◎"),
    ("Net worth", "◇"), ("Categories", "▧"),
    ("Currency valuation", "¤"),
    ("Subscriptions", "▣"), ("Tax center", "＄"), ("Auto-categorization", "✧"),
    ("Reports", "▥"), ("Activity log", "≡"), ("Settings", "⚙"),
]


class MetricCard(QFrame):
    def __init__(self, label: str, value: str, hint: str = ""):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(17, 14, 17, 14)
        title = QLabel(label)
        title.setObjectName("cardLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)

    def set_value(self, value: str, hint: str = ""):
        self.value_label.setText(value)
        self.hint_label.setText(hint)


class MainWindow(QMainWindow):
    def __init__(self, finance, config):
        super().__init__()
        self.finance = finance
        self.config = config
        self.csv_service = CsvService(finance)
        self.backup_service = BackupService(finance.db)
        self.attachment_service = ReceiptAttachmentService(finance)
        self.attachment_open_directory = tempfile.TemporaryDirectory(
            prefix="personalbank-receipts-"
        )
        self.recurring_service = RecurringTransactionService(finance)
        self.forecast_service = CashFlowForecastService(finance)
        self.reconciliation_service = ReconciliationService(finance)
        self.debt_service = DebtService(finance)
        self.investment_service = InvestmentService(finance)
        self.net_worth_service = NetWorthService(finance, self.investment_service)
        self.currency_service = CurrencyValuationService(finance, self.investment_service)
        self.scenario_service = FinancialScenarioService(finance, self.forecast_service)
        self.maintenance_service = MaintenanceService(finance.db)
        self.subscription_service = SubscriptionService(finance)
        self.calendar_service = FinanceCalendarService(finance)
        self.tax_service = TaxService(finance)
        self.rule_service = CategorizationRuleService(finance)
        self.current_reconciliation_session_id = None
        self._reconciliation_loading = False
        self.currency = config.currency
        self.setWindowTitle("PersonalBank")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 650)
        self.setStyleSheet(STYLE)
        self._build_shell()
        self._build_pages()
        self.navigate(config.start_page if config.start_page in NAV_ITEMS_NAMES else "Dashboard")
        self.refresh_all()

    def _build_shell(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(215)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(14, 20, 14, 16)
        brand = QLabel("PERSONALBANK")
        brand.setStyleSheet("color: white; font-size: 16px; font-weight: 800; padding: 6px 8px 18px;")
        side_layout.addWidget(brand)
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        nav_widget = QWidget()
        nav_widget.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(3)
        self.nav_buttons = {}
        for name, symbol in NAV_ITEMS:
            button = QPushButton(f"{symbol}   {name}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=name: self.navigate(page))
            self.nav_buttons[name] = button
            nav_layout.addWidget(button)
        nav_layout.addStretch()
        nav_scroll.setWidget(nav_widget)
        side_layout.addWidget(nav_scroll, 1)
        footer = QLabel("LOCAL DATABASE\nNo server • No cloud")
        footer.setStyleSheet("color: #94a3b8; font-size: 10px; padding: 8px;")
        side_layout.addWidget(footer)
        root.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 22, 26, 22)
        content_layout.setSpacing(16)
        self.header_title = QLabel("Dashboard")
        self.header_title.setObjectName("pageTitle")
        self.header_subtitle = QLabel("Your personal financial overview")
        self.header_subtitle.setObjectName("muted")
        content_layout.addWidget(self.header_title)
        content_layout.addWidget(self.header_subtitle)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

    def _build_pages(self):
        self.pages = {}
        for name, _ in NAV_ITEMS:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            self.pages[name] = (page, layout)
            self.stack.addWidget(page)
        self._build_dashboard()
        self._build_accounts()
        self._build_transactions()
        self._build_budgets()
        self._build_bills()
        self._build_finance_calendar()
        self._build_goals()
        self._build_reports()
        self._build_settings()
        self._build_recurring()
        self._build_cash_flow_forecast()
        self._build_scenario_planner()
        self._build_reconciliation()
        self._build_debt_planner()
        self._build_investments()
        self._build_net_worth()
        self._build_categories()
        self._build_currency_valuation()
        self._build_activity_log()
        self._build_subscriptions()
        self._build_tax_center()
        self._build_auto_categorization()

    def navigate(self, page_name: str):
        if page_name not in self.pages:
            page_name = "Dashboard"
        self.stack.setCurrentWidget(self.pages[page_name][0])
        self.header_title.setText(page_name)
        subtitles = {
            "Dashboard": "Your personal financial overview",
            "Accounts": "Manage the accounts you track locally",
            "Transactions": "Record and review income, expenses, and transfers",
            "Budgets": "Set monthly spending limits by category",
            "Bills": "Keep track of recurring payments",
            "Calendar": "See bills, recurring entries, and subscription renewals by date",
            "Recurring": "Schedule income and expenses for manual posting",
            "Cash flow forecast": "Project upcoming bills and recurring cash flow",
            "Scenario planner": "Compare saved what-if assumptions without changing your ledger",
            "Reconciliation": "Match account activity to your statements",
            "Debt planner": "Track balances, interest, and payoff projections",
            "Investments": "Track securities, holdings, trades, and manual prices",
            "Savings goals": "Track progress toward your savings targets",
            "Net worth": "Review assets, liabilities, and historical snapshots",
            "Currency valuation": "Convert current balances using your manually entered exchange rates",
            "Categories": "Organize income and spending categories",
            "Reports": "Understand cash flow and spending patterns",
            "Activity log": "Review local database changes and health",
            "Settings": "Manage local data, backups, and preferences",
        }
        self.header_subtitle.setText(subtitles.get(page_name, ""))
        if page_name == "Calendar":
            self.refresh_finance_calendar()
        elif page_name == "Settings":
            self.refresh_setting_currencies()
        for name, button in self.nav_buttons.items():
            button.setChecked(name == page_name)

    def _title_row(self, layout, description: str, button_text: str | None = None, callback=None):
        row = QHBoxLayout()
        label = QLabel(description)
        label.setObjectName("muted")
        row.addWidget(label)
        row.addStretch()
        if button_text:
            button = QPushButton(button_text)
            button.setObjectName("primary")
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)

    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _build_dashboard(self):
        page, layout = self.pages["Dashboard"]
        cards = QGridLayout()
        self.card_balance = MetricCard("TOTAL ACCOUNT BALANCE", "$0.00", "Across active accounts")
        self.card_income = MetricCard("MONTHLY INCOME", "$0.00", "Current month")
        self.card_expenses = MetricCard("MONTHLY EXPENSES", "$0.00", "Current month")
        self.card_net = MetricCard("MONTHLY NET", "$0.00", "Income minus expenses")
        for index, card in enumerate([self.card_balance, self.card_income, self.card_expenses, self.card_net]):
            cards.addWidget(card, 0, index)
        layout.addLayout(cards)
        charts = QGridLayout()
        chart_frame = QFrame()
        chart_frame.setObjectName("card")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(QLabel("Monthly cash flow"))
        self.cashflow_chart = BarChart()
        chart_layout.addWidget(self.cashflow_chart)
        spend_frame = QFrame()
        spend_frame.setObjectName("card")
        spend_layout = QVBoxLayout(spend_frame)
        spend_layout.addWidget(QLabel("Spending by category"))
        self.spending_chart = HorizontalBars()
        spend_layout.addWidget(self.spending_chart)
        charts.addWidget(chart_frame, 0, 0, 1, 2)
        charts.addWidget(spend_frame, 0, 2)
        layout.addLayout(charts, 1)
        alert_heading = QLabel("Budget alerts")
        alert_heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(alert_heading)
        self.budget_alerts_label = QLabel("No budget alerts this month.")
        self.budget_alerts_label.setWordWrap(True)
        self.budget_alerts_label.setMaximumHeight(90)
        layout.addWidget(self.budget_alerts_label)
        self._title_row(layout, "Recent activity")
        self.dashboard_table = self._table(["Date", "Type", "Account", "Payee / description", "Category", "Amount"])
        layout.addWidget(self.dashboard_table, 1)

    def _build_accounts(self):
        page, layout = self.pages["Accounts"]
        self._title_row(layout, "Your accounts and current balances", "＋ Add account", self.add_account)
        self.accounts_table = self._table(["Account", "Type", "Currency", "Opening balance", "Current balance", "Status"])
        layout.addWidget(self.accounts_table, 1)
        row = QHBoxLayout()
        archive = QPushButton("Archive selected")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_account)
        row.addWidget(archive)
        row.addStretch()
        layout.addLayout(row)

    def _build_transactions(self):
        page, layout = self.pages["Transactions"]
        controls = QHBoxLayout()
        self.transaction_search = QLineEdit()
        self.transaction_search.setPlaceholderText("Search payee, description, reference…")
        self.transaction_search.textChanged.connect(self.refresh_transactions)
        self.transaction_type_filter = QComboBox()
        self.transaction_type_filter.addItems(["All types", "Income", "Expense", "Transfer", "Adjustment"])
        self.transaction_type_filter.currentIndexChanged.connect(self.refresh_transactions)
        add = QPushButton("＋ Add transaction")
        add.setObjectName("primary")
        add.clicked.connect(self.add_transaction)
        controls.addWidget(self.transaction_search, 2)
        controls.addWidget(self.transaction_type_filter)
        controls.addWidget(add)
        layout.addLayout(controls)
        self.transactions_table = self._table(["Date", "Type", "Account", "Payee", "Description", "Category", "Amount"])
        layout.addWidget(self.transactions_table, 1)
        row = QHBoxLayout()
        edit = QPushButton("Edit selected")
        edit.setObjectName("secondary")
        edit.clicked.connect(self.edit_transaction)
        delete = QPushButton("Delete selected")
        delete.setObjectName("secondary")
        delete.clicked.connect(self.delete_transaction)
        receipts = QPushButton("Receipts")
        receipts.setObjectName("secondary")
        receipts.clicked.connect(self.manage_transaction_attachments)
        export = QPushButton("Export CSV")
        export.setObjectName("secondary")
        export.clicked.connect(self.export_csv)
        import_button = QPushButton("Import CSV")
        import_button.setObjectName("secondary")
        import_button.clicked.connect(self.import_csv)
        row.addWidget(edit)
        row.addWidget(delete)
        row.addWidget(receipts)
        row.addStretch()
        row.addWidget(import_button)
        row.addWidget(export)
        layout.addLayout(row)

    def _build_budgets(self):
        page, layout = self.pages["Budgets"]
        controls = QHBoxLayout()
        self.budget_month = QLineEdit(date.today().strftime("%Y-%m"))
        self.budget_month.setMaximumWidth(120)
        self.budget_month.editingFinished.connect(self.refresh_budgets)
        add = QPushButton("＋ Set budget")
        add.setObjectName("primary")
        add.clicked.connect(self.add_budget)
        controls.addWidget(QLabel("Month"))
        controls.addWidget(self.budget_month)
        controls.addStretch()
        controls.addWidget(add)
        layout.addLayout(controls)
        self.budgets_table = self._table(["Category", "Budget", "Spent", "Remaining", "Used"])
        layout.addWidget(self.budgets_table, 1)

    def _build_bills(self):
        page, layout = self.pages["Bills"]
        self._title_row(layout, "Recurring bills and upcoming due dates", "＋ Add bill", self.add_bill)
        self.bills_table = self._table(["Bill", "Amount", "Frequency", "Next due", "Pay from", "Status"])
        layout.addWidget(self.bills_table, 1)
        row = QHBoxLayout()
        pay = QPushButton("Record payment")
        pay.setObjectName("primary")
        pay.clicked.connect(self.pay_bill)
        archive = QPushButton("Archive selected")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_bill)
        row.addWidget(pay)
        row.addWidget(archive)
        row.addStretch()
        layout.addLayout(row)

    def _build_finance_calendar(self):
        page, layout = self.pages["Calendar"]
        body = QHBoxLayout()
        self.finance_calendar_widget = QCalendarWidget()
        self.finance_calendar_widget.setMinimumWidth(340)
        self.finance_calendar_widget.setGridVisible(True)
        self.finance_calendar_widget.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.finance_calendar_widget.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self._finance_calendar_events_by_date = {}
        self._finance_calendar_highlight_dates = []
        self.finance_calendar_widget.currentPageChanged.connect(self.refresh_finance_calendar)
        self.finance_calendar_widget.clicked.connect(self.refresh_finance_calendar_day)
        body.addWidget(self.finance_calendar_widget, 1)

        details = QVBoxLayout()
        self.finance_calendar_day_label = QLabel("Select a date")
        self.finance_calendar_day_label.setObjectName("pageTitle")
        details.addWidget(self.finance_calendar_day_label)
        self.finance_calendar_empty_label = QLabel("No scheduled items")
        self.finance_calendar_empty_label.setObjectName("muted")
        details.addWidget(self.finance_calendar_empty_label)
        self.finance_calendar_table = self._table(["Source", "Item", "Amount", "Status"])
        details.addWidget(self.finance_calendar_table, 1)
        body.addLayout(details, 1)
        layout.addLayout(body, 1)

    def _build_goals(self):
        page, layout = self.pages["Savings goals"]
        self._title_row(layout, "Savings targets and progress", "＋ Create goal", self.add_goal)
        self.goals_table = self._table(["Goal", "Target", "Saved", "Remaining", "Progress", "Target date"])
        layout.addWidget(self.goals_table, 1)
        row = QHBoxLayout()
        contribute = QPushButton("Add contribution")
        contribute.setObjectName("primary")
        contribute.clicked.connect(self.contribute_goal)
        row.addWidget(contribute)
        row.addStretch()
        layout.addLayout(row)

    def _build_reports(self):
        page, layout = self.pages["Reports"]
        controls = QHBoxLayout()
        self.report_year = QSpinBox()
        self.report_year.setRange(2000, 2100)
        self.report_year.setValue(date.today().year)
        self.report_year.valueChanged.connect(self.refresh_reports)
        controls.addWidget(QLabel("Year"))
        controls.addWidget(self.report_year)
        controls.addStretch()
        layout.addLayout(controls)
        frame = QFrame()
        frame.setObjectName("card")
        frame_layout = QVBoxLayout(frame)
        frame_layout.addWidget(QLabel("Income and expenses by month"))
        self.report_chart = BarChart()
        frame_layout.addWidget(self.report_chart)
        layout.addWidget(frame)
        self.report_table = self._table(["Category", "Total expenses"])
        layout.addWidget(self.report_table, 1)

    def _build_settings(self):
        page, layout = self.pages["Settings"]
        self.settings_currency = QComboBox()
        currencies = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR"}
        currencies.update(self.currency_service.available_currencies())
        self.settings_currency.addItems(sorted(currencies))
        self.settings_currency.setCurrentText(self.config.currency)
        self.settings_theme = QComboBox()
        self.settings_theme.addItems(["light"])
        form = QFormLayout()
        form.addRow("Display / valuation base currency", self.settings_currency)
        form.addRow("Theme", self.settings_theme)
        self.settings_budget_warning = QSpinBox()
        self.settings_budget_warning.setRange(1, 99)
        self.settings_budget_warning.setSuffix("%")
        self.settings_budget_warning.setValue(self.config.budget_warning_percent)
        self.settings_budget_critical = QSpinBox()
        self.settings_budget_critical.setRange(100, 500)
        self.settings_budget_critical.setSuffix("%")
        self.settings_budget_critical.setValue(self.config.budget_critical_percent)
        form.addRow("Near-limit warning at", self.settings_budget_warning)
        form.addRow("Critical alert at", self.settings_budget_critical)
        layout.addLayout(form)
        save = QPushButton("Save preferences")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        layout.addWidget(save)
        layout.addSpacing(20)
        backup_row = QHBoxLayout()
        create = QPushButton("Create database backup")
        create.setObjectName("secondary")
        create.clicked.connect(self.create_backup)
        restore = QPushButton("Restore from backup")
        restore.setObjectName("secondary")
        restore.clicked.connect(self.restore_backup)
        backup_row.addWidget(create)
        backup_row.addWidget(restore)
        backup_row.addStretch()
        layout.addLayout(backup_row)
        layout.addSpacing(20)
        info = QLabel(
            "Your data is stored on this computer in a SQLite database. "
            "This application does not connect to a bank or send data to a server. "
            "Backups are ordinary database files; store them somewhere private."
        )
        info.setWordWrap(True)
        info.setObjectName("muted")
        layout.addWidget(info)
        layout.addStretch()

    def _build_recurring(self):
        page, layout = self.pages["Recurring"]
        self._title_row(layout, "Templates are posted only when you confirm them", "＋ Add schedule", self.add_recurring)
        self.recurring_table = self._table([
            "Schedule", "Type", "Account", "Category", "Amount", "Frequency", "Next due", "Status"
        ])
        layout.addWidget(self.recurring_table, 1)
        actions = QHBoxLayout()
        post = QPushButton("Post selected")
        post.setObjectName("primary")
        post.clicked.connect(self.post_recurring)
        skip = QPushButton("Skip occurrence")
        skip.setObjectName("secondary")
        skip.clicked.connect(self.skip_recurring)
        archive = QPushButton("Archive selected")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_recurring)
        actions.addWidget(post)
        actions.addWidget(skip)
        actions.addWidget(archive)
        actions.addStretch()
        layout.addLayout(actions)

    def _build_cash_flow_forecast(self):
        page, layout = self.pages["Cash flow forecast"]
        controls = QHBoxLayout()
        self.forecast_days = QSpinBox()
        self.forecast_days.setRange(7, 3650)
        self.forecast_days.setValue(90)
        self.forecast_days.valueChanged.connect(self.refresh_cash_flow_forecast)
        controls.addWidget(QLabel("Forecast horizon (days)"))
        controls.addWidget(self.forecast_days)
        refresh = QPushButton("Refresh forecast")
        refresh.setObjectName("primary")
        refresh.clicked.connect(self.refresh_cash_flow_forecast)
        controls.addStretch()
        controls.addWidget(refresh)
        layout.addLayout(controls)
        cards = QGridLayout()
        self.forecast_income_card = MetricCard("PROJECTED INCOME", "$0.00")
        self.forecast_expenses_card = MetricCard("PROJECTED EXPENSES", "$0.00")
        self.forecast_net_card = MetricCard("PROJECTED NET", "$0.00")
        cards.addWidget(self.forecast_income_card, 0, 0)
        cards.addWidget(self.forecast_expenses_card, 0, 1)
        cards.addWidget(self.forecast_net_card, 0, 2)
        layout.addLayout(cards)
        self.forecast_range_label = QLabel("Projection based on active recurring schedules and bills.")
        self.forecast_range_label.setObjectName("muted")
        layout.addWidget(self.forecast_range_label)
        self.forecast_table = self._table([
            "Projected date", "Original due date", "Source", "Item", "Type", "Account", "Amount", "Projected balance"
        ])
        layout.addWidget(self.forecast_table, 1)
        layout.addWidget(QLabel("Forecasts are estimates only. Nothing is posted automatically."))

    def _build_scenario_planner(self):
        page, page_layout = self.pages["Scenario planner"]
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        description = QLabel(
            "Model one account at a time. Baseline uses active bills and recurring schedules; "
            "assumptions are hypothetical and never create transactions."
        )
        description.setWordWrap(True)
        description.setObjectName("muted")
        layout.addWidget(description)

        scenario_actions = QHBoxLayout()
        add_scenario = QPushButton("Add scenario")
        add_scenario.setObjectName("primary")
        add_scenario.clicked.connect(self.add_financial_scenario)
        edit_scenario = QPushButton("Edit selected")
        edit_scenario.setObjectName("secondary")
        edit_scenario.clicked.connect(self.edit_financial_scenario)
        duplicate_scenario = QPushButton("Duplicate")
        duplicate_scenario.setObjectName("secondary")
        duplicate_scenario.clicked.connect(self.duplicate_financial_scenario)
        delete_scenario = QPushButton("Delete selected")
        delete_scenario.setObjectName("secondary")
        delete_scenario.clicked.connect(self.delete_financial_scenario)
        compare = QPushButton("Compare selected")
        compare.setObjectName("secondary")
        compare.clicked.connect(self.compare_financial_scenarios)
        export = QPushButton("Export projection")
        export.setObjectName("secondary")
        export.clicked.connect(self.export_scenario_projection)
        scenario_actions.addWidget(add_scenario)
        scenario_actions.addWidget(edit_scenario)
        scenario_actions.addWidget(duplicate_scenario)
        scenario_actions.addWidget(delete_scenario)
        scenario_actions.addStretch()
        scenario_actions.addWidget(compare)
        scenario_actions.addWidget(export)
        layout.addLayout(scenario_actions)

        self.scenarios_table = self._table([
            "Scenario", "Account", "Currency", "Starts", "Horizon",
        ])
        self.scenarios_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.scenarios_table.currentCellChanged.connect(
            self.refresh_scenario_details
        )
        self.scenarios_table.setMaximumHeight(150)
        layout.addWidget(self.scenarios_table)

        assumption_heading = QHBoxLayout()
        assumption_heading.addWidget(QLabel("Scenario assumptions"))
        assumption_heading.addStretch()
        add_assumption = QPushButton("Add assumption")
        add_assumption.setObjectName("primary")
        add_assumption.clicked.connect(self.add_scenario_adjustment)
        edit_assumption = QPushButton("Edit")
        edit_assumption.setObjectName("secondary")
        edit_assumption.clicked.connect(self.edit_scenario_adjustment)
        delete_assumption = QPushButton("Remove")
        delete_assumption.setObjectName("secondary")
        delete_assumption.clicked.connect(self.delete_scenario_adjustment)
        assumption_heading.addWidget(add_assumption)
        assumption_heading.addWidget(edit_assumption)
        assumption_heading.addWidget(delete_assumption)
        layout.addLayout(assumption_heading)
        self.scenario_adjustments_table = self._table([
            "Assumption", "Type", "Schedule", "Amount", "Months",
        ])
        self.scenario_adjustments_table.setMaximumHeight(145)
        layout.addWidget(self.scenario_adjustments_table)

        summary = QGridLayout()
        self.scenario_baseline_card = MetricCard("BASELINE ENDING BALANCE", "—")
        self.scenario_projected_card = MetricCard("SCENARIO ENDING BALANCE", "—")
        self.scenario_difference_card = MetricCard("SCENARIO DIFFERENCE", "—")
        summary.addWidget(self.scenario_baseline_card, 0, 0)
        summary.addWidget(self.scenario_projected_card, 0, 1)
        summary.addWidget(self.scenario_difference_card, 0, 2)
        layout.addLayout(summary)
        self.scenario_status = QLabel("Select a scenario to preview its monthly balances.")
        self.scenario_status.setWordWrap(True)
        self.scenario_status.setObjectName("muted")
        layout.addWidget(self.scenario_status)
        self.scenario_balance_chart = ScenarioBalanceChart()
        layout.addWidget(self.scenario_balance_chart)
        self.scenario_projection_table = self._table([
            "Month", "Baseline income", "Baseline expenses", "Plan income",
            "Plan expenses", "Baseline close", "Scenario close", "Difference",
        ])
        layout.addWidget(self.scenario_projection_table, 1)
        self.scenario_comparison_table = self._table([
            "Scenario", "Ending balance", "Difference vs baseline", "First negative month",
        ])
        self.scenario_comparison_table.setMaximumHeight(110)
        layout.addWidget(self.scenario_comparison_table)

    def _build_reconciliation(self):
        page, layout = self.pages["Reconciliation"]
        controls = QHBoxLayout()
        self.reconciliation_account = QComboBox()
        self.reconciliation_account.setMinimumWidth(180)
        self.reconciliation_account.currentIndexChanged.connect(self.load_open_reconciliation)
        controls.addWidget(QLabel("Account"))
        controls.addWidget(self.reconciliation_account)
        controls.addStretch()
        start = QPushButton("Start reconciliation")
        start.setObjectName("primary")
        start.clicked.connect(self.start_reconciliation)
        load = QPushButton("Load open session")
        load.setObjectName("secondary")
        load.clicked.connect(self.load_open_reconciliation)
        controls.addWidget(load)
        controls.addWidget(start)
        layout.addLayout(controls)
        self.reconciliation_summary = QLabel("Start a reconciliation using the ending balance on your bank statement.")
        self.reconciliation_summary.setWordWrap(True)
        self.reconciliation_summary.setStyleSheet("background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;")
        layout.addWidget(self.reconciliation_summary)
        self.reconciliation_table = self._table([
            "Cleared", "Date", "Type", "Description", "Payee", "Amount"
        ])
        self.reconciliation_table.itemChanged.connect(self._on_reconciliation_item_changed)
        layout.addWidget(self.reconciliation_table, 1)
        actions = QHBoxLayout()
        close = QPushButton("Close balanced reconciliation")
        close.setObjectName("primary")
        close.clicked.connect(self.close_reconciliation)
        discard = QPushButton("Discard open session")
        discard.setObjectName("secondary")
        discard.clicked.connect(self.discard_reconciliation)
        actions.addWidget(close)
        actions.addWidget(discard)
        actions.addStretch()
        layout.addLayout(actions)

    def _build_debt_planner(self):
        page, layout = self.pages["Debt planner"]
        self._title_row(layout, "Manual debt tracking with fixed-rate payoff projections", "＋ Add debt", self.add_debt_plan)
        self.debt_table = self._table([
            "Debt", "Creditor", "Outstanding", "APR", "Monthly payment", "Pay from", "Status"
        ])
        layout.addWidget(self.debt_table, 1)
        actions = QHBoxLayout()
        payment = QPushButton("Record payment")
        payment.setObjectName("primary")
        payment.clicked.connect(self.record_debt_payment)
        schedule = QPushButton("View payoff schedule")
        schedule.setObjectName("secondary")
        schedule.clicked.connect(self.view_debt_schedule)
        archive = QPushButton("Archive selected")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_debt_plan)
        actions.addWidget(payment)
        actions.addWidget(schedule)
        actions.addWidget(archive)
        actions.addStretch()
        layout.addLayout(actions)

    def _build_investments(self):
        page, layout = self.pages["Investments"]
        summary = QGridLayout()
        self.investment_value_card = MetricCard("MARKET VALUE", "$0.00")
        self.investment_cost_card = MetricCard("COST BASIS", "$0.00")
        self.investment_gain_card = MetricCard("UNREALIZED GAIN / LOSS", "$0.00")
        self.investment_realized_card = MetricCard("REALIZED GAIN / LOSS", "$0.00")
        summary.addWidget(self.investment_value_card, 0, 0)
        summary.addWidget(self.investment_cost_card, 0, 1)
        summary.addWidget(self.investment_gain_card, 0, 2)
        summary.addWidget(self.investment_realized_card, 0, 3)
        layout.addLayout(summary)
        self._title_row(layout, "Prices are entered manually; no live market feed is used")
        self.holdings_table = self._table([
            "Symbol", "Security", "Account", "Shares", "Cost basis", "Last price", "Market value", "Unrealized"
        ])
        layout.addWidget(self.holdings_table, 1)
        actions = QHBoxLayout()
        add_security = QPushButton("Add security")
        add_security.setObjectName("secondary")
        add_security.clicked.connect(self.add_security)
        trade = QPushButton("Record trade")
        trade.setObjectName("primary")
        trade.clicked.connect(self.record_investment_trade)
        quote = QPushButton("Update selected price")
        quote.setObjectName("secondary")
        quote.clicked.connect(self.update_security_price)
        actions.addWidget(add_security)
        actions.addWidget(trade)
        actions.addWidget(quote)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(QLabel("Recent trades"))
        self.investment_trades_table = self._table([
            "Date", "Action", "Symbol", "Account", "Quantity", "Price", "Fees", "Gross value"
        ])
        layout.addWidget(self.investment_trades_table, 1)

    def _build_net_worth(self):
        page, layout = self.pages["Net worth"]
        cards = QGridLayout()
        self.net_worth_assets_card = MetricCard("ASSETS", "$0.00")
        self.net_worth_liabilities_card = MetricCard("LIABILITIES", "$0.00")
        self.net_worth_total_card = MetricCard("NET WORTH", "$0.00")
        cards.addWidget(self.net_worth_assets_card, 0, 0)
        cards.addWidget(self.net_worth_liabilities_card, 0, 1)
        cards.addWidget(self.net_worth_total_card, 0, 2)
        layout.addLayout(cards)
        self._title_row(layout, "Snapshots preserve a point-in-time estimate of your finances", "Save snapshot", self.save_net_worth_snapshot)
        self.net_worth_table = self._table([
            "Snapshot date", "Assets", "Liabilities", "Net worth", "Notes"
        ])
        layout.addWidget(self.net_worth_table, 1)

    def _build_currency_valuation(self):
        page, layout = self.pages["Currency valuation"]
        note = QLabel(
            "Rates are entered manually. Each rate means one source-currency unit "
            "equals the stated number of base-currency units. No live market rates are used."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

        cards = QGridLayout()
        self.currency_assets_card = MetricCard("VALUED ASSETS", "—")
        self.currency_liabilities_card = MetricCard("VALUED LIABILITIES", "—")
        self.currency_net_worth_card = MetricCard("VALUED NET WORTH", "—")
        cards.addWidget(self.currency_assets_card, 0, 0)
        cards.addWidget(self.currency_liabilities_card, 0, 1)
        cards.addWidget(self.currency_net_worth_card, 0, 2)
        layout.addLayout(cards)

        self.currency_valuation_status = QLabel()
        self.currency_valuation_status.setWordWrap(True)
        layout.addWidget(self.currency_valuation_status)
        self.currency_valuation_table = self._table([
            "Source", "Item", "Currency", "Original value", "Base value", "Rate",
        ])
        layout.addWidget(self.currency_valuation_table, 1)

        layout.addWidget(QLabel("Manual exchange rates"))
        rate_controls = QHBoxLayout()
        self.exchange_source_currency = QComboBox()
        self.exchange_rate = QDoubleSpinBox()
        self.exchange_rate.setDecimals(8)
        self.exchange_rate.setRange(0.00000001, 1_000_000_000)
        self.exchange_rate.setValue(1.0)
        self.exchange_rate.setMinimumWidth(170)
        self.exchange_base_label = QLabel()
        self.exchange_source_currency.currentTextChanged.connect(
            self._update_exchange_rate_input
        )
        save_rate = QPushButton("Save rate")
        save_rate.setObjectName("primary")
        save_rate.clicked.connect(self.save_exchange_rate)
        rate_controls.addWidget(QLabel("1"))
        rate_controls.addWidget(self.exchange_source_currency)
        rate_controls.addWidget(QLabel("="))
        rate_controls.addWidget(self.exchange_rate)
        rate_controls.addWidget(self.exchange_base_label)
        rate_controls.addWidget(save_rate)
        rate_controls.addStretch()
        layout.addLayout(rate_controls)

        self.exchange_rates_table = self._table(["Currency pair", "Rate", "Updated"])
        layout.addWidget(self.exchange_rates_table, 1)
        rate_actions = QHBoxLayout()
        remove_rate = QPushButton("Remove selected rate")
        remove_rate.setObjectName("secondary")
        remove_rate.clicked.connect(self.remove_exchange_rate)
        rate_actions.addWidget(remove_rate)
        rate_actions.addStretch()
        layout.addLayout(rate_actions)

    def _build_categories(self):
        page, layout = self.pages["Categories"]
        self._title_row(layout, "Maintain the labels used by transactions and budgets", "＋ Add category", self.add_category)
        self.categories_table = self._table(["Category", "Type", "Color", "Status"])
        layout.addWidget(self.categories_table, 1)
        actions = QHBoxLayout()
        archive = QPushButton("Archive selected")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_category)
        actions.addWidget(archive)
        actions.addStretch()
        layout.addLayout(actions)


    def _build_subscriptions(self):
        page, layout = self.pages["Subscriptions"]
        cards = QGridLayout()
        self.subscription_count_card = MetricCard("ACTIVE SUBSCRIPTIONS", "0")
        self.subscription_monthly_card = MetricCard("MONTHLY EQUIVALENT", "$0.00")
        self.subscription_annual_card = MetricCard("ANNUALIZED COST", "$0.00")
        cards.addWidget(self.subscription_count_card, 0, 0)
        cards.addWidget(self.subscription_monthly_card, 0, 1)
        cards.addWidget(self.subscription_annual_card, 0, 2)
        layout.addLayout(cards)
        self._title_row(
            layout,
            "Track trials, renewal dates, cancellation deadlines, and price changes. Payments are always manual.",
            "＋ Add subscription",
            self.add_subscription,
        )
        self.subscriptions_table = self._table([
            "Subscription", "Vendor", "Price", "Frequency", "Next renewal",
            "Trial ends", "Cancel by", "Pay from", "Status",
        ])
        layout.addWidget(self.subscriptions_table, 1)
        actions = QHBoxLayout()
        renew = QPushButton("Record renewal")
        renew.setObjectName("primary")
        renew.clicked.connect(self.record_subscription_renewal)
        price = QPushButton("Update price")
        price.setObjectName("secondary")
        price.clicked.connect(self.update_subscription_price)
        history = QPushButton("Price history")
        history.setObjectName("secondary")
        history.clicked.connect(self.show_subscription_history)
        archive = QPushButton("Archive selected")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_subscription)
        actions.addWidget(renew)
        actions.addWidget(price)
        actions.addWidget(history)
        actions.addWidget(archive)
        actions.addStretch()
        layout.addLayout(actions)

    def _build_tax_center(self):
        page, layout = self.pages["Tax center"]
        controls = QHBoxLayout()
        self.tax_year = QSpinBox()
        self.tax_year.setRange(2000, 2100)
        self.tax_year.setValue(date.today().year)
        self.tax_year.valueChanged.connect(self.refresh_tax_center)
        controls.addWidget(QLabel("Tax year"))
        controls.addWidget(self.tax_year)
        controls.addStretch()
        export = QPushButton("Export tax CSV")
        export.setObjectName("secondary")
        export.clicked.connect(self.export_tax_csv)
        controls.addWidget(export)
        layout.addLayout(controls)
        cards = QGridLayout()
        self.tax_gross_income_card = MetricCard("GROSS INCOME", "$0.00")
        self.taxable_income_card = MetricCard("TAXABLE INCOME TAGGED", "$0.00")
        self.tax_deductible_card = MetricCard("DEDUCTIBLE EXPENSES TAGGED", "$0.00")
        self.tax_payments_card = MetricCard("TAX PAYMENTS", "$0.00")
        cards.addWidget(self.tax_gross_income_card, 0, 0)
        cards.addWidget(self.taxable_income_card, 0, 1)
        cards.addWidget(self.tax_deductible_card, 0, 2)
        cards.addWidget(self.tax_payments_card, 0, 3)
        layout.addLayout(cards)
        self.tax_unclassified_label = QLabel("Unclassified income: 0 · Unclassified expenses: 0")
        self.tax_unclassified_label.setObjectName("muted")
        layout.addWidget(self.tax_unclassified_label)
        self.tax_records_table = self._table([
            "Date", "Type", "Account", "Payee / description", "Treatment",
            "Tax category", "Amount", "Deductible",
        ])
        layout.addWidget(self.tax_records_table, 1)
        actions = QHBoxLayout()
        tag = QPushButton("Classify transaction")
        tag.setObjectName("primary")
        tag.clicked.connect(self.add_tax_record)
        remove = QPushButton("Remove tax classification")
        remove.setObjectName("secondary")
        remove.clicked.connect(self.remove_tax_record)
        actions.addWidget(tag)
        actions.addWidget(remove)
        actions.addStretch()
        layout.addLayout(actions)
        note = QLabel(
            "Personal recordkeeping only. Tax labels and totals are not tax advice, "
            "do not calculate tax owed, and should be reviewed with a qualified tax professional."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

    def _build_auto_categorization(self):
        page, layout = self.pages["Auto-categorization"]
        self._title_row(
            layout,
            "Create explicit keyword rules. Rules only touch uncategorized income and expenses.",
            "＋ Add rule",
            self.add_categorization_rule,
        )
        self.rules_table = self._table([
            "Rule", "Keyword", "Field", "Transaction type", "Category", "Priority", "Status",
        ])
        layout.addWidget(self.rules_table, 1)
        actions = QHBoxLayout()
        apply_rules = QPushButton("Apply rules to uncategorized transactions")
        apply_rules.setObjectName("primary")
        apply_rules.clicked.connect(self.apply_categorization_rules)
        archive = QPushButton("Archive selected rule")
        archive.setObjectName("secondary")
        archive.clicked.connect(self.archive_categorization_rule)
        actions.addWidget(apply_rules)
        actions.addWidget(archive)
        actions.addStretch()
        layout.addLayout(actions)
        self.rules_status_label = QLabel("Rules never overwrite a category already assigned to a transaction.")
        self.rules_status_label.setObjectName("muted")
        layout.addWidget(self.rules_status_label)

    def _build_activity_log(self):
        page, layout = self.pages["Activity log"]
        self._title_row(layout, "Local record of application changes")
        self.activity_table = self._table(["Timestamp", "Entity", "Action", "Record ID", "Details"])
        layout.addWidget(self.activity_table, 1)
        actions = QHBoxLayout()
        refresh = QPushButton("Refresh log")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh_activity_log)
        check = QPushButton("Run database health check")
        check.setObjectName("primary")
        check.clicked.connect(self.run_database_health_check)
        actions.addWidget(refresh)
        actions.addWidget(check)
        actions.addStretch()
        layout.addLayout(actions)

    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_accounts()
        self.refresh_transactions()
        self.refresh_budgets()
        self.refresh_bills()
        self.refresh_finance_calendar()
        self.refresh_goals()
        self.refresh_reports()
        self.refresh_recurring()
        self.refresh_cash_flow_forecast()
        self.refresh_scenarios()
        self.refresh_reconciliation()
        self.refresh_debts()
        self.refresh_investments()
        self.refresh_net_worth()
        self.refresh_currency_valuation()
        self.refresh_categories()
        self.refresh_activity_log()
        self.refresh_subscriptions()
        self.refresh_tax_center()
        self.refresh_auto_categorization()

    def refresh_dashboard(self):
        summary = self.finance.dashboard_summary()
        self.card_balance.set_value(money(summary["total_balance"], self.currency))
        self.card_income.set_value(money(summary["income"], self.currency))
        self.card_expenses.set_value(money(summary["expenses"], self.currency))
        self.card_net.set_value(money(summary["net"], self.currency))
        cashflow = self.finance.monthly_cashflow(date.today().year)
        self.cashflow_chart.set_values([
            (calendar.month_abbr[int(item["month"][-2:])], item["income"], item["expenses"])
            for item in cashflow
        ])
        spending = self.finance.spending_by_category(
            date.today().replace(day=1).isoformat(), today_iso()
        )
        self.spending_chart.set_values([
            (item["category_name"], item["total_minor"], item["color"]) for item in spending
        ])
        self._fill_transaction_table(self.dashboard_table, self.finance.recent_activity(8), dashboard=True)
        self.refresh_budget_alerts()

    def refresh_budget_alerts(self):
        alerts = self.finance.budget_alerts(
            date.today().strftime("%Y-%m"),
            self.config.budget_warning_percent,
            self.config.budget_critical_percent,
        )
        if not alerts:
            self.budget_alerts_label.setText("No budget alerts this month.")
            return

        lines = []
        for alert in alerts[:3]:
            if alert["percent"] is None:
                usage = f"{money(alert['spent_minor'], self.currency)} spent against a zero budget"
            else:
                usage = (
                    f"{money(alert['spent_minor'], self.currency)} / "
                    f"{money(alert['limit_minor'], self.currency)} "
                    f"({alert['percent']:.0f}%)"
                )
            lines.append(f"{alert['status']}: {alert['category_name']} - {usage}")
        if len(alerts) > 3:
            lines.append(f"{len(alerts) - 3} more budget alerts")
        self.budget_alerts_label.setText("\n".join(lines))

    def refresh_accounts(self):
        rows = self.finance.accounts.list(include_inactive=True)
        balances = {item["id"]: item["balance_minor"] for item in self.finance.account_balances()}
        self.accounts_table.setRowCount(0)
        for row in rows:
            index = self.accounts_table.rowCount()
            self.accounts_table.insertRow(index)
            values = [
                row["name"], humanize(row["kind"]), row["currency"],
                money(int(row["opening_balance_minor"]), row["currency"]),
                money(balances.get(row["id"], int(row["opening_balance_minor"])), row["currency"]),
                "Active" if row["is_active"] else "Archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.accounts_table.setItem(index, column, cell)

    def refresh_transactions(self):
        if not hasattr(self, "transactions_table"):
            return
        selected = self.transaction_type_filter.currentText().lower()
        kind = None if selected == "all types" else selected.replace(" ", "_")
        rows = self.finance.list_transactions(
            kind=kind, search=self.transaction_search.text(), limit=1000
        )
        self._fill_transaction_table(self.transactions_table, rows)

    def _fill_transaction_table(self, table, rows, dashboard=False):
        table.setRowCount(0)
        for row in rows:
            index = table.rowCount()
            table.insertRow(index)
            account = row["account_name"]
            if row["kind"] == "transfer":
                account = f"{account} → {row['transfer_account_name'] or '?'}"
            description = row["payee"] or row["description"]
            values = [
                row["occurred_on"], humanize(row["kind"]), account, description,
                row["category_name"] or "", money(int(row["amount_minor"]), self.currency),
            ]
            if not dashboard:
                values = [
                    row["occurred_on"], humanize(row["kind"]), account,
                    row["payee"], row["description"], row["category_name"] or "",
                    money(int(row["amount_minor"]), self.currency),
                ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                table.setItem(index, column, cell)

    def refresh_budgets(self):
        if not hasattr(self, "budgets_table"):
            return
        try:
            rows = self.finance.budget_status(self.budget_month.text().strip())
        except Exception:
            return
        self.budgets_table.setRowCount(0)
        for row in rows:
            index = self.budgets_table.rowCount()
            self.budgets_table.insertRow(index)
            values = [
                row["category_name"], money(row["limit_minor"], self.currency),
                money(row["spent_minor"], self.currency),
                money(row["remaining_minor"], self.currency), f"{row['percent']:.1f}%",
            ]
            for column, value in enumerate(values):
                self.budgets_table.setItem(index, column, QTableWidgetItem(str(value)))

    def refresh_bills(self):
        rows = self.finance.bills.list(include_inactive=True)
        self.bills_table.setRowCount(0)
        for row in rows:
            index = self.bills_table.rowCount()
            self.bills_table.insertRow(index)
            values = [
                row["name"], money(int(row["amount_minor"]), self.currency),
                humanize(row["frequency"]), row["next_due_date"],
                row["account_name"] or "Not assigned", "Active" if row["active"] else "Archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.bills_table.setItem(index, column, cell)

    def refresh_finance_calendar(self, year: int | None = None, month: int | None = None):
        if not hasattr(self, "finance_calendar_widget"):
            return
        year = year or self.finance_calendar_widget.yearShown()
        month = month or self.finance_calendar_widget.monthShown()
        month_key = f"{year:04d}-{month:02d}"

        for day in self._finance_calendar_highlight_dates:
            self.finance_calendar_widget.setDateTextFormat(
                QDate.fromString(day, "yyyy-MM-dd"), QTextCharFormat()
            )

        events = self.calendar_service.events(month_key)
        events_by_date = {}
        for event in events:
            events_by_date.setdefault(event["date"], []).append(event)
        self._finance_calendar_events_by_date = events_by_date
        self._finance_calendar_highlight_dates = sorted(events_by_date)

        for day, day_events in events_by_date.items():
            text_format = QTextCharFormat()
            overdue = any(event["overdue"] for event in day_events)
            text_format.setBackground(QColor("#fee2e2" if overdue else "#dbeafe"))
            text_format.setForeground(QColor("#991b1b" if overdue else "#1d4ed8"))
            text_format.setToolTip("\n".join(event["name"] for event in day_events))
            self.finance_calendar_widget.setDateTextFormat(
                QDate.fromString(day, "yyyy-MM-dd"), text_format
            )

        selected = self.finance_calendar_widget.selectedDate()
        if selected.year() != year or selected.month() != month:
            selected = QDate(year, month, 1)
            self.finance_calendar_widget.setSelectedDate(selected)
        self.refresh_finance_calendar_day(selected)

    def refresh_finance_calendar_day(self, selected: QDate | None = None):
        if not hasattr(self, "finance_calendar_table"):
            return
        selected = selected or self.finance_calendar_widget.selectedDate()
        day = selected.toString("yyyy-MM-dd")
        events = self._finance_calendar_events_by_date.get(day, [])
        self.finance_calendar_day_label.setText(
            f"{selected.toString('dddd, MMMM d')} · {len(events)} scheduled"
        )
        self.finance_calendar_empty_label.setVisible(not events)
        self.finance_calendar_table.setRowCount(0)
        for event in events:
            index = self.finance_calendar_table.rowCount()
            self.finance_calendar_table.insertRow(index)
            status = f"Overdue (due {event['due_date']})" if event["overdue"] else "Scheduled"
            values = [
                humanize(event["source_type"]),
                event["name"],
                money(int(event["amount_minor"]), event["currency"] or self.currency),
                status,
            ]
            for column, value in enumerate(values):
                self.finance_calendar_table.setItem(index, column, QTableWidgetItem(str(value)))

    def refresh_goals(self):
        rows = self.finance.goals.list(include_inactive=True)
        self.goals_table.setRowCount(0)
        for row in rows:
            index = self.goals_table.rowCount()
            self.goals_table.insertRow(index)
            target, current = int(row["target_minor"]), int(row["current_minor"])
            remaining = max(0, target - current)
            percent = current / target * 100 if target else 0
            values = [
                row["name"], money(target, self.currency), money(current, self.currency),
                money(remaining, self.currency), f"{percent:.1f}%", row["target_date"] or "—",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.goals_table.setItem(index, column, cell)

    def refresh_reports(self):
        if not hasattr(self, "report_year"):
            return
        year = self.report_year.value()
        rows = self.finance.monthly_cashflow(year)
        self.report_chart.set_values([
            (calendar.month_abbr[int(item["month"][-2:])], item["income"], item["expenses"])
            for item in rows
        ])
        spending = self.finance.spending_by_category(f"{year}-01-01", f"{year}-12-31")
        self.report_table.setRowCount(0)
        for row in spending:
            index = self.report_table.rowCount()
            self.report_table.insertRow(index)
            self.report_table.setItem(index, 0, QTableWidgetItem(row["category_name"]))
            self.report_table.setItem(index, 1, QTableWidgetItem(money(row["total_minor"], self.currency)))

    def _selected_id(self, table, column=0):
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, column)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show_error(self, exc):
        QMessageBox.warning(self, "Please check your entry", str(exc))

    def manage_transaction_attachments(self):
        transaction_id = self._selected_id(self.transactions_table)
        if not transaction_id:
            QMessageBox.information(
                self, "Select a transaction", "Choose a transaction before managing receipts."
            )
            return
        dialog = ReceiptAttachmentDialog(
            self,
            self.attachment_service,
            int(transaction_id),
            self.attachment_open_directory.name,
        )
        dialog.exec()
        self.refresh_activity_log()

    def add_account(self):
        dialog = AccountDialog(self, currency=self.currency)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.finance.create_account(**dialog.values())
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def archive_account(self):
        account_id = self._selected_id(self.accounts_table)
        if not account_id:
            QMessageBox.information(self, "Select an account", "Choose an account first.")
            return
        if QMessageBox.question(self, "Archive account", "Archive the selected account?") == QMessageBox.StandardButton.Yes:
            try:
                self.finance.archive_account(account_id)
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def add_transaction(self):
        accounts = self.finance.accounts.list()
        if not accounts:
            QMessageBox.information(self, "Create an account", "Add an account before recording transactions.")
            self.navigate("Accounts")
            return
        categories = self.finance.categories.list()
        dialog = TransactionDialog(self, accounts, categories, self.currency)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                values = dialog.values()
                kind = values.pop("kind")
                target_id = values.pop("transfer_account_id")
                if kind == "income":
                    values.pop("transfer_account_id", None)
                    self.finance.create_income(**values)
                elif kind == "expense":
                    values.pop("transfer_account_id", None)
                    self.finance.create_expense(**values)
                else:
                    self.finance.create_transfer(
                        values["account_id"], target_id, values["amount_minor"],
                        values["occurred_on"], values["description"], values["notes"],
                    )
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def edit_transaction(self):
        transaction_id = self._selected_id(self.transactions_table)
        if not transaction_id:
            QMessageBox.information(self, "Select a transaction", "Choose a transaction first.")
            return
        transaction = self.finance.transactions.get(int(transaction_id))
        if not transaction:
            QMessageBox.information(self, "Transaction not found", "Refresh the list and try again.")
            return
        if transaction["kind"] == "adjustment":
            QMessageBox.information(
                self, "Adjustment editing unavailable",
                "Balance adjustments cannot be edited in this version. Delete and recreate the adjustment if it has not been reconciled.",
            )
            return
        dialog = TransactionEditDialog(
            self, transaction, self.finance.accounts.list(), self.finance.categories.list()
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.finance.update_transaction(int(transaction_id), **dialog.values())
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def delete_transaction(self):
        transaction_id = self._selected_id(self.transactions_table)
        if not transaction_id:
            QMessageBox.information(self, "Select a transaction", "Choose a transaction first.")
            return
        if QMessageBox.question(
            self, "Delete transaction",
            "Delete this transaction and its attached receipt files?",
        ) == QMessageBox.StandardButton.Yes:
            try:
                self.finance.delete_transaction(int(transaction_id))
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def add_budget(self):
        categories = self.finance.categories.list(kind="expense")
        if not categories:
            QMessageBox.information(self, "No categories", "Create an expense category first.")
            return
        dialog = BudgetDialog(self, categories, self.budget_month.text())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                category_id, month, amount = dialog.values()
                self.finance.set_budget(category_id, month, amount)
                self.refresh_budgets()
            except Exception as exc:
                self._show_error(exc)

    def add_bill(self):
        dialog = BillDialog(
            self, self.finance.accounts.list(), self.finance.categories.list(kind="expense")
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.finance.create_bill(**dialog.values())
                self.refresh_bills()
            except Exception as exc:
                self._show_error(exc)

    def pay_bill(self):
        bill_id = self._selected_id(self.bills_table)
        if not bill_id:
            QMessageBox.information(self, "Select a bill", "Choose a bill first.")
            return
        if QMessageBox.question(self, "Record payment", "Record this bill as paid?") == QMessageBox.StandardButton.Yes:
            try:
                self.finance.pay_bill(int(bill_id))
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def archive_bill(self):
        bill_id = self._selected_id(self.bills_table)
        if not bill_id:
            QMessageBox.information(self, "Select a bill", "Choose a bill first.")
            return
        self.finance.bills.update(int(bill_id), active=0)
        self.refresh_bills()

    def add_goal(self):
        dialog = GoalDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, target, target_date, notes = dialog.values()
                self.finance.create_goal(name, target, target_date, notes)
                self.refresh_goals()
            except Exception as exc:
                self._show_error(exc)

    def contribute_goal(self):
        goal_id = self._selected_id(self.goals_table)
        if not goal_id:
            QMessageBox.information(self, "Select a goal", "Choose a savings goal first.")
            return
        row = self.finance.db.fetch_one("SELECT name FROM savings_goals WHERE id = ?", (goal_id,))
        dialog = ContributionDialog(self, row["name"] if row else "goal")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.finance.contribute_to_goal(int(goal_id), dialog.values())
                self.refresh_goals()
            except Exception as exc:
                self._show_error(exc)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export transactions", "transactions.csv", "CSV files (*.csv)")
        if not path:
            return
        try:
            count = self.csv_service.export_transactions(path)
            QMessageBox.information(self, "Export complete", f"Exported {count} transactions.")
        except Exception as exc:
            self._show_error(exc)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import transactions", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            preview = self.csv_service.preview_import(path)
            answer = QMessageBox.question(
                self, "Confirm import",
                f"The file contains {len(preview)} rows. Import valid rows now?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            result = self.csv_service.import_transactions(path, skip_invalid=True)
            QMessageBox.information(
                self, "Import finished",
                f"Imported: {result['imported']}\nSkipped: {result['skipped']}"
                + (("\n\n" + "\n".join(result["errors"][:10])) if result["errors"] else ""),
            )
            self.refresh_all()
        except Exception as exc:
            self._show_error(exc)

    def save_settings(self):
        self.currency = self.settings_currency.currentText()
        self.config.update(
            currency=self.currency,
            theme=self.settings_theme.currentText(),
            budget_warning_percent=self.settings_budget_warning.value(),
            budget_critical_percent=self.settings_budget_critical.value(),
        )
        QMessageBox.information(self, "Preferences saved", "Your preferences have been saved.")
        self.refresh_all()

    def create_backup(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Create backup", "personalbank-backup.sqlite3", "SQLite database (*.sqlite3)"
        )
        if not path:
            return
        try:
            self.backup_service.create_backup(path)
            QMessageBox.information(self, "Backup created", f"Backup saved to:\n{path}")
        except Exception as exc:
            self._show_error(exc)

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore backup", "", "SQLite database (*.sqlite3 *.db)"
        )
        if not path:
            return
        answer = QMessageBox.warning(
            self, "Replace local database?",
            "Restoring replaces the current database with the selected backup. "
            "Create a backup of the current data first if you may need it.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.backup_service.restore_backup(path)
            QMessageBox.information(self, "Restore complete", "Database restored. Restart the application.")
            self.close()
        except Exception as exc:
            self._show_error(exc)


    # ------------------------------------------------------------------
    # Advanced personal-finance workflows
    # ------------------------------------------------------------------
    def refresh_recurring(self):
        if not hasattr(self, "recurring_table"):
            return
        rows = self.recurring_service.list(include_inactive=True)
        self.recurring_table.setRowCount(0)
        for row in rows:
            index = self.recurring_table.rowCount()
            self.recurring_table.insertRow(index)
            values = [
                row["name"], humanize(row["kind"]), row["account_name"],
                row["category_name"] or "—", money(int(row["amount_minor"]), self.currency),
                humanize(row["frequency"]), row["next_due_date"],
                "Active" if row["active"] else "Archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.recurring_table.setItem(index, column, cell)

    def add_recurring(self):
        accounts = self.finance.accounts.list()
        if not accounts:
            QMessageBox.information(self, "Create an account", "Add an account before creating a recurring schedule.")
            self.navigate("Accounts")
            return
        dialog = RecurringDialog(self, accounts, self.finance.categories.list())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.recurring_service.create(**dialog.values())
                self.refresh_recurring()
            except Exception as exc:
                self._show_error(exc)

    def post_recurring(self):
        recurring_id = self._selected_id(self.recurring_table)
        if not recurring_id:
            QMessageBox.information(self, "Select a schedule", "Choose a recurring schedule first.")
            return
        answer = QMessageBox.question(
            self, "Post recurring transaction",
            "Create the transaction using this schedule? This does not send money or contact a bank.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.recurring_service.post(int(recurring_id))
            self.refresh_all()
        except Exception as exc:
            self._show_error(exc)

    def skip_recurring(self):
        recurring_id = self._selected_id(self.recurring_table)
        if not recurring_id:
            QMessageBox.information(self, "Select a schedule", "Choose a recurring schedule first.")
            return
        if QMessageBox.question(self, "Skip occurrence", "Advance the next due date without creating a transaction?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.recurring_service.skip(int(recurring_id))
            self.refresh_recurring()
        except Exception as exc:
            self._show_error(exc)

    def archive_recurring(self):
        recurring_id = self._selected_id(self.recurring_table)
        if not recurring_id:
            QMessageBox.information(self, "Select a schedule", "Choose a recurring schedule first.")
            return
        if QMessageBox.question(self, "Archive schedule", "Archive this recurring schedule?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.recurring_service.archive(int(recurring_id))
            self.refresh_recurring()
        except Exception as exc:
            self._show_error(exc)

    def refresh_cash_flow_forecast(self):
        if not hasattr(self, "forecast_table"):
            return
        try:
            forecast = self.forecast_service.project(self.forecast_days.value())
            self.forecast_income_card.set_value(money(forecast["projected_income_minor"], self.currency))
            self.forecast_expenses_card.set_value(money(forecast["projected_expenses_minor"], self.currency))
            self.forecast_net_card.set_value(money(forecast["projected_net_minor"], self.currency))
            self.forecast_range_label.setText(
                f"From {forecast['as_of']} through {forecast['end_date']} · {len(forecast['events'])} projected events"
            )
            self.forecast_table.setRowCount(0)
            for event in forecast["events"]:
                index = self.forecast_table.rowCount()
                self.forecast_table.insertRow(index)
                values = [
                    event["date"] + (" · overdue" if event["overdue"] else ""),
                    event["due_date"], humanize(event["source_type"]), event["name"],
                    humanize(event["kind"]), event["account_name"],
                    money(int(event["amount_minor"]), self.currency),
                    money(int(event["projected_balance_minor"]), self.currency)
                    if event["projected_balance_minor"] is not None else "—",
                ]
                for column, value in enumerate(values):
                    self.forecast_table.setItem(index, column, QTableWidgetItem(str(value)))
        except Exception as exc:
            self.forecast_range_label.setText(f"Forecast unavailable: {exc}")

    def refresh_scenarios(self, preferred_id: int | None = None):
        if not hasattr(self, "scenarios_table"):
            return
        selected_id = preferred_id or self._selected_id(self.scenarios_table)
        rows = self.scenario_service.list()
        self.scenarios_table.blockSignals(True)
        self.scenarios_table.setRowCount(0)
        selected_row = None
        for scenario in rows:
            index = self.scenarios_table.rowCount()
            self.scenarios_table.insertRow(index)
            values = [
                scenario["name"], scenario["account_name"], scenario["currency"],
                scenario["start_date"], f"{scenario['horizon_months']} months",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(scenario["id"]))
                self.scenarios_table.setItem(index, column, item)
            if selected_id is not None and int(scenario["id"]) == int(selected_id):
                selected_row = index
        if rows and selected_row is None:
            selected_row = 0
        if selected_row is not None:
            self.scenarios_table.selectRow(selected_row)
        self.scenarios_table.blockSignals(False)
        self.scenario_comparison_table.setRowCount(0)
        self.refresh_scenario_details()

    def refresh_scenario_details(self, current_row: int = -1, *_args):
        scenario_id = self._selected_id(self.scenarios_table)
        self.scenario_adjustments_table.setRowCount(0)
        self.scenario_projection_table.setRowCount(0)
        self.scenario_comparison_table.setRowCount(0)
        if not scenario_id:
            for card in (
                self.scenario_baseline_card,
                self.scenario_projected_card,
                self.scenario_difference_card,
            ):
                card.set_value("—")
            self.scenario_status.setText("Create or select a scenario to preview a plan.")
            self.scenario_balance_chart.set_values([])
            return
        try:
            scenario = self.scenario_service.get(int(scenario_id))
            currency = scenario["currency"]
            for adjustment in self.scenario_service.adjustments(int(scenario_id)):
                index = self.scenario_adjustments_table.rowCount()
                self.scenario_adjustments_table.insertRow(index)
                start = int(adjustment["start_month"])
                end = adjustment["end_month"]
                months = (
                    f"{start} only" if adjustment["cadence"] == "one_time" else
                    f"{start}-{end}" if end is not None else f"{start}+"
                )
                values = [
                    adjustment["name"], humanize(adjustment["kind"]),
                    humanize(adjustment["cadence"]),
                    money(int(adjustment["amount_minor"]), currency), months,
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, int(adjustment["id"]))
                    self.scenario_adjustments_table.setItem(index, column, item)

            preview = self.scenario_service.preview(int(scenario_id))
            self.scenario_balance_chart.set_values([
                (
                    month["month"][2:],
                    month["baseline_balance_minor"],
                    month["scenario_balance_minor"],
                )
                for month in preview["months"]
            ])
            self.scenario_baseline_card.set_value(
                money(preview["ending_baseline_minor"], currency),
                f"Opening {money(preview['opening_balance_minor'], currency)}",
            )
            self.scenario_projected_card.set_value(
                money(preview["ending_scenario_minor"], currency), scenario["account_name"]
            )
            self.scenario_difference_card.set_value(
                money(preview["ending_difference_minor"], currency), "Scenario minus baseline"
            )
            negative = preview["first_negative_month"]
            self.scenario_status.setText(
                f"First projected negative balance: {negative}. Nothing is posted to the ledger."
                if negative else
                "No negative monthly closing balance is projected. Nothing is posted to the ledger."
            )
            for month in preview["months"]:
                index = self.scenario_projection_table.rowCount()
                self.scenario_projection_table.insertRow(index)
                values = [
                    month["month"],
                    money(month["baseline_income_minor"], currency),
                    money(month["baseline_expenses_minor"], currency),
                    money(month["planned_income_minor"], currency),
                    money(month["planned_expenses_minor"], currency),
                    money(month["baseline_balance_minor"], currency),
                    money(month["scenario_balance_minor"], currency),
                    money(month["difference_minor"], currency),
                ]
                for column, value in enumerate(values):
                    self.scenario_projection_table.setItem(
                        index, column, QTableWidgetItem(str(value))
                    )
        except Exception as exc:
            self.scenario_status.setText(f"Scenario preview unavailable: {exc}")

    def export_scenario_projection(self):
        scenario_id = self._selected_id(self.scenarios_table)
        if not scenario_id:
            QMessageBox.information(self, "Select a scenario", "Choose a scenario to export.")
            return
        scenario = self.scenario_service.get(int(scenario_id))
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in scenario["name"]
        ).strip("_") or "scenario"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export scenario projection", f"{safe_name}-projection.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        try:
            row_count = self.scenario_service.export_csv(int(scenario_id), path)
            QMessageBox.information(
                self, "Projection exported", f"Exported {row_count} projected months to:\n{path}"
            )
        except Exception as exc:
            self._show_error(exc)

    def add_financial_scenario(self):
        accounts = self.finance.accounts.list()
        if not accounts:
            QMessageBox.information(
                self, "Create an account", "Add an account before creating a scenario."
            )
            self.navigate("Accounts")
            return
        dialog = FinancialScenarioDialog(self, accounts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                scenario_id = self.scenario_service.create(**dialog.values())
                self.refresh_scenarios(scenario_id)
            except Exception as exc:
                self._show_error(exc)

    def edit_financial_scenario(self):
        scenario_id = self._selected_id(self.scenarios_table)
        if not scenario_id:
            QMessageBox.information(self, "Select a scenario", "Choose a scenario to edit.")
            return
        scenario = self.scenario_service.get(int(scenario_id))
        dialog = FinancialScenarioDialog(self, self.finance.accounts.list(), scenario)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.scenario_service.update(int(scenario_id), **dialog.values())
                self.refresh_scenarios(int(scenario_id))
            except Exception as exc:
                self._show_error(exc)

    def duplicate_financial_scenario(self):
        scenario_id = self._selected_id(self.scenarios_table)
        if not scenario_id:
            QMessageBox.information(
                self, "Select a scenario", "Choose a scenario to duplicate."
            )
            return
        scenario = self.scenario_service.get(int(scenario_id))
        name, accepted = QInputDialog.getText(
            self, "Duplicate scenario", "New scenario name:",
            text=f"{scenario['name']} copy",
        )
        if not accepted:
            return
        try:
            duplicate_id = self.scenario_service.duplicate(int(scenario_id), name)
            self.refresh_scenarios(duplicate_id)
        except Exception as exc:
            self._show_error(exc)

    def delete_financial_scenario(self):
        scenario_id = self._selected_id(self.scenarios_table)
        if not scenario_id:
            QMessageBox.information(self, "Select a scenario", "Choose a scenario to delete.")
            return
        if QMessageBox.question(
            self, "Delete scenario",
            "Delete this scenario and all of its assumptions? Actual financial records are unchanged.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.scenario_service.delete(int(scenario_id))
            self.refresh_scenarios()
        except Exception as exc:
            self._show_error(exc)

    def add_scenario_adjustment(self):
        scenario_id = self._selected_id(self.scenarios_table)
        if not scenario_id:
            QMessageBox.information(self, "Select a scenario", "Choose a scenario first.")
            return
        scenario = self.scenario_service.get(int(scenario_id))
        dialog = ScenarioAdjustmentDialog(self, int(scenario["horizon_months"]))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.scenario_service.add_adjustment(
                    int(scenario_id), **dialog.values()
                )
                self.refresh_scenario_details()
            except Exception as exc:
                self._show_error(exc)

    def edit_scenario_adjustment(self):
        scenario_id = self._selected_id(self.scenarios_table)
        adjustment_id = self._selected_id(self.scenario_adjustments_table)
        if not scenario_id or not adjustment_id:
            QMessageBox.information(
                self, "Select an assumption", "Choose a scenario and an assumption to edit."
            )
            return
        scenario = self.scenario_service.get(int(scenario_id))
        adjustment = self.db_row_scenario_adjustment(int(adjustment_id))
        if not adjustment:
            self.refresh_scenario_details()
            return
        dialog = ScenarioAdjustmentDialog(
            self, int(scenario["horizon_months"]), adjustment
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.scenario_service.update_adjustment(
                    int(adjustment_id), **dialog.values()
                )
                self.refresh_scenario_details()
            except Exception as exc:
                self._show_error(exc)

    def db_row_scenario_adjustment(self, adjustment_id: int):
        return self.finance.db.fetch_one(
            "SELECT * FROM scenario_adjustments WHERE id = ?", (int(adjustment_id),)
        )

    def delete_scenario_adjustment(self):
        adjustment_id = self._selected_id(self.scenario_adjustments_table)
        if not adjustment_id:
            QMessageBox.information(
                self, "Select an assumption", "Choose an assumption to remove."
            )
            return
        try:
            self.scenario_service.delete_adjustment(int(adjustment_id))
            self.refresh_scenario_details()
        except Exception as exc:
            self._show_error(exc)

    def compare_financial_scenarios(self):
        scenario_ids = []
        for model_index in self.scenarios_table.selectionModel().selectedRows():
            item = self.scenarios_table.item(model_index.row(), 0)
            if item:
                scenario_ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        try:
            comparison = self.scenario_service.compare(scenario_ids)
            self.scenario_comparison_table.setRowCount(0)
            for item in comparison["ending_balances"]:
                index = self.scenario_comparison_table.rowCount()
                self.scenario_comparison_table.insertRow(index)
                values = [
                    item["name"],
                    money(item["ending_balance_minor"], comparison["currency"]),
                    money(item["difference_minor"], comparison["currency"]),
                    item["first_negative_month"] or "None",
                ]
                for column, value in enumerate(values):
                    self.scenario_comparison_table.setItem(
                        index, column, QTableWidgetItem(str(value))
                    )
        except Exception as exc:
            self._show_error(exc)

    def refresh_reconciliation(self):
        if not hasattr(self, "reconciliation_account"):
            return
        selected_id = self.reconciliation_account.currentData()
        accounts = self.finance.accounts.list()
        self.reconciliation_account.blockSignals(True)
        self.reconciliation_account.clear()
        for account in accounts:
            self.reconciliation_account.addItem(account["name"], int(account["id"]))
        if selected_id is not None:
            index = self.reconciliation_account.findData(int(selected_id))
            if index >= 0:
                self.reconciliation_account.setCurrentIndex(index)
        self.reconciliation_account.blockSignals(False)
        self.load_open_reconciliation()

    def load_open_reconciliation(self):
        if not hasattr(self, "reconciliation_account"):
            return
        account_id = self.reconciliation_account.currentData()
        if account_id is None:
            self.current_reconciliation_session_id = None
            self._populate_reconciliation(None)
            return
        session = self.reconciliation_service.open_session(int(account_id))
        self.current_reconciliation_session_id = int(session["id"]) if session else None
        self._populate_reconciliation(self.current_reconciliation_session_id)

    def _populate_reconciliation(self, session_id):
        self._reconciliation_loading = True
        self.reconciliation_table.setRowCount(0)
        if session_id is None:
            self.reconciliation_summary.setText(
                "No open session. Start a reconciliation using the ending balance on your bank statement."
            )
            self._reconciliation_loading = False
            return
        try:
            items = self.reconciliation_service.items(int(session_id))
            summary = self.reconciliation_service.summary(int(session_id))
            for row in items:
                index = self.reconciliation_table.rowCount()
                self.reconciliation_table.insertRow(index)
                checkbox = QTableWidgetItem("")
                checkbox.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                    Qt.ItemFlag.ItemIsUserCheckable
                )
                checkbox.setCheckState(
                    Qt.CheckState.Checked if row["cleared"] else Qt.CheckState.Unchecked
                )
                checkbox.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.reconciliation_table.setItem(index, 0, checkbox)
                description = row["description"] or row["payee"] or row["category_name"] or "Transaction"
                account_label = row["account_name"]
                if row["kind"] == "transfer":
                    account_label += f" → {row['transfer_account_name'] or '?'}"
                values = [
                    row["occurred_on"], humanize(row["kind"]), description,
                    row["payee"] or account_label,
                    money(int(row["signed_amount_minor"]), self.currency),
                ]
                for column, value in enumerate(values, start=1):
                    self.reconciliation_table.setItem(index, column, QTableWidgetItem(str(value)))
            difference = int(summary["difference_minor"])
            state = "BALANCED" if difference == 0 else "DIFFERENCE"
            self.reconciliation_summary.setText(
                f"Opening balance: {money(int(summary['opening_balance_minor']), self.currency)}    "
                f"Cleared activity: {money(int(summary['cleared_total_minor']), self.currency)}    "
                f"Calculated balance: {money(int(summary['calculated_balance_minor']), self.currency)}    "
                f"Statement balance: {money(int(summary['statement_balance_minor']), self.currency)}    "
                f"{state}: {money(difference, self.currency)}"
            )
        except Exception as exc:
            self.reconciliation_summary.setText(f"Could not load reconciliation: {exc}")
        finally:
            self._reconciliation_loading = False

    def _on_reconciliation_item_changed(self, item):
        if self._reconciliation_loading or item.column() != 0:
            return
        session_id = self.current_reconciliation_session_id
        transaction_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id or not transaction_id:
            return
        try:
            self.reconciliation_service.set_cleared(
                int(session_id), int(transaction_id), item.checkState() == Qt.CheckState.Checked
            )
            summary = self.reconciliation_service.summary(int(session_id))
            difference = int(summary["difference_minor"])
            state = "BALANCED" if difference == 0 else "DIFFERENCE"
            self.reconciliation_summary.setText(
                f"Opening balance: {money(int(summary['opening_balance_minor']), self.currency)}    "
                f"Cleared activity: {money(int(summary['cleared_total_minor']), self.currency)}    "
                f"Calculated balance: {money(int(summary['calculated_balance_minor']), self.currency)}    "
                f"Statement balance: {money(int(summary['statement_balance_minor']), self.currency)}    "
                f"{state}: {money(difference, self.currency)}"
            )
        except Exception as exc:
            self._show_error(exc)
            self._populate_reconciliation(session_id)

    def start_reconciliation(self):
        accounts = self.finance.accounts.list()
        if not accounts:
            QMessageBox.information(self, "No accounts", "Create an account before reconciling it.")
            return
        dialog = ReconciliationStartDialog(self, accounts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                account_id, statement_date, statement_balance, notes = dialog.values()
                session_id = self.reconciliation_service.start_session(
                    account_id, statement_date, statement_balance, notes
                )
                self.current_reconciliation_session_id = session_id
                index = self.reconciliation_account.findData(account_id)
                if index >= 0:
                    self.reconciliation_account.setCurrentIndex(index)
                self._populate_reconciliation(session_id)
            except Exception as exc:
                self._show_error(exc)

    def close_reconciliation(self):
        session_id = self.current_reconciliation_session_id
        if not session_id:
            QMessageBox.information(self, "No open session", "Start or load a reconciliation first.")
            return
        try:
            summary = self.reconciliation_service.summary(int(session_id))
            if int(summary["difference_minor"]) != 0:
                QMessageBox.warning(
                    self, "Not balanced",
                    f"The reconciliation still differs by {money(int(summary['difference_minor']), self.currency)}.",
                )
                return
            self.reconciliation_service.close_session(int(session_id))
            self.current_reconciliation_session_id = None
            QMessageBox.information(self, "Reconciliation closed", "The balanced session has been closed.")
            self.refresh_all()
        except Exception as exc:
            self._show_error(exc)

    def discard_reconciliation(self):
        session_id = self.current_reconciliation_session_id
        if not session_id:
            QMessageBox.information(self, "No open session", "There is no open reconciliation to discard.")
            return
        if QMessageBox.question(self, "Discard reconciliation", "Discard this open reconciliation session?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.reconciliation_service.discard_open_session(int(session_id))
            self.current_reconciliation_session_id = None
            self.refresh_reconciliation()
        except Exception as exc:
            self._show_error(exc)

    def refresh_debts(self):
        if not hasattr(self, "debt_table"):
            return
        rows = self.debt_service.list_plans(include_inactive=True)
        self.debt_table.setRowCount(0)
        for row in rows:
            index = self.debt_table.rowCount()
            self.debt_table.insertRow(index)
            values = [
                row["name"], row["creditor"] or "—",
                money(int(row["principal_minor"]), self.currency),
                f"{int(row['apr_basis_points']) / 100:.2f}%",
                money(int(row["minimum_payment_minor"]), self.currency),
                row["payment_account_name"], "Active" if row["active"] else "Paid / archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.debt_table.setItem(index, column, cell)

    def add_debt_plan(self):
        accounts = self.finance.accounts.list()
        if not any(account["kind"] in {"checking", "savings", "cash"} for account in accounts):
            QMessageBox.information(
                self, "Add a payment account",
                "Create a checking, savings, or cash account before adding a debt plan.",
            )
            return
        dialog = DebtPlanDialog(self, accounts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.debt_service.create_plan(**dialog.values())
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def record_debt_payment(self):
        debt_id = self._selected_id(self.debt_table)
        if not debt_id:
            QMessageBox.information(self, "Select a debt", "Choose a debt plan first.")
            return
        plan = self.debt_service.get_plan(int(debt_id))
        if not plan:
            return
        dialog = DebtPaymentDialog(self, plan["name"], int(plan["minimum_payment_minor"]))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                result = dialog.values()
                payment = self.debt_service.record_payment(int(debt_id), **result)
                QMessageBox.information(
                    self, "Payment recorded",
                    f"Payment: {money(payment['payment_minor'], self.currency)}\n"
                    f"Interest: {money(payment['interest_minor'], self.currency)}\n"
                    f"Principal reduction: {money(payment['principal_minor'], self.currency)}\n"
                    f"Remaining principal: {money(payment['remaining_minor'], self.currency)}",
                )
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def view_debt_schedule(self):
        debt_id = self._selected_id(self.debt_table)
        if not debt_id:
            QMessageBox.information(self, "Select a debt", "Choose a debt plan first.")
            return
        try:
            plan = self.debt_service.get_plan(int(debt_id))
            rows = self.debt_service.schedule(int(debt_id))
            if not rows:
                QMessageBox.information(self, "Debt paid", "This debt has no remaining principal.")
                return
            dialog = DebtScheduleDialog(self, plan["name"], rows, self.currency)
            dialog.exec()
        except Exception as exc:
            self._show_error(exc)

    def archive_debt_plan(self):
        debt_id = self._selected_id(self.debt_table)
        if not debt_id:
            QMessageBox.information(self, "Select a debt", "Choose a debt plan first.")
            return
        if QMessageBox.question(self, "Archive debt plan", "Archive this debt plan?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.debt_service.archive(int(debt_id))
            self.refresh_net_worth()
            self.refresh_debts()
        except Exception as exc:
            self._show_error(exc)

    def refresh_investments(self):
        if not hasattr(self, "holdings_table"):
            return
        summary = self.investment_service.summary()
        self.investment_value_card.set_value(money(summary["market_value_minor"], self.currency))
        self.investment_cost_card.set_value(money(summary["cost_basis_minor"], self.currency))
        self.investment_gain_card.set_value(money(summary["unrealized_minor"], self.currency))
        self.investment_realized_card.set_value(money(summary["realized_minor"], self.currency))
        self.holdings_table.setRowCount(0)
        for row in self.investment_service.holdings():
            index = self.holdings_table.rowCount()
            self.holdings_table.insertRow(index)
            values = [
                row["symbol"], row["security_name"], row["account_name"],
                f"{int(row['quantity_micros']) / 1_000_000:.6f}".rstrip("0").rstrip("."),
                money(int(row["cost_basis_minor"]), row["currency"]),
                money(int(row["last_price_minor"]), row["currency"]),
                money(int(row["market_value_minor"]), row["currency"]),
                money(int(row["unrealized_minor"]), row["currency"]),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["security_id"]))
                self.holdings_table.setItem(index, column, cell)
        self.investment_trades_table.setRowCount(0)
        for row in self.investment_service.trades(100):
            index = self.investment_trades_table.rowCount()
            self.investment_trades_table.insertRow(index)
            values = [
                row["trade_date"], humanize(row["side"]), row["symbol"], row["account_name"],
                f"{int(row['quantity_micros']) / 1_000_000:.6f}".rstrip("0").rstrip("."),
                money(int(row["price_minor"]), self.currency),
                money(int(row["commission_minor"]), self.currency),
                money(int(row["gross_minor"]), self.currency),
            ]
            for column, value in enumerate(values):
                self.investment_trades_table.setItem(index, column, QTableWidgetItem(str(value)))

    def add_security(self):
        dialog = SecurityDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.investment_service.create_security(*dialog.values())
                self.refresh_investments()
            except Exception as exc:
                self._show_error(exc)

    def record_investment_trade(self):
        accounts = self.finance.accounts.list()
        securities = self.investment_service.securities()
        if not any(account["kind"] == "investment" for account in accounts):
            QMessageBox.information(self, "Create an investment account", "Add an account with type Investment first.")
            self.navigate("Accounts")
            return
        if not securities:
            QMessageBox.information(self, "Add a security", "Create a security before recording a trade.")
            self.add_security()
            securities = self.investment_service.securities()
            if not securities:
                return
        dialog = TradeDialog(self, accounts, securities)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.investment_service.record_trade(**dialog.values())
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def update_security_price(self):
        row_index = self.holdings_table.currentRow()
        if row_index < 0:
            QMessageBox.information(self, "Select a holding", "Choose a holding first.")
            return
        item = self.holdings_table.item(row_index, 0)
        security_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not security_id:
            return
        security = self.db_security(int(security_id))
        if not security:
            return
        dialog = SecurityPriceDialog(self, security["symbol"], int(security["last_price_minor"]))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.investment_service.update_price(int(security_id), dialog.values())
                self.refresh_all()
            except Exception as exc:
                self._show_error(exc)

    def db_security(self, security_id: int):
        return self.finance.db.fetch_one(
            "SELECT * FROM investment_securities WHERE id = ?", (int(security_id),)
        )

    def refresh_net_worth(self):
        if not hasattr(self, "net_worth_table"):
            return
        position = self.net_worth_service.current_position()
        currencies = {row["currency"] for row in position["accounts"]}
        mixed = len(currencies) > 1
        display_currency = next(iter(currencies), self.currency) if not mixed else self.currency
        hint = "Unconverted; see Currency Valuation" if mixed else f"Current value in {display_currency}"
        assets_value = "Multiple currencies" if mixed else money(position["assets_minor"], display_currency)
        liabilities_value = "Multiple currencies" if mixed else money(position["liabilities_minor"], display_currency)
        net_worth_value = "Multiple currencies" if mixed else money(position["net_worth_minor"], display_currency)
        self.net_worth_assets_card.set_value(
            assets_value, hint
        )
        self.net_worth_liabilities_card.set_value(
            liabilities_value, hint
        )
        self.net_worth_total_card.set_value(
            net_worth_value, hint
        )
        self.net_worth_table.setRowCount(0)
        for row in self.net_worth_service.snapshots():
            index = self.net_worth_table.rowCount()
            self.net_worth_table.insertRow(index)
            try:
                snapshot_accounts = json.loads(row["details_json"]).get("accounts", [])
                snapshot_currencies = {account["currency"] for account in snapshot_accounts}
            except (TypeError, ValueError, KeyError):
                snapshot_currencies = set()
            snapshot_mixed = len(snapshot_currencies) > 1
            snapshot_currency = (
                next(iter(snapshot_currencies), self.currency)
                if not snapshot_mixed else None
            )
            snapshot_values = (
                ["Multiple currencies"] * 3 if snapshot_mixed else [
                    money(int(row["assets_minor"]), snapshot_currency),
                    money(int(row["liabilities_minor"]), snapshot_currency),
                    money(int(row["net_worth_minor"]), snapshot_currency),
                ]
            )
            values = [
                row["snapshot_date"], *snapshot_values, row["notes"],
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.net_worth_table.setItem(index, column, cell)

    def save_net_worth_snapshot(self):
        dialog = NetWorthSnapshotDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                snapshot_date, notes = dialog.values()
                self.net_worth_service.save_snapshot(snapshot_date, notes)
                self.refresh_net_worth()
            except Exception as exc:
                self._show_error(exc)

    def refresh_currency_valuation(self):
        if not hasattr(self, "currency_valuation_table"):
            return
        base_currency = self.config.currency.upper()
        self.exchange_base_label.setText(base_currency)

        selected_currency = self.exchange_source_currency.currentText()
        self.exchange_source_currency.blockSignals(True)
        self.exchange_source_currency.clear()
        for currency in self.currency_service.available_currencies():
            if currency != base_currency:
                self.exchange_source_currency.addItem(currency)
        selected_index = self.exchange_source_currency.findText(selected_currency)
        if selected_index >= 0:
            self.exchange_source_currency.setCurrentIndex(selected_index)
        self.exchange_source_currency.blockSignals(False)
        self._update_exchange_rate_input()

        rates = self.currency_service.rates()
        self.exchange_rates_table.setRowCount(0)
        for rate in rates:
            index = self.exchange_rates_table.rowCount()
            self.exchange_rates_table.insertRow(index)
            pair = f"{rate['from_currency']} -> {rate['to_currency']}"
            values = [pair, str(rate["rate"]), str(rate["updated_at"]).replace("T", " ")[:19]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        (rate["from_currency"], rate["to_currency"]),
                    )
                self.exchange_rates_table.setItem(index, column, item)

        report = self.currency_service.valuation(base_currency)
        complete = report["complete"]
        hint = (
            "Complete valuation" if complete else
            f"Missing exchange rates: {', '.join(report['missing_currencies'])}"
        )
        self.currency_assets_card.set_value(money(report["assets_minor"], base_currency), hint)
        self.currency_liabilities_card.set_value(
            money(report["liabilities_minor"], base_currency), hint
        )
        self.currency_net_worth_card.set_value(
            money(report["net_worth_minor"], base_currency), hint
        )
        self.currency_valuation_status.setText(
            f"{hint}. Missing-rate amounts are excluded from totals. Debt amounts may be counted "
            "again if also entered as negative account balances."
        )

        self.currency_valuation_table.setRowCount(0)
        for row in report["rows"]:
            index = self.currency_valuation_table.rowCount()
            self.currency_valuation_table.insertRow(index)
            rate = self.currency_service.rate(row["currency"], base_currency)
            rate_text = (
                f"1 {row['currency']} = {rate:f} {base_currency}"
                if rate is not None else "Rate missing"
            )
            values = [
                humanize(row["source_type"]),
                row["name"],
                row["currency"],
                money(row["amount_minor"], row["currency"]),
                money(row["base_minor"], base_currency)
                if row["base_minor"] is not None else "Rate missing",
                rate_text,
            ]
            for column, value in enumerate(values):
                self.currency_valuation_table.setItem(
                    index, column, QTableWidgetItem(str(value))
                )

    def refresh_setting_currencies(self):
        if not hasattr(self, "settings_currency"):
            return
        current = self.settings_currency.currentText() or self.config.currency
        currencies = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR"}
        currencies.update(self.currency_service.available_currencies())
        self.settings_currency.blockSignals(True)
        self.settings_currency.clear()
        self.settings_currency.addItems(sorted(currencies))
        self.settings_currency.setCurrentText(current)
        self.settings_currency.blockSignals(False)

    def _update_exchange_rate_input(self):
        if not hasattr(self, "exchange_rate"):
            return
        source = self.exchange_source_currency.currentText()
        if not source:
            self.exchange_rate.setValue(1.0)
            return
        rate = self.currency_service.rate(source, self.config.currency)
        if rate is not None:
            self.exchange_rate.setValue(float(rate))

    def save_exchange_rate(self):
        source = self.exchange_source_currency.currentText()
        if not source:
            QMessageBox.information(
                self, "No foreign currencies", "Create an account in another currency first."
            )
            return
        try:
            self.currency_service.set_rate(
                source, self.config.currency, self.exchange_rate.value()
            )
            self.refresh_currency_valuation()
        except Exception as exc:
            self._show_error(exc)

    def remove_exchange_rate(self):
        row = self.exchange_rates_table.currentRow()
        item = self.exchange_rates_table.item(row, 0) if row >= 0 else None
        pair = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not pair:
            QMessageBox.information(
                self, "Select an exchange rate", "Choose a saved rate first."
            )
            return
        if QMessageBox.question(
            self, "Remove exchange rate", f"Remove {pair[0]} to {pair[1]} rate?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.currency_service.delete_rate(*pair)
            self.refresh_currency_valuation()
        except Exception as exc:
            self._show_error(exc)

    def refresh_categories(self):
        if not hasattr(self, "categories_table"):
            return
        rows = self.finance.categories.list(include_inactive=True)
        self.categories_table.setRowCount(0)
        for row in rows:
            index = self.categories_table.rowCount()
            self.categories_table.insertRow(index)
            values = [
                row["name"], humanize(row["kind"]), row["color"],
                "Active" if row["is_active"] else "Archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.categories_table.setItem(index, column, cell)

    def add_category(self):
        dialog = CategoryDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, kind, color = dialog.values()
                self.finance.create_category(name, kind, color)
                self.refresh_categories()
            except Exception as exc:
                self._show_error(exc)

    def archive_category(self):
        category_id = self._selected_id(self.categories_table)
        if not category_id:
            QMessageBox.information(self, "Select a category", "Choose a category first.")
            return
        if QMessageBox.question(self, "Archive category", "Archive this category? Existing transactions are retained.") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.finance.categories.archive(int(category_id))
            self.refresh_categories()
        except Exception as exc:
            self._show_error(exc)

    def refresh_activity_log(self):
        if not hasattr(self, "activity_table"):
            return
        rows = self.maintenance_service.audit_entries(500)
        self.activity_table.setRowCount(0)
        for row in rows:
            index = self.activity_table.rowCount()
            self.activity_table.insertRow(index)
            values = [
                row["created_at"], row["entity"], row["action"],
                str(row["entity_id"] or "—"), row["details"],
            ]
            for column, value in enumerate(values):
                self.activity_table.setItem(index, column, QTableWidgetItem(str(value)))

    def run_database_health_check(self):
        try:
            report = self.maintenance_service.integrity_report()
            integrity_ok = report["integrity"] == ["ok"]
            foreign_count = len(report["foreign_key_issues"])
            status = "Database integrity: OK" if integrity_ok else f"Database integrity: {report['integrity']}"
            status += f"\nForeign-key issues: {foreign_count}"
            status += f"\nTables checked: {len(report['table_counts'])}"
            status += f"\nDatabase: {report['database_path']}"
            if foreign_count:
                status += f"\nDetails: {report['foreign_key_issues'][:5]}"
            QMessageBox.information(self, "Database health check", status)
        except Exception as exc:
            self._show_error(exc)



    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------
    def refresh_subscriptions(self):
        if not hasattr(self, "subscriptions_table"):
            return
        summary = self.subscription_service.summary()
        self.subscription_count_card.set_value(str(summary["active_count"]), "Active recurring services")
        if summary["currency_mixed"]:
            currency_hint = "Mixed currencies · no FX conversion"
            self.subscription_monthly_card.set_value("Mixed currencies", currency_hint)
            self.subscription_annual_card.set_value("Mixed currencies", currency_hint)
        else:
            self.subscription_monthly_card.set_value(money(summary["monthly_equivalent_minor"], self.currency))
            self.subscription_annual_card.set_value(money(summary["annual_equivalent_minor"], self.currency))
        rows = self.subscription_service.list(include_inactive=True)
        self.subscriptions_table.setRowCount(0)
        for row in rows:
            index = self.subscriptions_table.rowCount()
            self.subscriptions_table.insertRow(index)
            values = [
                row["name"], row["vendor"] or "—",
                money(int(row["amount_minor"]), row["currency"]),
                humanize(row["frequency"]), row["next_renewal_date"],
                row["trial_end_date"] or "—", row["cancel_by_date"] or "—",
                row["account_name"] or "Not assigned",
                "Active" if row["active"] else "Archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.subscriptions_table.setItem(index, column, cell)

    def add_subscription(self):
        dialog = SubscriptionDialog(
            self, self.finance.accounts.list(), self.finance.categories.list(kind="expense"),
            self.currency,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.subscription_service.create(**dialog.values())
                self.refresh_subscriptions()
            except Exception as exc:
                self._show_error(exc)

    def record_subscription_renewal(self):
        subscription_id = self._selected_id(self.subscriptions_table)
        if not subscription_id:
            QMessageBox.information(self, "Select a subscription", "Choose a subscription first.")
            return
        row = self.subscription_service.get(int(subscription_id))
        if not row:
            return
        answer = QMessageBox.question(
            self, "Record renewal",
            f"Create a {money(int(row['amount_minor']), row['currency'])} expense "
            f"for {row['name']} and advance its renewal date?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.subscription_service.record_renewal(int(subscription_id))
            self.refresh_all()
        except Exception as exc:
            self._show_error(exc)

    def update_subscription_price(self):
        subscription_id = self._selected_id(self.subscriptions_table)
        if not subscription_id:
            QMessageBox.information(self, "Select a subscription", "Choose a subscription first.")
            return
        row = self.subscription_service.get(int(subscription_id))
        if not row:
            return
        dialog = SubscriptionPriceDialog(self, row["name"], int(row["amount_minor"]))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                amount, effective_date, notes = dialog.values()
                self.subscription_service.update_price(
                    int(subscription_id), amount, effective_date, notes
                )
                self.refresh_subscriptions()
            except Exception as exc:
                self._show_error(exc)

    def show_subscription_history(self):
        subscription_id = self._selected_id(self.subscriptions_table)
        if not subscription_id:
            QMessageBox.information(self, "Select a subscription", "Choose a subscription first.")
            return
        row = self.subscription_service.get(int(subscription_id))
        if row:
            dialog = SubscriptionHistoryDialog(
                self, row["name"], self.subscription_service.price_history(int(subscription_id)),
                row["currency"],
            )
            dialog.exec()

    def archive_subscription(self):
        subscription_id = self._selected_id(self.subscriptions_table)
        if not subscription_id:
            QMessageBox.information(self, "Select a subscription", "Choose a subscription first.")
            return
        if QMessageBox.question(
            self, "Archive subscription", "Archive the selected subscription?"
        ) == QMessageBox.StandardButton.Yes:
            try:
                self.subscription_service.archive(int(subscription_id))
                self.refresh_subscriptions()
            except Exception as exc:
                self._show_error(exc)

    # ------------------------------------------------------------------
    # Tax recordkeeping
    # ------------------------------------------------------------------
    def refresh_tax_center(self):
        if not hasattr(self, "tax_records_table"):
            return
        year = self.tax_year.value()
        summary = self.tax_service.summary(year)
        self.tax_gross_income_card.set_value(money(summary["gross_income_minor"], self.currency))
        self.taxable_income_card.set_value(money(summary["taxable_income_minor"], self.currency))
        self.tax_deductible_card.set_value(money(summary["deductible_expenses_minor"], self.currency))
        self.tax_payments_card.set_value(money(summary["tax_payments_minor"], self.currency))
        self.tax_unclassified_label.setText(
            f"Unclassified income: {summary['unclassified_income_count']} · "
            f"Unclassified expenses: {summary['unclassified_expense_count']} · "
            f"Classified transactions: {summary['classified_count']}"
        )
        self.tax_records_table.setRowCount(0)
        for row in self.tax_service.records(year):
            index = self.tax_records_table.rowCount()
            self.tax_records_table.insertRow(index)
            deductible = (
                int(row["amount_minor"]) * int(row["deductible_basis_points"]) + 5000
            ) // 10000
            values = [
                row["occurred_on"], humanize(row["kind"]), row["account_name"],
                row["payee"] or row["description"] or "—", humanize(row["treatment"]),
                row["tax_category"], money(int(row["amount_minor"]), self.currency),
                money(deductible, self.currency),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["transaction_id"]))
                self.tax_records_table.setItem(index, column, cell)

    def add_tax_record(self):
        year = self.tax_year.value()
        transactions = self.finance.list_transactions(
            start_date=f"{year}-01-01", end_date=f"{year}-12-31", limit=10000
        )
        eligible = [row for row in transactions if row["kind"] in {"income", "expense"}]
        if not eligible:
            QMessageBox.information(
                self, "No transactions", "There are no income or expense transactions for this tax year."
            )
            return
        dialog = TaxRecordDialog(self, eligible)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.tax_service.tag_transaction(**dialog.values())
                self.refresh_tax_center()
            except Exception as exc:
                self._show_error(exc)

    def remove_tax_record(self):
        transaction_id = self._selected_id(self.tax_records_table)
        if not transaction_id:
            QMessageBox.information(self, "Select a classification", "Choose a tax record first.")
            return
        if QMessageBox.question(
            self, "Remove classification", "Remove the tax classification from this transaction?"
        ) == QMessageBox.StandardButton.Yes:
            self.tax_service.delete_tag(int(transaction_id))
            self.refresh_tax_center()

    def export_tax_csv(self):
        year = self.tax_year.value()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export tax records", f"tax-records-{year}.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            count = self.tax_service.export_csv(path, year)
            QMessageBox.information(self, "Tax export complete", f"Exported {count} classified transactions.")
        except Exception as exc:
            self._show_error(exc)

    # ------------------------------------------------------------------
    # Explicit transaction categorization rules
    # ------------------------------------------------------------------
    def refresh_auto_categorization(self):
        if not hasattr(self, "rules_table"):
            return
        rows = self.rule_service.list(include_inactive=True)
        self.rules_table.setRowCount(0)
        for row in rows:
            index = self.rules_table.rowCount()
            self.rules_table.insertRow(index)
            values = [
                row["name"], row["keyword"], humanize(row["match_field"]),
                humanize(row["transaction_kind"]), row["category_name"],
                str(row["priority"]), "Active" if row["active"] else "Archived",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.rules_table.setItem(index, column, cell)

    def add_categorization_rule(self):
        dialog = CategorizationRuleDialog(self, self.finance.categories.list())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.rule_service.create(**dialog.values())
                self.refresh_auto_categorization()
            except Exception as exc:
                self._show_error(exc)

    def apply_categorization_rules(self):
        if QMessageBox.question(
            self, "Apply categorization rules",
            "Apply active rules to transactions that do not currently have a category? "
            "Existing categories will not be changed.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.rule_service.apply_to_uncategorized()
            self.rules_status_label.setText(
                f"Examined {result['examined']} · Categorized {result['categorized']} · "
                f"Unmatched {result['unmatched']}"
            )
            QMessageBox.information(
                self, "Categorization complete",
                f"Categorized {result['categorized']} transactions. "
                f"{result['unmatched']} had no matching rule.",
            )
            self.refresh_all()
        except Exception as exc:
            self._show_error(exc)

    def archive_categorization_rule(self):
        rule_id = self._selected_id(self.rules_table)
        if not rule_id:
            QMessageBox.information(self, "Select a rule", "Choose a rule first.")
            return
        try:
            self.rule_service.archive(int(rule_id))
            self.refresh_auto_categorization()
        except Exception as exc:
            self._show_error(exc)


NAV_ITEMS_NAMES = {name for name, _ in NAV_ITEMS}
