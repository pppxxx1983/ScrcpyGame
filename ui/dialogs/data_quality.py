from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
)
from ui.widgets.charts import PieChartWidget
from agent_data import AgentDataManager
from log_manager import LogManager

class DataQualityDialog(QDialog):
    """数据质量监控面板：展示事件覆盖率、元素统计、规则命中率等。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据质量监控")
        self.resize(900, 640)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 顶部统计卡片
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_widgets = []
        for title, color in [
            ("事件总数", "#0e639c"),
            ("场景覆盖", "#6a9955"),
            ("UI元素", "#ffcc00"),
            ("规则总数", "#4ec9b0"),
            ("Action成功率", "#c586c0"),
        ]:
            card = self._build_card(title, "0", color)
            cards.addWidget(card)
            self.card_widgets.append(card)
        layout.addLayout(cards)

        # 图表行
        charts = QHBoxLayout()
        charts.setSpacing(10)
        self.pie_elements = PieChartWidget([], "UI元素来源分布")
        charts.addWidget(self.pie_elements, 1)
        self.pie_scene = PieChartWidget([], "事件场景覆盖")
        charts.addWidget(self.pie_scene, 1)
        layout.addLayout(charts, 1)

        # 详情表格
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(3)
        self.detail_table.setHorizontalHeaderLabels(["维度", "指标", "数值"])
        self.detail_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.detail_table.setColumnWidth(0, 160)
        self.detail_table.setColumnWidth(1, 240)
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        self.detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.detail_table.setMaximumHeight(200)
        layout.addWidget(self.detail_table)

        btn_refresh = QPushButton("刷新数据")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._load_data)
        layout.addWidget(btn_refresh)

        self._load_data()

    def _build_card(self, title: str, value: str, color: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"background-color: #252526; border-left: 4px solid {color}; padding: 8px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #888888; font-size: 11px;")
        card_layout.addWidget(lbl_title)
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")
        card_layout.addWidget(lbl_value)
        card._value_label = lbl_value
        return card

    def _update_card(self, index: int, value: str):
        if 0 <= index < len(self.card_widgets):
            self.card_widgets[index]._value_label.setText(value)

    def _load_data(self):
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            stats = dm.get_data_quality_stats()

            events = stats.get("events", {})
            elements = stats.get("elements", {})
            scenes = stats.get("scenes", {})
            rules = stats.get("rules", {})
            actions = stats.get("actions", {})

            self._update_card(0, str(events.get("total", 0)))
            self._update_card(1, f"{events.get('scene_coverage', 0) * 100:.1f}%")
            self._update_card(2, str(elements.get("total", 0)))
            self._update_card(3, str(rules.get("total", 0)))
            self._update_card(4, f"{actions.get('success_rate', 0) * 100:.1f}%")

            # UI元素来源分布饼图
            source_dist = elements.get("source_distribution", {})
            self.pie_elements.set_data([
                {"label": k or "unknown", "value": v}
                for k, v in source_dist.items()
            ])

            # 事件场景覆盖饼图
            total_ev = events.get("total", 0)
            with_scene = events.get("with_scene", 0)
            self.pie_scene.set_data([
                {"label": "有场景", "value": with_scene},
                {"label": "无场景", "value": max(0, total_ev - with_scene)},
            ])

            # 详情表格
            details = [
                ("事件", "总事件数", events.get("total", 0)),
                ("事件", "有场景识别", events.get("with_scene", 0)),
                ("事件", "场景覆盖率", f"{events.get('scene_coverage', 0) * 100:.1f}%"),
                ("场景", "已注册场景数", scenes.get("total", 0)),
                ("UI元素", "总元素数", elements.get("total", 0)),
                ("规则", "总规则数", rules.get("total", 0)),
                ("规则", "已启用", rules.get("enabled", 0)),
                ("规则", "已禁用", rules.get("disabled", 0)),
                ("规则", "总命中次数", rules.get("total_hits", 0)),
                ("Action", "总Action数", actions.get("total", 0)),
                ("Action", "成功次数", actions.get("success", 0)),
                ("Action", "失败次数", actions.get("fail", 0)),
                ("Action", "成功率", f"{actions.get('success_rate', 0) * 100:.1f}%"),
            ]
            self.detail_table.setRowCount(len(details))
            for row, (dim, metric, val) in enumerate(details):
                self.detail_table.setItem(row, 0, QTableWidgetItem(dim))
                self.detail_table.setItem(row, 1, QTableWidgetItem(metric))
                self.detail_table.setItem(row, 2, QTableWidgetItem(str(val)))

        except Exception as e:
            LogManager().append(f"[DataQuality] 加载数据失败: {e}")

