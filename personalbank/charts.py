from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import QWidget


class BarChart(QWidget):
    """Small dependency-free chart widget for monthly income and expenses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[tuple[str, int, int]] = []
        self.setMinimumHeight(230)

    def set_values(self, values: list[tuple[str, int, int]]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(42, 16, -16, -34)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        if not self.values:
            painter.setPen(QColor("#64748b"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No activity for this year")
            painter.end()
            return
        maximum = max((max(income, expense) for _, income, expense in self.values), default=1) or 1
        slot = rect.width() / max(1, len(self.values))
        bar_width = min(14.0, slot * 0.28)
        for index, (label, income, expense) in enumerate(self.values):
            center = rect.left() + slot * (index + 0.5)
            for offset, value, color in [
                (-bar_width / 2, income, QColor("#16a34a")),
                (bar_width / 2, expense, QColor("#ef4444")),
            ]:
                height = rect.height() * value / maximum
                bar = QRectF(center + offset, rect.bottom() - height, bar_width - 1, height)
                painter.fillRect(bar, QBrush(color))
            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(
                QRectF(center - slot / 2, rect.bottom() + 5, slot, 18),
                Qt.AlignmentFlag.AlignHCenter,
                label,
            )
        painter.setPen(QColor("#16a34a"))
        painter.drawText(42, 13, "Income")
        painter.setPen(QColor("#ef4444"))
        painter.drawText(100, 13, "Expenses")
        painter.end()


class HorizontalBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[tuple[str, int, str]] = []
        self.setMinimumHeight(160)

    def set_values(self, values: list[tuple[str, int, str]]) -> None:
        self.values = values[:8]
        self.setMinimumHeight(max(160, len(self.values) * 34 + 20))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        if not self.values:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No expenses recorded")
            painter.end()
            return
        maximum = max(value for _, value, _ in self.values) or 1
        for index, (label, value, color) in enumerate(self.values):
            y = 12 + index * 34
            painter.setPen(QColor("#334155"))
            painter.drawText(0, y + 16, label[:22])
            bar_rect = QRectF(160, y, max(2, (self.width() - 220) * value / maximum), 18)
            painter.fillRect(bar_rect, QColor(color))
            painter.setPen(QColor("#475569"))
            painter.drawText(self.width() - 54, y + 15, f"{value / 100:,.0f}")
        painter.end()
