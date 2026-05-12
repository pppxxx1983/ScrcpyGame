from __future__ import annotations

from pathlib import Path
from datetime import datetime

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from log_manager import LogManager
from scene_index import SceneIndex




from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QTextEdit, QTreeWidgetItem, QVBoxLayout, QWidget
class SceneAuditPanelMixin:
    def _open_audit_scene_tab(self, item: QTreeWidgetItem):
        """单击审核列表项时，刷新唯一的'审核' tab 页。"""
        row_id = item.data(0, 256)
        scene_key = item.text(0)
        scene_type = item.text(1)
        review_status_text = item.text(4)
        image_path_str = item.data(0, 257)
        if not image_path_str:
            self._set_status("审核: 该场景没有图片路径")
            return

        image_path = Path(image_path_str)
        if not image_path.exists():
            self._set_status(f"审核: 图片不存在 {image_path}")
            return

        # 从数据库读取当前完整数据（包括 description）
        description = ""
        try:
            from scene_index import SceneIndex
            si = SceneIndex()
            with si._connect() as conn:
                row = conn.execute(
                    "SELECT description FROM scenes WHERE id = ?", (row_id,)
                ).fetchone()
                if row:
                    description = row[0] or ""
        except Exception:
            pass

        # 找到或创建唯一的"审核" tab，复用 widget 只替换内容
        audit_tab = None
        for i in range(self.ui.tabWidget.count()):
            if self.ui.tabWidget.tabText(i) == "审核":
                audit_tab = self.ui.tabWidget.widget(i)
                break

        if audit_tab is None:
            audit_tab = QWidget()
            audit_tab.setStyleSheet("background-color: #1e1e1e;")
            self.ui.tabWidget.addTab(audit_tab, "审核")
            layout = QHBoxLayout(audit_tab)
            layout.setContentsMargins(8, 8, 8, 8)
        else:
            layout = audit_tab.layout()
            if layout is not None:
                # 清空布局中的 widget，保留布局本身
                while layout.count():
                    child = layout.takeAt(0)
                    w = child.widget()
                    if w:
                        w.setParent(None)
                        w.deleteLater()

        # 左边：可编辑表单（固定宽度 280）
        form = QWidget()
        form.setFixedWidth(280)
        form_layout = QVBoxLayout(form)
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(0, 0, 0, 0)

        # 状态
        status_row = QHBoxLayout()
        lbl_status = QLabel("状态:")
        lbl_status.setFixedWidth(50)
        status_row.addWidget(lbl_status)
        combo_status = QComboBox()
        combo_status.addItems(["未审核", "审核通过"])
        combo_status.setCurrentIndex(1 if review_status_text == "审核通过" else 0)
        combo_status.setStyleSheet("QComboBox { background-color: #3c3c3c; color: #cccccc; }")
        status_row.addWidget(combo_status, 1)
        form_layout.addLayout(status_row)

        # 类型（预定义分类，只读下拉）
        type_row = QHBoxLayout()
        lbl_type = QLabel("类型:")
        lbl_type.setFixedWidth(50)
        type_row.addWidget(lbl_type)
        combo_type = QComboBox()
        combo_type.setEditable(False)
        type_options = [
            "", "登录界面", "游戏大厅", "战斗画面", "结算界面",
            "背包界面", "商城界面", "设置菜单", "广告弹窗",
            "公告弹窗", "loading", "任务列表", "选人界面",
            "网络断开", "更新提示", "其他",
        ]
        combo_type.addItems(type_options)
        combo_type.setCurrentText(scene_type)
        combo_type.setStyleSheet("QComboBox { background-color: #3c3c3c; color: #cccccc; }")
        type_row.addWidget(combo_type, 1)
        form_layout.addLayout(type_row)

        # 名字
        name_row = QHBoxLayout()
        lbl_name = QLabel("名字:")
        lbl_name.setFixedWidth(50)
        name_row.addWidget(lbl_name)
        edit_name = QLineEdit(scene_key)
        edit_name.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        name_row.addWidget(edit_name, 1)
        form_layout.addLayout(name_row)

        # 说明
        form_layout.addWidget(QLabel("说明:"))
        edit_desc = QTextEdit(description)
        edit_desc.setMaximumHeight(80)
        edit_desc.setStyleSheet("QTextEdit { background-color: #3c3c3c; color: #cccccc; }")
        form_layout.addWidget(edit_desc)

        # 保存按钮
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_save.clicked.connect(lambda: self._save_scene_edit(
            row_id, edit_name.text(), combo_type.currentText(), edit_desc.toPlainText(),
            combo_status.currentIndex(), audit_tab
        ))
        form_layout.addWidget(btn_save)
        form_layout.addStretch(1)

        layout.addWidget(form)

        # 右边：图片显示（自适应缩放）
        class ScalableLabel(QLabel):
            def __init__(self, pixmap: QPixmap, parent=None):
                super().__init__(parent)
                self._orig_pixmap = pixmap
                self.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self.setStyleSheet("background-color: #111111; border: 1px solid #333333;")
                if pixmap.isNull():
                    self.setText("图片加载失败")
                    self.setStyleSheet("color: #f44747; font-size: 16px;")
                else:
                    self._update_scaled()

            def resizeEvent(self, event):
                super().resizeEvent(event)
                if not self._orig_pixmap.isNull():
                    self._update_scaled()

            def _update_scaled(self):
                available = self.contentsRect().size()
                if available.width() <= 0 or available.height() <= 0:
                    return
                scaled = self._orig_pixmap.scaled(
                    available,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.setPixmap(scaled)

        label = ScalableLabel(QPixmap(str(image_path.resolve())), audit_tab)
        layout.addWidget(label, 1)

        idx = self.ui.tabWidget.indexOf(audit_tab)
        if idx < 0:
            idx = self.ui.tabWidget.addTab(audit_tab, "审核")
        self.ui.tabWidget.setCurrentIndex(idx)

    def _save_scene_edit(self, row_id: int, scene_key: str, scene_type: str, description: str, review_status: int, tab: QWidget):
        """保存场景编辑到数据库。"""
        try:
            from scene_index import SceneIndex
            from datetime import datetime
            si = SceneIndex()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with si._connect() as conn:
                conn.execute(
                    "UPDATE scenes SET scene_key = ?, scene_type = ?, description = ?, review_status = ?, updated_at = ? WHERE id = ?",
                    (scene_key, scene_type, description, review_status, now, row_id),
                )
            self._set_status(f"审核: 已保存 '{scene_key}'")
            self._refresh_audit_list()
            # 更新 tab 标题
            self.ui.tabWidget.setTabText(self.ui.tabWidget.indexOf(tab), f"审核 {scene_key[:8]}")
        except Exception as e:
            LogManager().append(f"[Audit] 保存失败: {e}")
            self._set_status(f"审核: 保存失败 - {e}")

