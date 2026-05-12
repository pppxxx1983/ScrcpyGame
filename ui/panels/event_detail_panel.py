from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from log_manager import LogManager
from scene_index import SceneIndex
from ui.dialogs.rule_stats import RuntimeRuleDebugDialog




from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget
class EventDetailPanelMixin:
    def _open_event_tab(self, item: QListWidgetItem):
        data = item.data(256)
        if not data or not isinstance(data, dict):
            return

        if data.get("type") == "physical_folder":
            folder = data.get("folder")
            if folder:
                self._open_physical_event_tab(Path(folder))
            return

        session_id = data.get("session_id", "")
        idx = data.get("index_no", 0)
        x = data.get("x", 0)
        y = data.get("y", 0)
        before_img = data.get("before_image")
        after_300 = data.get("after_300ms_image")
        after_800 = data.get("after_800ms_image")

        # 找到或创建唯一的"事件" tab
        event_tab = None
        for i in range(self.ui.tabWidget.count()):
            if self.ui.tabWidget.tabText(i) == "事件":
                event_tab = self.ui.tabWidget.widget(i)
                break

        if event_tab is None:
            event_tab = QWidget()
            event_tab.setStyleSheet("background-color: #1e1e1e;")
            self.ui.tabWidget.addTab(event_tab, "事件")
            outer_layout = QVBoxLayout(event_tab)
            outer_layout.setContentsMargins(8, 8, 8, 8)
        else:
            outer_layout = event_tab.layout()
            # 删除旧的内容容器
            if outer_layout.count() > 0:
                old_content = outer_layout.itemAt(0).widget()
                if old_content:
                    old_content.deleteLater()

        # 新的内容容器
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        info = QLabel(f"Session: {session_id}  |  事件 #{idx:03d}  |  坐标: ({x}, {y})")
        info.setStyleSheet("color: #888888; padding: 4px;")
        layout.addWidget(info)

        images_layout = QHBoxLayout()

        def add_image_column(path: str, label_text: str):
            col = QVBoxLayout()
            lbl_title = QLabel(label_text)
            lbl_title.setStyleSheet("color: #cccccc; font-weight: bold;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl_title)

            img_label = QLabel()
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_label.setMinimumSize(200, 150)
            img_label.setStyleSheet("background-color: #111111; border: 1px solid #333333;")
            if path:
                p = Path(path)
                if p.exists():
                    pixmap = QPixmap(str(p.resolve()))
                    if not pixmap.isNull():
                        img_label.setPixmap(pixmap.scaled(
                            320, 240,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        ))
                    else:
                        img_label.setText("加载失败")
                        img_label.setStyleSheet("color: #f44747;")
                else:
                    img_label.setText(f"无图片\n{p.name}")
                    img_label.setStyleSheet("color: #666666;")
                    LogManager().append(f"[EventTab] 图片不存在: {p}")
            else:
                img_label.setText("无图片\n(path=None)")
                img_label.setStyleSheet("color: #666666;")
            col.addWidget(img_label)
            images_layout.addLayout(col)

        LogManager().append(f"[EventTab] before={before_img}, after300={after_300}, after800={after_800}")
        add_image_column(before_img, "点击前")
        add_image_column(after_300, "300ms后")
        add_image_column(after_800, "800ms后")

        layout.addLayout(images_layout)

        # 规则调试按钮
        debug_btn_row = QHBoxLayout()
        btn_debug = QPushButton("规则调试")
        btn_debug.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_debug.clicked.connect(lambda: self._show_event_rule_debug(data))
        debug_btn_row.addWidget(btn_debug)
        debug_btn_row.addStretch(1)
        layout.addLayout(debug_btn_row)

        layout.addStretch(1)
        outer_layout.addWidget(content)

        tab_idx = self.ui.tabWidget.indexOf(event_tab)
        self.ui.tabWidget.setCurrentIndex(tab_idx)

    def _show_event_rule_debug(self, data: dict):
        before_img = data.get("before_image")
        if not before_img:
            QMessageBox.warning(self, "规则调试", "没有 before 图片，无法调试。")
            return
        before_path = Path(before_img)
        if not before_path.exists():
            QMessageBox.warning(self, "规则调试", f"图片不存在: {before_img}")
            return
        op_dir = before_path.parent
        x = data.get("x", 0)
        y = data.get("y", 0)
        event_data = {
            "images": {"before": before_path.name},
            "touch": {"frame_start": {"x": x, "y": y}},
        }
        try:
            from scene_index import SceneIndex
            scene_result = SceneIndex().ensure_scene(before_path, threshold=0.92)
        except Exception as e:
            LogManager().append(f"[RuleDebug] 场景识别失败: {e}")
            scene_result = None
        result = self._analyze_click_target(op_dir, event_data, scene_result, collect_debug=True)
        debug_info = result.get("_debug", {})
        dlg = RuntimeRuleDebugDialog(debug_info, self)
        dlg.exec()

    def _open_physical_event_tab(self, folder: Path):
        if not folder.exists() or not folder.is_dir():
            return

        event_tab, outer_layout = self._get_or_create_single_event_tab()
        content = self._build_screenshot_stats_tab(folder)
        outer_layout.addWidget(content)
        self.ui.tabWidget.setCurrentIndex(self.ui.tabWidget.indexOf(event_tab))

