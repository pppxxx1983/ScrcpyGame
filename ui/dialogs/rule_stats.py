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
from PySide6.QtGui import QColor, QBrush
from ui.widgets.charts import BarChartWidget, PieChartWidget
from log_manager import LogManager

class RuntimeRuleDebugDialog(QDialog):
    """Runtime Rule 命中调试面板：展示命中原因、候选规则、分数。"""

    def __init__(self, debug_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("规则命中调试")
        self.resize(960, 720)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        self._debug = debug_data or {}
        self._setup_ui()
        self._render()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 顶部信息栏
        self.info_label = QLabel()
        self.info_label.setStyleSheet(
            "background-color: #252526; color: #dcdcaa; padding: 8px; "
            "border: 1px solid #444444; font-weight: bold;"
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # 步骤结果卡片
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.step_cards = {}
        for step_name, title, color in [
            ("runtime_rule", "Runtime Rule", "#0e639c"),
            ("yolo", "YOLO", "#6a9955"),
            ("hash", "Hash", "#ffcc00"),
            ("llm", "LLM", "#4ec9b0"),
        ]:
            card = self._build_card(title, "未执行", color)
            cards.addWidget(card)
            self.step_cards[step_name] = card
        layout.addLayout(cards)

        # 详情标签页
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { background-color: #252526; border: 1px solid #444444; }"
            "QTabBar::tab { background-color: #333333; color: #cccccc; padding: 6px 12px; }"
            "QTabBar::tab:selected { background-color: #0e639c; color: white; }"
        )

        # Runtime Rule 页
        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(7)
        self.rule_table.setHorizontalHeaderLabels(
            ["ID", "元素名", "BBOX", "置信度", "命中", "启用", "原因/状态"]
        )
        self.rule_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.rule_table.setColumnWidth(0, 50)
        self.rule_table.setColumnWidth(1, 140)
        self.rule_table.setColumnWidth(2, 140)
        self.rule_table.setColumnWidth(3, 60)
        self.rule_table.setColumnWidth(4, 50)
        self.rule_table.setColumnWidth(5, 50)
        self.rule_table.horizontalHeader().setStretchLastSection(True)
        self.rule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabs.addTab(self.rule_table, "Runtime Rules")

        # YOLO 页
        self.yolo_table = QTableWidget()
        self.yolo_table.setColumnCount(5)
        self.yolo_table.setHorizontalHeaderLabels(
            ["类别", "BBOX", "置信度", "包含点击", "来源"]
        )
        self.yolo_table.setStyleSheet(self.rule_table.styleSheet())
        self.yolo_table.setColumnWidth(0, 140)
        self.yolo_table.setColumnWidth(1, 140)
        self.yolo_table.setColumnWidth(2, 70)
        self.yolo_table.setColumnWidth(3, 70)
        self.yolo_table.horizontalHeader().setStretchLastSection(True)
        self.yolo_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.yolo_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabs.addTab(self.yolo_table, "YOLO 检测")

        # Hash 页
        self.hash_widget = QWidget()
        hash_layout = QVBoxLayout(self.hash_widget)
        hash_layout.setContentsMargins(8, 8, 8, 8)
        self.hash_label = QLabel("暂无数据")
        self.hash_label.setStyleSheet("color: #cccccc; font-family: Consolas; font-size: 12px;")
        self.hash_label.setWordWrap(True)
        hash_layout.addWidget(self.hash_label)
        hash_layout.addStretch(1)
        self.tabs.addTab(self.hash_widget, "Hash 匹配")

        # LLM 页
        self.llm_widget = QWidget()
        llm_layout = QVBoxLayout(self.llm_widget)
        llm_layout.setContentsMargins(8, 8, 8, 8)
        self.llm_label = QLabel("暂无数据")
        self.llm_label.setStyleSheet("color: #cccccc; font-family: Consolas; font-size: 12px;")
        self.llm_label.setWordWrap(True)
        llm_layout.addWidget(self.llm_label)
        llm_layout.addStretch(1)
        self.tabs.addTab(self.llm_widget, "LLM 解析")

        layout.addWidget(self.tabs, 1)

        # 底部最终结果
        self.result_label = QLabel()
        self.result_label.setStyleSheet(
            "background-color: #252526; color: #4ec9b0; padding: 8px; "
            "border: 1px solid #444444; font-weight: bold; font-size: 13px;"
        )
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

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
        lbl_value.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        card_layout.addWidget(lbl_value)
        card._value_label = lbl_value
        return card

    def _update_card(self, step_name: str, value: str, color: str = None):
        card = self.step_cards.get(step_name)
        if card:
            card._value_label.setText(value)
            if color:
                card._value_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")

    def _render(self):
        click = self._debug.get("click", {})
        scene = self._debug.get("scene_result") or {}
        scene_key = scene.get("scene_key", "未知场景")
        scene_id = scene.get("scene_id", "-")
        self.info_label.setText(
            f"场景: {scene_key} (ID={scene_id})  |  "
            f"点击坐标: ({click.get('x', '-')}, {click.get('y', '-')})"
        )

        steps = self._debug.get("steps", [])
        step_map = {s.get("name"): s for s in steps}

        # Runtime Rule
        rule_step = step_map.get("runtime_rule", {})
        candidates = rule_step.get("candidates", [])
        self.rule_table.setRowCount(len(candidates))
        matched_any = False
        for row, c in enumerate(candidates):
            self.rule_table.setItem(row, 0, QTableWidgetItem(str(c.get("id", ""))))
            self.rule_table.setItem(row, 1, QTableWidgetItem(str(c.get("element_name", ""))))
            bbox = c.get("bbox_xyxy", [])
            bbox_str = f"[{','.join(str(int(v)) for v in bbox)}]" if len(bbox) == 4 else str(bbox)
            self.rule_table.setItem(row, 2, QTableWidgetItem(bbox_str))
            self.rule_table.setItem(row, 3, QTableWidgetItem(f"{c.get('confidence', 0):.2f}"))
            contains = c.get("contains_click")
            hit_item = QTableWidgetItem("是" if contains else "否")
            hit_item.setForeground(QColor("#4ec9b0" if contains else "#f44747"))
            self.rule_table.setItem(row, 4, hit_item)
            enabled = c.get("enabled", True)
            en_item = QTableWidgetItem("是" if enabled else "否")
            en_item.setForeground(QColor("#4ec9b0" if enabled else "#f44747"))
            self.rule_table.setItem(row, 5, en_item)
            reason = c.get("reason", "")
            if not reason:
                reason = "命中" if contains else "坐标不在范围内"
            self.rule_table.setItem(row, 6, QTableWidgetItem(reason))
            if contains:
                matched_any = True
                for col in range(7):
                    item = self.rule_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#1e3a2f"))
        self._update_card(
            "runtime_rule",
            f"命中" if matched_any else f"未命中 ({len(candidates)}条)",
            "#4ec9b0" if matched_any else "#f44747",
        )

        # YOLO
        yolo_step = step_map.get("yolo", {})
        objects = yolo_step.get("objects", [])
        self.yolo_table.setRowCount(len(objects))
        yolo_matched = False
        for row, obj in enumerate(objects):
            self.yolo_table.setItem(row, 0, QTableWidgetItem(str(obj.get("class_name", ""))))
            bbox = obj.get("bbox_xyxy", [])
            bbox_str = f"[{','.join(str(int(v)) for v in bbox)}]" if len(bbox) == 4 else str(bbox)
            self.yolo_table.setItem(row, 1, QTableWidgetItem(bbox_str))
            self.yolo_table.setItem(row, 2, QTableWidgetItem(f"{obj.get('confidence', 0):.2f}"))
            best = yolo_step.get("best_match")
            is_best = best and best.get("bbox_xyxy") == obj.get("bbox_xyxy") and best.get("class_name") == obj.get("class_name")
            contains_item = QTableWidgetItem("是" if is_best else "否")
            contains_item.setForeground(QColor("#4ec9b0" if is_best else "#cccccc"))
            self.yolo_table.setItem(row, 3, contains_item)
            self.yolo_table.setItem(row, 4, QTableWidgetItem(str(obj.get("source", ""))))
            if is_best:
                yolo_matched = True
                for col in range(5):
                    item = self.yolo_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#1e3a2f"))
        self._update_card(
            "yolo",
            f"命中" if yolo_matched else f"未命中 ({len(objects)}个)",
            "#4ec9b0" if yolo_matched else "#f44747",
        )

        # Hash
        hash_step = step_map.get("hash", {})
        fp_summary = hash_step.get("fingerprint_summary", {})
        best_match = hash_step.get("best_match")
        hash_lines = []
        hash_lines.append(f"指纹摘要:")
        for k, v in fp_summary.items():
            hash_lines.append(f"  {k}: {v}")
        if best_match:
            hash_lines.append(f"\n最佳匹配:")
            hash_lines.append(f"  ID: {best_match.get('id')}")
            hash_lines.append(f"  元素: {best_match.get('element_name')}")
            hash_lines.append(f"  置信度: {best_match.get('confidence', 0):.4f}")
        else:
            hash_lines.append("\n无匹配元素")
        self.hash_label.setText("\n".join(hash_lines))
        hash_matched = hash_step.get("matched", False)
        self._update_card(
            "hash",
            "命中" if hash_matched else "未命中",
            "#4ec9b0" if hash_matched else "#f44747",
        )

        # LLM
        llm_step = step_map.get("llm", {})
        result_summary = llm_step.get("result_summary", {})
        llm_lines = []
        llm_lines.append(f"元素名: {result_summary.get('element_name', '-')}")
        llm_lines.append(f"元素类型: {result_summary.get('element_type', '-')}")
        llm_lines.append(f"置信度: {result_summary.get('confidence', '-')}")
        llm_lines.append(f"解析成功: {'是' if result_summary.get('parse_ok') else '否'}")
        if result_summary.get("error"):
            llm_lines.append(f"错误: {result_summary['error']}")
        self.llm_label.setText("\n".join(llm_lines))
        llm_matched = llm_step.get("matched", False)
        self._update_card(
            "llm",
            "命中" if llm_matched else "未命中",
            "#4ec9b0" if llm_matched else "#f44747",
        )

        # 最终结果
        status_order = ["runtime_rule", "yolo", "hash", "llm"]
        final_status = "未知"
        for name in status_order:
            step = step_map.get(name, {})
            if step.get("matched"):
                final_status = f"{name} 命中"
                break
        self.result_label.setText(f"最终命中结果: {final_status}")


class RuleStatsDialog(QDialog):
    """规则命中率统计和失败率趋势面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("规则命中率统计")
        self.resize(900, 640)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 顶部统计卡片行
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_widgets = []
        for title, color in [
            ("总规则", "#0e639c"),
            ("已启用", "#6a9955"),
            ("总命中", "#ffcc00"),
            ("成功率", "#4ec9b0"),
        ]:
            card = self._build_card(title, "0", color)
            cards.addWidget(card)
            self.card_widgets.append(card)
        layout.addLayout(cards)

        # 图表行
        charts = QHBoxLayout()
        charts.setSpacing(10)

        self.bar_chart = BarChartWidget([], "规则命中排行 TOP10")
        charts.addWidget(self.bar_chart, 1)

        right_charts = QVBoxLayout()
        right_charts.setSpacing(10)
        self.pie_enabled = PieChartWidget([], "规则启用分布")
        self.pie_action = PieChartWidget([], "Action 成功/失败")
        right_charts.addWidget(self.pie_enabled)
        right_charts.addWidget(self.pie_action)
        charts.addLayout(right_charts)
        layout.addLayout(charts, 1)

        # 底部规则明细表
        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(5)
        self.rule_table.setHorizontalHeaderLabels(["规则 Key", "场景", "元素", "命中", "状态"])
        self.rule_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.rule_table.setColumnWidth(0, 240)
        self.rule_table.setColumnWidth(1, 100)
        self.rule_table.setColumnWidth(2, 100)
        self.rule_table.setColumnWidth(3, 60)
        self.rule_table.horizontalHeader().setStretchLastSection(True)
        self.rule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rule_table.setMaximumHeight(180)
        layout.addWidget(self.rule_table)

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

            # 规则统计
            rule_stats = dm.get_runtime_rule_stats()
            self._update_card(0, str(rule_stats.get("total", 0)))
            self._update_card(1, str(rule_stats.get("enabled", 0)))
            self._update_card(2, str(rule_stats.get("total_hits", 0)))

            # Action 统计
            action_stats = dm.get_action_stats()
            total = action_stats.get("total_actions", 0)
            success = action_stats.get("total_success", 0)
            fail = action_stats.get("total_fail", 0)
            success_rate = action_stats.get("success_rate", 0)
            self._update_card(3, f"{success_rate * 100:.1f}%")

            # 规则命中排行柱状图
            top_rules = dm.list_runtime_rules_top_hits(10)
            bar_data = [
                {"label": r.get("element_name", "")[:6] or str(i + 1), "value": r.get("hits", 0)}
                for i, r in enumerate(top_rules)
            ]
            self.bar_chart.set_data(bar_data)

            # 启用/禁用饼图
            enabled = rule_stats.get("enabled", 0)
            disabled = rule_stats.get("disabled", 0)
            self.pie_enabled.set_data([
                {"label": "已启用", "value": enabled},
                {"label": "已禁用", "value": disabled},
            ])

            # Action 成功/失败饼图
            self.pie_action.set_data([
                {"label": "成功", "value": success},
                {"label": "失败", "value": fail},
            ])

            # 规则明细表
            self.rule_table.setRowCount(len(top_rules))
            for row, r in enumerate(top_rules):
                self.rule_table.setItem(row, 0, QTableWidgetItem(r.get("rule_key", "")[:40]))
                self.rule_table.setItem(row, 1, QTableWidgetItem(r.get("scene_key", "")[:12]))
                self.rule_table.setItem(row, 2, QTableWidgetItem(r.get("element_name", "")[:12]))
                self.rule_table.setItem(row, 3, QTableWidgetItem(str(r.get("hits", 0))))
                status = "启用" if r.get("enabled") else "禁用"
                item = QTableWidgetItem(status)
                item.setForeground(QBrush(QColor("#6a9955" if r.get("enabled") else "#f44747")))
                self.rule_table.setItem(row, 4, item)

        except Exception as e:
            LogManager().append(f"[RuleStats] 加载数据失败: {e}")

