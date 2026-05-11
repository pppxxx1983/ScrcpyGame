from pathlib import Path
import json
import sqlite3
from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QMessageBox,
    QComboBox,
    QDialog,
    QFileDialog,
)
from PySide6.QtGui import QColor
from agent_data import AgentDataManager
from log_manager import LogManager

class BehaviorTreeDialog(QDialog):
    """行为树生成与可视化：从 Session 事件序列生成简化行为树。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("行为树生成")
        self.resize(800, 600)
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
        btn_export = QPushButton("导出 JSON")
        btn_export.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; border: 1px solid #555555; padding: 4px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_export.clicked.connect(self._export_json)
        session_row.addWidget(btn_export)
        layout.addLayout(session_row)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["节点类型", "名称", "参数"])
        self.tree_widget.setStyleSheet(
            "QTreeWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTreeWidget::item:selected { background-color: #0e639c; }"
        )
        self.tree_widget.setColumnWidth(0, 120)
        self.tree_widget.setColumnWidth(1, 200)
        self.tree_widget.header().setStretchLastSection(True)
        layout.addWidget(self.tree_widget, 1)

        self._load_sessions()

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
            LogManager().append(f"[BehaviorTree] 加载 session 失败: {e}")

    def _on_session_changed(self, index):
        session_id = self.combo_session.currentText()
        self._generate_tree(session_id)

    def _generate_tree(self, session_id: str):
        self.tree_widget.clear()
        if not session_id:
            return
        try:
            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT index_no, x, y, before_scene_id, after_scene_id FROM click_event "
                "WHERE session_id = ? ORDER BY index_no",
                (session_id,),
            ).fetchall()
            conn.close()
            if not rows:
                return

            root_item = QTreeWidgetItem(self.tree_widget, ["Sequence", "Root", f"events={len(rows)}"])
            root_item.setForeground(0, QColor("#4ec9b0"))
            current_scene = None
            scene_item = None
            for idx, x, y, before_scene, after_scene in rows:
                scene_changed = before_scene != current_scene
                if scene_changed:
                    current_scene = before_scene
                    scene_name = f"Scene_{before_scene}" if before_scene else "Unknown"
                    scene_item = QTreeWidgetItem(root_item, ["Sequence", scene_name, f"scene_id={before_scene or '-'}"])
                    scene_item.setForeground(0, QColor("#ffcc00"))
                    root_item.addChild(scene_item)
                action_item = QTreeWidgetItem(scene_item or root_item, ["Action", f"click_{idx}", f"x={x}, y={y}"])
                action_item.setForeground(0, QColor("#0e639c"))
                if scene_item:
                    scene_item.addChild(action_item)
                else:
                    root_item.addChild(action_item)
                if after_scene and after_scene != before_scene:
                    trans_item = QTreeWidgetItem(action_item, ["Transition", f"To Scene_{after_scene}", f"scene_id={after_scene}"])
                    trans_item.setForeground(0, QColor("#c586c0"))
                    action_item.addChild(trans_item)
            self.tree_widget.expandAll()
            self._bt_json = self._build_json(rows)
        except Exception as e:
            LogManager().append(f"[BehaviorTree] 生成失败: {e}")

    def _build_json(self, rows) -> dict:
        root = {"type": "Sequence", "name": "Root", "children": []}
        current_scene = None
        scene_node = None
        for idx, x, y, before_scene, after_scene in rows:
            if before_scene != current_scene:
                current_scene = before_scene
                scene_node = {
                    "type": "Sequence",
                    "name": f"Scene_{before_scene}" if before_scene else "Unknown",
                    "scene_id": before_scene,
                    "children": [],
                }
                root["children"].append(scene_node)
            action = {
                "type": "Action",
                "name": f"click_{idx}",
                "params": {"x": x, "y": y},
            }
            if after_scene and after_scene != before_scene:
                action["transition"] = {"to_scene_id": after_scene}
            scene_node["children"].append(action)
        return root

    def _export_json(self):
        if not hasattr(self, "_bt_json") or not self._bt_json:
            QMessageBox.warning(self, "行为树", "没有可导出的行为树数据。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出行为树", f"behavior_tree_{self.combo_session.currentText()}.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(self._bt_json, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "行为树", f"已导出到:\n{path}")

