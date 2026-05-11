from pathlib import Path
from datetime import datetime
import sqlite3
from PySide6.QtWidgets import (
    QPushButton,
    QVBoxLayout,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
)
from agent_data import AgentDataManager
from log_manager import LogManager

class SemanticAggregationDialog(QDialog):
    """语义动作聚合面板：分析高频坐标、场景转换路径和重复模式。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("语义动作聚合")
        self.resize(900, 640)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        btn_refresh = QPushButton("刷新分析")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._load_data)
        layout.addWidget(btn_refresh)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { background-color: #252526; border: 1px solid #444444; }"
            "QTabBar::tab { background-color: #333333; color: #cccccc; padding: 6px 12px; }"
            "QTabBar::tab:selected { background-color: #0e639c; color: white; }"
        )

        # 高频坐标页
        self.coord_table = QTableWidget()
        self.coord_table.setColumnCount(4)
        self.coord_table.setHorizontalHeaderLabels(["坐标", "出现次数", "关联场景", "首次出现"])
        self._style_table(self.coord_table)
        self.tabs.addTab(self.coord_table, "高频坐标")

        # 场景转换页
        self.transition_table = QTableWidget()
        self.transition_table.setColumnCount(3)
        self.transition_table.setHorizontalHeaderLabels(["从场景", "到场景", "转换次数"])
        self._style_table(self.transition_table)
        self.tabs.addTab(self.transition_table, "场景转换")

        # 重复模式页
        self.pattern_table = QTableWidget()
        self.pattern_table.setColumnCount(2)
        self.pattern_table.setHorizontalHeaderLabels(["模式序列", "出现次数"])
        self._style_table(self.pattern_table)
        self.tabs.addTab(self.pattern_table, "重复模式")

        layout.addWidget(self.tabs, 1)
        self._load_data()

    def _style_table(self, table: QTableWidget):
        table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)

    def _load_data(self):
        try:
            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            if not db_path.exists():
                return
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 高频坐标
            rows = cursor.execute(
                "SELECT x, y, before_scene_id, COUNT(*) as cnt, MIN(timestamp_ms) as first_ts "
                "FROM click_event GROUP BY x, y, before_scene_id ORDER BY cnt DESC LIMIT 100"
            ).fetchall()
            self.coord_table.setRowCount(len(rows))
            for row, (x, y, scene_id, cnt, first_ts) in enumerate(rows):
                self.coord_table.setItem(row, 0, QTableWidgetItem(f"({x},{y})"))
                self.coord_table.setItem(row, 1, QTableWidgetItem(str(cnt)))
                self.coord_table.setItem(row, 2, QTableWidgetItem(str(scene_id or "-")))
                dt = datetime.fromtimestamp(first_ts / 1000).strftime("%m-%d %H:%M") if first_ts else "-"
                self.coord_table.setItem(row, 3, QTableWidgetItem(dt))

            # 场景转换
            rows = cursor.execute(
                "SELECT before_scene_id, after_scene_id, COUNT(*) as cnt "
                "FROM click_event WHERE after_scene_id IS NOT NULL AND before_scene_id != after_scene_id "
                "GROUP BY before_scene_id, after_scene_id ORDER BY cnt DESC LIMIT 100"
            ).fetchall()
            self.transition_table.setRowCount(len(rows))
            for row, (before, after, cnt) in enumerate(rows):
                self.transition_table.setItem(row, 0, QTableWidgetItem(str(before or "-")))
                self.transition_table.setItem(row, 1, QTableWidgetItem(str(after or "-")))
                self.transition_table.setItem(row, 2, QTableWidgetItem(str(cnt)))

            # 重复模式（简化的连续场景序列，长度 2-4）
            rows = cursor.execute(
                "SELECT session_id, index_no, before_scene_id FROM click_event ORDER BY session_id, index_no"
            ).fetchall()
            conn.close()

            patterns = {}
            scenes = [r[2] for r in rows]
            for length in (2, 3, 4):
                for i in range(len(scenes) - length + 1):
                    seq = tuple(scenes[i:i + length])
                    patterns[seq] = patterns.get(seq, 0) + 1
            # 过滤出现次数 > 1 的
            filtered = [(seq, cnt) for seq, cnt in patterns.items() if cnt > 1]
            filtered.sort(key=lambda x: x[1], reverse=True)
            filtered = filtered[:100]
            self.pattern_table.setRowCount(len(filtered))
            for row, (seq, cnt) in enumerate(filtered):
                seq_str = " → ".join(str(s or "-") for s in seq)
                self.pattern_table.setItem(row, 0, QTableWidgetItem(seq_str))
                self.pattern_table.setItem(row, 1, QTableWidgetItem(str(cnt)))

        except Exception as e:
            LogManager().append(f"[SemanticAggregation] 加载数据失败: {e}")

