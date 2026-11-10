from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
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


class ScenarioBalanceChart(QWidget):
    """Compare baseline and scenario account balances across projected months."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[tuple[str, int, int]] = []
        self.setMinimumHeight(190)

    def set_values(self, values: list[tuple[str, int, int]]) -> None:
        self.values = list(values)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        plot = self.rect().adjusted(52, 28, -18, -38)
        if not self.values:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No scenario selected")
            painter.end()
            return

        numbers = [value for _, baseline, scenario in self.values for value in (baseline, scenario)]
        minimum, maximum = min(numbers), max(numbers)
        if minimum == maximum:
            padding = max(abs(maximum) // 10, 100)
        else:
            padding = max((maximum - minimum) // 10, 1)
        minimum -= padding
        maximum += padding
        span = maximum - minimum

        def point(index: int, value: int):
            x = plot.left() + plot.width() * (
                0.5 if len(self.values) == 1 else index / (len(self.values) - 1)
            )
            y = plot.bottom() - plot.height() * (value - minimum) / span
            return x, y

        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        for step in range(5):
            y = plot.top() + plot.height() * step / 4
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
        zero_y = plot.bottom() - plot.height() * (0 - minimum) / span
        if plot.top() <= zero_y <= plot.bottom():
            painter.setPen(QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(plot.left()), int(zero_y), int(plot.right()), int(zero_y))

        series = [
            (1, QColor("#2563eb")),
            (2, QColor("#d97706")),
        ]
        for value_index, color in series:
            path = QPainterPath()
            points = [point(index, values[value_index]) for index, values in enumerate(self.values)]
            path.moveTo(*points[0])
            for x, y in points[1:]:
                path.lineTo(x, y)
            painter.setPen(QPen(color, 2))
            painter.drawPath(path)
            painter.setBrush(QBrush(color))
            for x, y in points:
                painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)

        painter.setPen(QColor("#2563eb"))
        painter.drawText(54, 17, "Baseline")
        painter.setPen(QColor("#d97706"))
        painter.drawText(128, 17, "Scenario")
        painter.setPen(QColor("#64748b"))
        label_step = max(1, (len(self.values) + 7) // 8)
        for index, (label, _, _) in enumerate(self.values):
            if index % label_step == 0 or index == len(self.values) - 1:
                x, _ = point(index, minimum)
                painter.drawText(
                    int(x - 35), int(plot.bottom() + 8), 70, 18,
                    Qt.AlignmentFlag.AlignHCenter, label,
                )
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
