from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtCore import QTimer, Qt

from log_manager import LogManager


from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
class ExecutionPanelMixin:
    def _setup_execution_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.execution_panel = QWidget(self.side_panel)
        self.execution_panel.setObjectName("executionPanel")
        panel_layout = QVBoxLayout(self.execution_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("任务执行")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        # 执行 / 停止 按钮行
        self.runtime_feedback_label = QLabel("Runtime: waiting")
        self.runtime_feedback_label.setWordWrap(True)
        self.runtime_feedback_label.setStyleSheet("background-color: #111111; color: #9cdcfe; border: 1px solid #333333; padding: 6px; font-weight: bold;")
        panel_layout.addWidget(self.runtime_feedback_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_execute = QPushButton("▶ 执行", self.execution_panel)
        self.btn_execute.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; "
            "border: 1px solid #555555; padding: 6px; font-size: 14px; }"
            "QPushButton:hover { background-color: #1177bb; }"
            "QPushButton:disabled { background-color: #3c3c3c; color: #888888; }"
        )
        self.btn_execute.clicked.connect(self.do_start_execution)
        btn_row.addWidget(self.btn_execute)

        self.btn_stop_execution = QPushButton("⏹ 停止", self.execution_panel)
        self.btn_stop_execution.setStyleSheet(
            "QPushButton { background-color: #f44747; color: white; "
            "border: 1px solid #555555; padding: 6px; font-size: 14px; }"
            "QPushButton:hover { background-color: #ff5555; }"
            "QPushButton:disabled { background-color: #3c3c3c; color: #888888; }"
        )
        self.btn_stop_execution.clicked.connect(self.do_stop_execution)
        self.btn_stop_execution.setEnabled(False)
        btn_row.addWidget(self.btn_stop_execution)

        panel_layout.addLayout(btn_row)

        # 任务队列
        task_title = QLabel("任务队列")
        task_title.setStyleSheet("font-weight: bold; color: #888888; padding: 4px;")
        panel_layout.addWidget(task_title)

        self.task_list = QTreeWidget(self.execution_panel)
        self.task_list.setObjectName("taskList")
        self.task_list.setHeaderHidden(True)
        self.task_list.setIndentation(20)
        self.task_list.setStyleSheet(
            "QTreeWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; padding: 4px; }"
            "QTreeWidget::item { padding: 4px; border-bottom: 1px solid #333333; }"
            "QTreeWidget::item:selected { background-color: #0e639c; color: white; }"
            "QTreeWidget::item:hover { background-color: #2a2d2e; }"
        )
        # 任务队列初始为空，执行后动态添加
        panel_layout.addWidget(self.task_list, 1)  # stretch=1 让列表占据剩余空间

        layout.insertWidget(3, self.execution_panel)
        self.execution_panel.setVisible(False)

        # 程序启动时预填充所有场景类到任务队列
        try:
            from analysis.scene_classes import SceneFactory
            for level, scene_class in SceneFactory._level_map.items():
                self._on_task_added(scene_class.DISPLAY_NAME, True)
        except Exception:
            pass

    def _on_task_added(self, text: str, pending: bool):
        item = QTreeWidgetItem()
        item.setText(0, text)
        item.setData(0, 257, text)  # 存储 base_text 用于匹配
        if pending:
            item.setData(0, 256, "pending")
            item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_MessageBoxInformation))
            self._start_task_timer(item, text)
        else:
            item.setData(0, 256, "done")
            item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DialogApplyButton))
        self.task_list.addTopLevelItem(item)

    def _on_task_subtask_added(self, parent_text: str, sub_text: str):
        """在指定父任务下添加子任务；同名子任务已存在则复用，不重复插入。"""
        for i in range(self.task_list.topLevelItemCount()):
            parent = self.task_list.topLevelItem(i)
            if parent and parent.data(0, 257) == parent_text:
                # 查找是否已有同名子任务
                existing = None
                for j in range(parent.childCount()):
                    child = parent.child(j)
                    if child.data(0, 257) == sub_text:
                        existing = child
                        break
                if existing is not None:
                    # 复用已有子任务，重置为 pending 状态并重启计时器
                    existing.setData(0, 256, "pending")
                    existing.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_MessageBoxInformation))
                    if hasattr(self, '_task_timers') and id(existing) in self._task_timers:
                        self._task_timers[id(existing)].stop()
                        del self._task_timers[id(existing)]
                    self._start_task_timer(existing, sub_text)
                    parent.setExpanded(True)
                    return
                # 没有同名子任务，新建
                child = QTreeWidgetItem(parent)
                child.setText(0, sub_text)
                child.setData(0, 257, sub_text)
                child.setData(0, 256, "pending")
                child.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_MessageBoxInformation))
                parent.setExpanded(True)
                break

    def _find_task_item(self, text: str):
        """递归查找任务项（支持子节点）。"""
        def _search(item):
            if item.data(0, 257) == text:
                return item
            for i in range(item.childCount()):
                result = _search(item.child(i))
                if result:
                    return result
            return None

        for i in range(self.task_list.topLevelItemCount()):
            result = _search(self.task_list.topLevelItem(i))
            if result:
                return result
        return None

    def _start_task_timer(self, item, base_text: str):
        """为任务项启动 FPS 刷新计时器，每秒从对应场景线程获取 FPS 更新文本。"""
        if not hasattr(self, '_task_timers'):
            self._task_timers = {}
        timer = QTimer(self)
        timer.setInterval(1000)

        def _tick():
            fps = 0.0
            if hasattr(self, 'execution_engine') and self.execution_engine:
                fps = self.execution_engine.get_scene_fps(base_text)
            item.setText(0, f"{base_text} ({fps:.1f} fps)")

        timer.timeout.connect(_tick)
        timer.start()
        self._task_timers[id(item)] = timer

    def _on_task_cleared(self):
        self.task_list.clear()
        if hasattr(self, '_task_timers'):
            for timer in self._task_timers.values():
                timer.stop()
            self._task_timers.clear()

    def _on_task_done(self, text: str, success: bool):
        item = self._find_task_item(text)
        if item is None:
            return
        item.setData(0, 256, "done")
        # 停止计时器
        if hasattr(self, '_task_timers') and id(item) in self._task_timers:
            self._task_timers[id(item)].stop()
            del self._task_timers[id(item)]
        icon = (
            self.style().standardIcon(
                self.style().StandardPixmap.SP_DialogApplyButton
            )
            if success
            else self.style().standardIcon(
                self.style().StandardPixmap.SP_MessageBoxCritical
            )
        )
        item.setIcon(0, icon)

    def _draw_objects_on_pixmap(self, pixmap: QPixmap, objects: list) -> QPixmap:
        """在图片上绘制对象 bbox 和标签。"""
        if not objects:
            return pixmap
        annotated = QPixmap(pixmap)
        painter = QPainter(annotated)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = pixmap.width(), pixmap.height()
        colors = ["#ff4040", "#40d8ff", "#ffcc00", "#4ec9b0", "#ce9178", "#d670d6"]

        for i, obj in enumerate(objects[:30]):  # 最多画 30 个
            name = obj.get("name", "")
            bbox = obj.get("bbox", [0, 0, 0, 0])
            if len(bbox) != 4:
                continue

            x1, y1, x2, y2 = bbox
            px1 = int(x1 / 1000 * w)
            py1 = int(y1 / 1000 * h)
            px2 = int(x2 / 1000 * w)
            py2 = int(y2 / 1000 * h)

            color = QColor(colors[i % len(colors)])
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.drawRect(px1, py1, px2 - px1, py2 - py1)

            # 标签背景
            text = name[:12]
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(text) + 8
            text_h = fm.height() + 4
            painter.fillRect(px1, max(0, py1 - text_h), text_w, text_h, color)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            painter.drawText(px1 + 4, max(0, py1 - 4), text)

        painter.end()
        return annotated

    def _show_scene_image(self, title: str, image_path: Path, objects: list):
        """创建新标签页显示场景截图，并标注大模型识别出的对象 bbox。"""
        tab = QWidget()
        tab.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        label = QLabel(tab)
        pixmap = QPixmap(str(image_path.resolve()))
        if not pixmap.isNull():
            # 如果有对象，绘制 bbox
            if objects:
                pixmap = self._draw_objects_on_pixmap(pixmap, objects)
            label.setPixmap(
                pixmap.scaled(
                    960, 720,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            label.setText(f"图片加载失败\n{image_path}")
            label.setStyleSheet("color: #f44747; background-color: #111111;")
            LogManager().append(f"[SceneImage] 图片加载失败: {image_path}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        index = self.ui.tabWidget.addTab(tab, title)
        self.ui.tabWidget.setCurrentIndex(index)

    def do_start_execution(self):
        """开始执行：委托给 ExecutionEngine（全部在后台线程，不阻塞主界面）。"""
        if not (self.client and self.client.alive):
            self._set_status("状态: 请先连接设备")
            return

        self.btn_execute.setEnabled(False)
        self.btn_stop_execution.setEnabled(True)

        # 只传递 frame 引用（不复制），所有重活都在 ExecutionEngine 的后台线程中
        frame = self.video_widget._frame if self.video_widget else None
        self.execution_engine.start(frame)

    def do_stop_execution(self):
        """停止执行：委托给 ExecutionEngine。"""
        self.execution_engine.stop()
        self.btn_execute.setEnabled(True)
        self.btn_stop_execution.setEnabled(False)

