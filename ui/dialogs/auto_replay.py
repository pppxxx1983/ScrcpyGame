from pathlib import Path
from datetime import datetime
import sqlite3
from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QMessageBox,
    QComboBox,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QSlider,
)
from PySide6.QtCore import Qt
from log_manager import LogManager

class AutoReplayDialog(QDialog):
    """自动回放对话框：选择 Session 和事件范围，控制回放速度。"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("自动回放")
        self.resize(700, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        session_row = QHBoxLayout()
        session_row.addWidget(QLabel("Session:"))
        self.combo_session = QComboBox()
        self.combo_session.setStyleSheet(
            "QComboBox { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
        )
        self.combo_session.currentIndexChanged.connect(self._on_session_changed)
        session_row.addWidget(self.combo_session)
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_refresh.clicked.connect(self._load_sessions)
        session_row.addWidget(btn_refresh)
        layout.addLayout(session_row)

        self.event_table = QTableWidget()
        self.event_table.setColumnCount(4)
        self.event_table.setHorizontalHeaderLabels(["#", "时间", "坐标", "场景ID"])
        self.event_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.event_table.setColumnWidth(0, 50)
        self.event_table.setColumnWidth(1, 160)
        self.event_table.setColumnWidth(2, 80)
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.event_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.event_table, 1)

        control_row = QHBoxLayout()
        control_row.addWidget(QLabel("速度:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setMinimum(5)
        self.slider_speed.setMaximum(30)
        self.slider_speed.setValue(10)
        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        control_row.addWidget(self.slider_speed)
        self.lbl_speed = QLabel("1.0x")
        self.lbl_speed.setStyleSheet("color: #cccccc; min-width: 40px;")
        control_row.addWidget(self.lbl_speed)
        control_row.addStretch(1)

        self.btn_start = QPushButton("▶ 开始回放")
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        self.btn_start.clicked.connect(self._on_start)
        control_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #f44747; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #ff6666; }"
        )
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        control_row.addWidget(self.btn_stop)
        layout.addLayout(control_row)

        self._load_sessions()

    def _on_speed_changed(self, value):
        self.lbl_speed.setText(f"{value / 10.0:.1f}x")

    def _load_sessions(self):
        self.combo_session.clear()
        try:
            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            if not db_path.exists():
                return
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT DISTINCT session_id FROM click_event ORDER BY session_id DESC"
            ).fetchall()
            conn.close()
            for row in rows:
                self.combo_session.addItem(str(row[0]))
        except Exception as e:
            LogManager().append(f"[AutoReplay] 加载 session 失败: {e}")

    def _on_session_changed(self, index):
        session_id = self.combo_session.currentText()
        self._load_events(session_id)

    def _load_events(self, session_id: str):
        self.event_table.setRowCount(0)
        if not session_id:
            return
        try:
            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT index_no, timestamp_ms, x, y, before_scene_id FROM click_event "
                "WHERE session_id = ? ORDER BY index_no",
                (session_id,),
            ).fetchall()
            conn.close()
            self.event_table.setRowCount(len(rows))
            for row, (idx, ts, x, y, scene_id) in enumerate(rows):
                dt = datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S.%f")[:-3]
                self.event_table.setItem(row, 0, QTableWidgetItem(str(idx)))
                self.event_table.setItem(row, 1, QTableWidgetItem(dt))
                self.event_table.setItem(row, 2, QTableWidgetItem(f"({x},{y})"))
                self.event_table.setItem(row, 3, QTableWidgetItem(str(scene_id or "-")))
        except Exception as e:
            LogManager().append(f"[AutoReplay] 加载事件失败: {e}")

    def _on_start(self):
        session_id = self.combo_session.currentText()
        if not session_id:
            QMessageBox.warning(self, "自动回放", "请先选择一个 Session。")
            return
        try:
            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT x, y, before_scene_id FROM click_event "
                "WHERE session_id = ? ORDER BY index_no",
                (session_id,),
            ).fetchall()
            conn.close()
            if not rows:
                QMessageBox.warning(self, "自动回放", "该 Session 没有事件。")
                return
            events = [{"x": r[0], "y": r[1], "scene_id": r[2]} for r in rows]
            speed = self.slider_speed.value() / 10.0
            delay_ms = int(1000 / speed)
            self.main_window._start_auto_replay(events, delay_ms)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "自动回放", f"启动失败: {e}")

    def _on_stop(self):
        self.main_window._stop_auto_replay()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

