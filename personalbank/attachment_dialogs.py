from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QHeaderView, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .attachments import ReceiptAttachmentService


class ReceiptAttachmentDialog(QDialog):
    def __init__(
        self, parent, service: ReceiptAttachmentService, transaction_id: int,
        open_directory: str | Path,
    ):
        super().__init__(parent)
        self.service = service
        self.transaction_id = int(transaction_id)
        self.open_directory = Path(open_directory)
        self.setWindowTitle("Transaction receipts")
        self.setMinimumSize(680, 390)

        root = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Size", "Added"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        add = QPushButton("Attach file")
        add.setObjectName("primary")
        add.clicked.connect(self.attach_file)
        open_file = QPushButton("Open selected")
        open_file.setObjectName("secondary")
        open_file.clicked.connect(self.open_selected)
        remove = QPushButton("Remove selected")
        remove.setObjectName("secondary")
        remove.clicked.connect(self.remove_selected)
        actions.addWidget(add)
        actions.addWidget(open_file)
        actions.addWidget(remove)
        actions.addStretch()
        root.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.table.setRowCount(0)
        for attachment in self.service.list_for_transaction(self.transaction_id):
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                attachment["filename"],
                attachment["media_type"],
                f"{(int(attachment['size_bytes']) + 1023) // 1024} KB",
                str(attachment["created_at"]).replace("T", " ")[:19],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(attachment["id"]))
                self.table.setItem(row, column, item)

    def _selected_attachment_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach receipt",
            "",
            "Receipt files (*.pdf *.png *.jpg *.jpeg *.webp *.gif)",
        )
        if not path:
            return
        try:
            self.service.add(self.transaction_id, path)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not attach file", str(exc))

    def open_selected(self) -> None:
        attachment_id = self._selected_attachment_id()
        if not attachment_id:
            QMessageBox.information(self, "Select a receipt", "Choose a receipt to open.")
            return
        attachment = self.service.get(attachment_id)
        if not attachment:
            self.refresh()
            return
        try:
            self.open_directory.mkdir(parents=True, exist_ok=True)
            filename = Path(str(attachment["filename"])).name
            path = self.open_directory / f"{attachment_id}-{filename}"
            path.write_bytes(attachment["content"])
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise OSError("No application could open this receipt file.")
        except OSError as exc:
            QMessageBox.warning(self, "Could not open receipt", str(exc))

    def remove_selected(self) -> None:
        attachment_id = self._selected_attachment_id()
        if not attachment_id:
            QMessageBox.information(self, "Select a receipt", "Choose a receipt to remove.")
            return
        if QMessageBox.question(
            self, "Remove receipt", "Remove this receipt from the transaction?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete(attachment_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not remove receipt", str(exc))