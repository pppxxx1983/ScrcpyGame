from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QVBoxLayout,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QSlider,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
import sqlite3
from pathlib import Path
from log_manager import LogManager

class KickoffDashboardDialog(QDialog):
    """启动完成度仪表盘：检查项目各维度的准备状态。"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("启动完成度仪表盘")
        self.resize(700, 500)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 总体进度
        self.progress_bar = QSlider(Qt.Orientation.Horizontal)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setEnabled(False)
        self.progress_bar.setStyleSheet(
            "QSlider::groove:horizontal { height: 12px; background: #333333; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: #0e639c; border-radius: 6px; }"
            "QSlider::handle:horizontal { width: 0px; }"
        )
        self.lbl_progress = QLabel("完成度: 0%")
        self.lbl_progress.setStyleSheet("color: #4ec9b0; font-size: 18px; font-weight: bold;")
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_progress)
        layout.addWidget(self.progress_bar)

        # 检查项表格
        self.check_table = QTableWidget()
        self.check_table.setColumnCount(4)
        self.check_table.setHorizontalHeaderLabels(["维度", "状态", "数量/详情", "建议"])
        self.check_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.check_table.setColumnWidth(0, 140)
        self.check_table.setColumnWidth(1, 60)
        self.check_table.setColumnWidth(2, 160)
        self.check_table.horizontalHeader().setStretchLastSection(True)
        self.check_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.check_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.check_table, 1)

        btn_refresh = QPushButton("刷新检查")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._run_checks)
        layout.addWidget(btn_refresh)

        self._run_checks()

    def _run_checks(self):
        checks = []

        # 1. 设备连接
        connected = bool(self.main_window.client and self.main_window.client.alive)
        checks.append(("设备连接", connected, "已连接" if connected else "未连接", "请连接设备" if not connected else ""))

        # 2. API Key
        env_path = Path(".env")
        has_keys = env_path.exists() and any("API_KEY" in line for line in env_path.read_text(encoding="utf-8").splitlines() if "=" in line)
        checks.append(("API Key", has_keys, "已配置" if has_keys else "未配置", "请创建 .env 文件" if not has_keys else ""))

        # 3. 数据库
        db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
        db_exists = db_path.exists()
        checks.append(("数据库", db_exists, "已存在" if db_exists else "未创建", ""))

        # 4. 场景库
        scene_count = 0
        if db_exists:
            try:
                conn = sqlite3.connect(str(db_path))
                scene_count = conn.execute("SELECT COUNT(*) FROM scene").fetchone()[0]
                conn.close()
            except Exception:
                pass
        checks.append(("场景库", scene_count > 0, f"{scene_count} 个场景", "请录制并识别场景" if scene_count == 0 else ""))

        # 5. 规则库
        rule_count = 0
        if db_exists:
            try:
                conn = sqlite3.connect(str(db_path))
                rule_count = conn.execute("SELECT COUNT(*) FROM runtime_rule").fetchone()[0]
                conn.close()
            except Exception:
                pass
        checks.append(("规则库", rule_count > 0, f"{rule_count} 条规则", "请审核事件生成规则" if rule_count == 0 else ""))

        # 6. UI 元素库
        element_count = 0
        if db_exists:
            try:
                conn = sqlite3.connect(str(db_path))
                element_count = conn.execute("SELECT COUNT(*) FROM ui_element").fetchone()[0]
                conn.close()
            except Exception:
                pass
        checks.append(("UI 元素库", element_count > 0, f"{element_count} 个元素", "请审核事件生成元素" if element_count == 0 else ""))

        # 7. YOLO 数据
        yolo_dir = Path("game_agent_data") / "games" / "my_game" / "yolo_events"
        has_yolo = yolo_dir.exists() and any(yolo_dir.rglob("*.pt"))
        checks.append(("YOLO 模型", has_yolo, "已训练" if has_yolo else "未训练", "请完成 YOLO 审核和训练" if not has_yolo else ""))

        # 8. 录像目录
        recordings_exist = (Path("recordings").exists() and any(Path("recordings").iterdir())) or (Path("game_agent_data") / "games" / "my_game" / "raw_videos").exists()
        checks.append(("录像数据", recordings_exist, "有录像" if recordings_exist else "无录像", "请开始录制操作" if not recordings_exist else ""))

        passed = sum(1 for _, ok, _, _ in checks if ok)
        total = len(checks)
        pct = int(passed / total * 100)
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(f"完成度: {pct}% ({passed}/{total})")

        self.check_table.setRowCount(len(checks))
        for row, (dim, ok, detail, advice) in enumerate(checks):
            self.check_table.setItem(row, 0, QTableWidgetItem(dim))
            status_item = QTableWidgetItem("✅" if ok else "❌")
            status_item.setForeground(QColor("#4ec9b0" if ok else "#f44747"))
            self.check_table.setItem(row, 1, status_item)
            self.check_table.setItem(row, 2, QTableWidgetItem(detail))
            advice_item = QTableWidgetItem(advice)
            advice_item.setForeground(QColor("#ffcc00") if advice else QColor("#888888"))
            self.check_table.setItem(row, 3, advice_item)

