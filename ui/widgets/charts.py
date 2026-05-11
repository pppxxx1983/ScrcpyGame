from PySide6.QtWidgets import (
    QWidget,
)
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt

class BarChartWidget(QWidget):
    """简单柱状图控件。"""

    def __init__(self, data: list[dict], title: str = "", parent=None):
        super().__init__(parent)
        self._data = data
        self._title = title
        self.setMinimumHeight(220)
        self.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c;")

    def set_data(self, data: list[dict]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 10
        chart_w = w - margin * 2
        chart_h = h - margin * 2 - 20
        painter.fillRect(self.rect(), QColor("#252526"))

        if not self._data:
            painter.setPen(QColor("#888888"))
            painter.drawText(margin, h // 2, "暂无数据")
            painter.end()
            return

        max_val = max(d.get("value", 0) for d in self._data) or 1
        bar_w = max(12, min(60, chart_w // len(self._data) - 6))
        colors = ["#0e639c", "#6a9955", "#ce9178", "#d670d6", "#4ec9b0", "#ffcc00", "#9cdcfe", "#f44747"]

        for i, d in enumerate(self._data):
            val = d.get("value", 0)
            label = d.get("label", "")[:6]
            color = QColor(colors[i % len(colors)])
            bar_h = (val / max_val) * chart_h
            x = margin + i * (bar_w + 6)
            y = margin + 20 + chart_h - bar_h
            painter.fillRect(int(x), int(y), bar_w, int(bar_h), color)
            # 数值
            painter.setPen(QColor("#cccccc"))
            painter.setFont(QFont("Consolas", 8))
            painter.drawText(int(x), int(y) - 4, bar_w, 12, Qt.AlignmentFlag.AlignCenter, str(val))
            # 标签
            painter.drawText(int(x), margin + 20 + chart_h + 2, bar_w, 14, Qt.AlignmentFlag.AlignCenter, label)

        painter.setPen(QColor("#cccccc"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        painter.drawText(margin, margin + 12, self._title)
        painter.end()


class PieChartWidget(QWidget):
    """简单饼图控件。"""

    def __init__(self, data: list[dict], title: str = "", parent=None):
        super().__init__(parent)
        self._data = data
        self._title = title
        self.setMinimumHeight(200)
        self.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c;")

    def set_data(self, data: list[dict]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#252526"))
        w, h = self.width(), self.height()
        margin = 10
        colors = ["#0e639c", "#6a9955", "#ce9178", "#d670d6", "#4ec9b0", "#ffcc00", "#f44747"]

        total = sum(d.get("value", 0) for d in self._data)
        if total <= 0:
            painter.setPen(QColor("#888888"))
            painter.drawText(margin, h // 2, "暂无数据")
            painter.end()
            return

        cx = w // 3
        cy = h // 2 + 10
        radius = min(cx - margin, cy - margin - 20)
        start_angle = 0.0
        for i, d in enumerate(self._data):
            val = d.get("value", 0)
            angle = (val / total) * 360.0
            color = QColor(colors[i % len(colors)])
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#252526"), 2))
            painter.drawPie(cx - radius, cy - radius, radius * 2, radius * 2, int(start_angle * 16), int(angle * 16))
            start_angle += angle

        # 图例
        legend_x = cx + radius + 16
        legend_y = cy - (len(self._data) * 16) // 2
        for i, d in enumerate(self._data):
            color = QColor(colors[i % len(colors)])
            painter.fillRect(legend_x, legend_y + i * 16, 10, 10, color)
            painter.setPen(QColor("#cccccc"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            pct = d.get("value", 0) / total * 100
            text = f"{d.get('label', '')} {pct:.1f}%"
            painter.drawText(legend_x + 14, legend_y + i * 16 + 10, text)

        painter.setPen(QColor("#cccccc"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        painter.drawText(margin, margin + 12, self._title)
        painter.end()

