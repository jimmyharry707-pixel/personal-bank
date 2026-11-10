from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .statement_import import StatementMatchingService


class StatementReviewDialog(QDialog):
    """Review statement CSV rows and choose which ones to import."""

    HEADERS = ["Import", "Line", "Date", "Type", "Account", "Payee / description", "Amount", "Review"]
    def __init__(self, parent, matching_service: StatementMatchingService, path: str):
        super().__init__(parent)
        self.matching_service = matching_service
        self.review_rows = matching_service.review(path)
        self.import_result: dict[str, Any] | None = None
        self.setWindowTitle("Review statement import")
        self.resize(1120, 620)

        root = QVBoxLayout(self)
        summary = QLabel(
            "Possible matches and repeated file rows are unchecked by default. "
            "Review each row before importing; no row is imported until you confirm."
        )
        summary.setWordWrap(True)
        root.addWidget(summary)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 60)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.select_unmatched = QPushButton("Select unmatched valid rows")
        self.select_unmatched.clicked.connect(self._select_unmatched_rows)
        self.clear_selection = QPushButton("Clear selection")
        self.clear_selection.clicked.connect(self._clear_selection)
        actions.addWidget(self.select_unmatched)
        actions.addWidget(self.clear_selection)
        actions.addStretch()
        root.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.import_button = QPushButton("Import selected")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self._import_selected)
        buttons.addButton(self.import_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._populate()

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for review in self.review_rows:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            raw = review["raw"]
            parsed = review["parsed"]
            item = QTableWidgetItem()
            item.setFlags(
                (item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if review["valid"] else
                (item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            )
            item.setCheckState(
                Qt.CheckState.Checked if review["import_selected"] else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, int(review["line_number"]))
            self.table.setItem(row_index, 0, item)

            display = [
                str(review["line_number"]),
                parsed["occurred_on"] if parsed else str(raw.get("date") or ""),
                parsed["kind"] if parsed else str(raw.get("type") or ""),
                parsed["account_name"] if parsed else str(raw.get("account") or ""),
                (parsed["payee"] or parsed["description"]) if parsed else str(
                    raw.get("payee") or raw.get("description") or ""
                ),
                str(raw.get("amount") or ""),
                review["match_label"],
            ]
            for column, value in enumerate(display, start=1):
                cell = QTableWidgetItem(str(value))
                if column == 7:
                    details = self._match_details(review)
                    if review["error"]:
                        details = review["error"]
                    cell.setToolTip(details)
                    if not review["valid"]:
                        cell.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row_index, column, cell)

    @staticmethod
    def _match_details(review: dict[str, Any]) -> str:
        matches = review["matches"]
        if matches:
            details = [
                f"Transaction #{item['transaction_id']} · {item['date']} · "
                f"{item['payee'] or item['description'] or 'No description'} · "
                f"{item['confidence']:.0%} confidence"
                for item in matches
            ]
            return "Possible existing transactions:\n" + "\n".join(details)
        if review["duplicate_in_file_line"] is not None:
            return f"This row repeats the statement data on line {review['duplicate_in_file_line']}."
        return "No matching transaction found."

    def _selected_reviews(self) -> list[dict[str, Any]]:
        selected_lines = {
            int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        }
        return [
            review for review in self.review_rows
            if int(review["line_number"]) in selected_lines
        ]

    def _select_unmatched_rows(self) -> None:
        for row, review in enumerate(self.review_rows):
            if review["valid"] and not review["matches"] and review["duplicate_in_file_line"] is None:
                self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _clear_selection(self) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def _import_selected(self) -> None:
        selected = self._selected_reviews()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select at least one valid row to import.")
            return
        if QMessageBox.question(
            self, "Confirm statement import",
            f"Import {len(selected)} selected rows into your local ledger?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.import_result = self.matching_service.import_selected(selected)
        self.accept()
