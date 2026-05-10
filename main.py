import re
import struct
import sys
import threading
import time
import json
import socket
from pathlib import Path

import scrcpy
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QButtonGroup, QToolButton,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QHBoxLayout, QTextEdit, QSizePolicy, QMenu, QMessageBox,
    QRadioButton, QComboBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import QTimer, QObject, Signal, Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont

from ui_main_window import Ui_MainWindow
from video_widget import VideoGLWidget
from log_manager import LogManager
from decision_engine import DecisionEngine
from execution_engine import ExecutionEngine
from scene_index import UnknownFolderProcessor


class SignalBridge(QObject):
    status_changed = Signal(str, str)
    buttons_changed = Signal(bool)
    decision_ready = Signal(dict)
    touch_feedback = Signal(object, int)
    events_changed = Signal()


class AnnotatedImageLabel(QLabel):
    def __init__(self, image_path: Path, title: str, touch: dict, yolo: dict | None = None, parent=None):
        super().__init__(parent)
        self._annotated_pixmap = self._build_pixmap(image_path, title, touch, yolo or {})
        self.setStyleSheet("background-color: #111111; color: #cccccc; padding: 6px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 220)
        self._update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._annotated_pixmap.isNull():
            return
        available = self.contentsRect().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        self.setPixmap(
            self._annotated_pixmap.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _build_pixmap(self, image_path: Path, title: str, touch: dict, yolo: dict) -> QPixmap:
        pixmap = QPixmap(str(image_path.resolve()))
        if pixmap.isNull():
            fallback = QPixmap(420, 120)
            fallback.fill(QColor("#1e1e1e"))
            painter = QPainter(fallback)
            painter.setPen(QColor("#f44747"))
            painter.drawText(12, 34, f"{title}: 图片加载失败")
            painter.end()
            return fallback

        annotated = QPixmap(pixmap)
        painter = QPainter(annotated)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Arial", 14))
        painter.setPen(QColor("#ff4040"))
        painter.drawText(14, 28, title)

        start, end = self._points_for_image(annotated, touch)
        if start and end:
            sx, sy = start
            ex, ey = end
            line_pen = QPen(QColor("#ffcc00"), 4)
            painter.setPen(line_pen)
            painter.drawLine(sx, sy, ex, ey)

            start_pen = QPen(QColor("#ff4040"), 4)
            painter.setPen(start_pen)
            painter.setBrush(QColor("#ff4040"))
            painter.drawEllipse(sx - 10, sy - 10, 20, 20)
            painter.drawText(sx + 12, sy - 8, "DOWN")

            end_pen = QPen(QColor("#40d8ff"), 4)
            painter.setPen(end_pen)
            painter.setBrush(QColor("#40d8ff"))
            painter.drawEllipse(ex - 10, ey - 10, 20, 20)
            painter.drawText(ex + 12, ey + 20, "UP")

        yolo_objects = yolo.get("objects") or []
        if not yolo_objects and yolo.get("bbox_xyxy"):
            yolo_objects = [yolo]
        for yolo_obj in yolo_objects:
            bbox = yolo_obj.get("bbox_xyxy")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            x1 = max(0, min(annotated.width() - 1, x1))
            y1 = max(0, min(annotated.height() - 1, y1))
            x2 = max(x1 + 1, min(annotated.width(), x2))
            y2 = max(y1 + 1, min(annotated.height(), y2))

            box_pen = QPen(QColor("#4ec9b0"), 4)
            painter.setPen(box_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

            label = yolo_obj.get("class_name") or "yolo"
            painter.setFont(QFont("Microsoft YaHei", 14))
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(label) + 12
            text_h = fm.height() + 6
            label_y = max(0, y1 - text_h)
            painter.fillRect(x1, label_y, text_w, text_h, QColor("#107c5d"))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(x1 + 6, label_y + text_h - 7, label)

        painter.end()
        return annotated

    def _points_for_image(self, pixmap: QPixmap, touch: dict):
        width = pixmap.width()
        height = pixmap.height()
        if not touch:
            return None, None

        if "frame_start" in touch and "frame_end" in touch:
            start = touch["frame_start"]
            end = touch["frame_end"]
        else:
            start = touch.get("start")
            end = touch.get("end")

        if not start or not end:
            return None, None

        sx = max(0, min(width - 1, int(start["x"])))
        sy = max(0, min(height - 1, int(start["y"])))
        ex = max(0, min(width - 1, int(end["x"])))
        ey = max(0, min(height - 1, int(end["y"])))
        return (sx, sy), (ex, ey)


class ImageThumbnailLabel(QLabel):
    def __init__(self, image_path: Path, title: str, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._selected = False
        self.setFixedSize(144, 92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(title)
        self._apply_style()
        pixmap = QPixmap(str(image_path.resolve()))
        if pixmap.isNull():
            self.setText(title)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.setPixmap(
                pixmap.scaled(
                    140,
                    88,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(
                "QLabel { background-color: #17324d; border: 2px solid #40d8ff; "
                "color: #ffffff; padding: 1px; }"
            )
        else:
            self.setStyleSheet(
                "QLabel { background-color: #111111; border: 1px solid #333333; "
                "color: #cccccc; padding: 2px; }"
                "QLabel:hover { border: 1px solid #666666; }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.client = None
        self._device_resolution = None
        self._adb_device = None
        self._touch_start = None
        self._touch_last = None
        self._touch_frame_start = None
        self._touch_frame_last = None
        self._touch_time = 0.0
        self._op_dir_for_touch = None
        self._screenshot_lock = threading.Lock()
        self._getevent_thread = None
        self._getevent_stop = threading.Event()
        self._getevent_conn = None
        self._getevent_generation = 0
        self._physical_touch_start = None
        self._physical_touch_last = None
        self._physical_touch_frame_start = None
        self._physical_touch_frame_last = None
        self._physical_touch_time = 0.0
        self._physical_op_dir = None
        self._projection_control_enabled = False

        # 录制相关
        self._video_writer = None
        self._record_fps = 20
        self._record_path = None

        # 帧刷新：把 scrcpy 回调中的处理移到主线程 QTimer，避免阻塞解码线程
        self._pending_frame = None
        self._frame_flush_count = 0
        self._frame_flush_last_time = time.time()
        self._scrcpy_max_width = 1280
        self._scrcpy_max_fps = 60
        self._scrcpy_bitrate = 6000000
        self._frame_flush_timer = QTimer(self)
        self._frame_flush_timer.timeout.connect(self._flush_pending_frame)
        self._frame_flush_timer.start(16)  # 约 60fps

        # unknown 文件夹后台处理器（独立于 ExecutionEngine，程序启动即运行）
        self._unknown_processor = UnknownFolderProcessor(interval=5)
        self._unknown_processor.start()
        self._event_unknown_stop = threading.Event()
        self._event_unknown_thread = None

        # 自动化决策引擎
        self.decision_engine = DecisionEngine()
        self.decision_panel = None
        self.edit_goal = None
        self.lbl_decision_result = None
        self.btn_auto_run = None
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self.do_auto_step)

        # 执行引擎（不阻塞主界面）
        self.execution_engine = ExecutionEngine()
        self.execution_engine.status_changed.connect(self._update_status_ui)
        self.execution_engine.task_added.connect(self._on_task_added)
        self.execution_engine.task_subtask_added.connect(self._on_task_subtask_added)
        self.execution_engine.task_cleared.connect(self._on_task_cleared)
        self.execution_engine.task_done.connect(self._on_task_done)
        self.execution_engine.scene_image_ready.connect(self._show_scene_image)

        # 把 .ui 里的 videoWidget 替换为 VideoGLWidget
        old_widget = self.findChild(QWidget, "videoWidget")
        self.video_widget = None
        if old_widget:
            parent = old_widget.parentWidget()
            layout = old_widget.parentWidget().layout()
            # 找到 old_widget 在 layout 中的索引
            idx = -1
            if layout:
                for i in range(layout.count()):
                    if layout.itemAt(i).widget() is old_widget:
                        idx = i
                        break
            self.video_widget = VideoGLWidget(parent)
            self.video_widget.setObjectName("videoWidget")
            if self._projection_control_enabled:
                self.video_widget.on_touch = self._on_touch
                self.video_widget.on_scroll = self._on_scroll
            if layout and idx >= 0:
                layout.replaceWidget(old_widget, self.video_widget)
            old_widget.deleteLater()

        # video_widget 创建完成后连接场景名字叠加信号
        if self.video_widget:
            self.execution_engine.scene_name_changed.connect(self.video_widget.set_overlay_text)

        # 跨线程信号桥（必须在 setupUi 之后创建）
        self._bridge = SignalBridge(self)
        self._bridge.status_changed.connect(self._update_status_ui)
        self._bridge.buttons_changed.connect(self._update_connect_buttons_slot)
        self._bridge.decision_ready.connect(self._execute_decision_slot)
        self._bridge.touch_feedback.connect(self._show_touch_feedback_slot)
        self._bridge.events_changed.connect(self._refresh_events)
        self._event_unknown_thread = threading.Thread(target=self._event_unknown_loop, daemon=True)
        self._event_unknown_thread.start()
        LogManager().append("[EventUnknown] 事件处理线程已启动")

        # 设置 splitter 比例
        splitter = self.findChild(QSplitter, "centralwidget")
        if splitter:
            splitter.setSizes([600, 150])

        top_splitter = self.findChild(QSplitter, "topPanel")
        if top_splitter:
            top_splitter.setSizes([40, 260, 1000])
        self.ui.tabWidget.tabCloseRequested.connect(self._close_tab)

        # 活动栏按钮单选组
        group = QButtonGroup(self)
        group.setExclusive(True)
        for name in ["btnAndroid", "btnSearch", "btnGit", "btnRun", "btnExt"]:
            btn = self.findChild(QToolButton, name)
            if btn:
                group.addButton(btn)

        btn_android = self.findChild(QToolButton, "btnAndroid")
        if btn_android:
            btn_android.setChecked(True)

        # 功能面板显示/隐藏
        self.side_panel = self.findChild(QWidget, "sidePanel")
        self.file_panel = None
        self.list_screenshot_folders = None
        self.execution_panel = None
        self._setup_file_panel()
        self._setup_audit_panel()
        self._setup_execution_panel()

        # 修改 btnGit 为"执行"
        btn_git = self.findChild(QToolButton, "btnGit")
        if btn_git:
            btn_git.setText("▶")
            btn_git.setToolTip("执行")

        # 修改 btnRun 为"审核"
        btn_run = self.findChild(QToolButton, "btnRun")
        if btn_run:
            btn_run.setText("审")
            btn_run.setToolTip("审核")

        # 修改 btnSearch 为"事件"
        btn_search = self.findChild(QToolButton, "btnSearch")
        if btn_search:
            btn_search.setText("事")
            btn_search.setToolTip("事件")

        # 隐藏 btnExt
        btn_ext = self.findChild(QToolButton, "btnExt")
        if btn_ext:
            btn_ext.setVisible(False)

        def on_activity_clicked(btn):
            if not self.side_panel:
                return
            name = btn.objectName()
            self.side_panel.setVisible(name in ("btnAndroid", "btnSearch", "btnRun", "btnGit"))
            if self.ui.tabConnect:
                self.ui.tabConnect.setVisible(name == "btnAndroid")
            if self.file_panel:
                self.file_panel.setVisible(name == "btnSearch")
            if self.audit_panel:
                self.audit_panel.setVisible(name == "btnRun")
            if self.execution_panel:
                self.execution_panel.setVisible(name == "btnGit")
            if name == "btnSearch":
                self._refresh_events()

        for name in ["btnAndroid", "btnSearch", "btnGit", "btnRun", "btnExt"]:
            btn = self.findChild(QToolButton, name)
            if btn:
                btn.clicked.connect(lambda checked, b=btn: on_activity_clicked(b))

        if self.side_panel:
            self.side_panel.setVisible(True)
        if self.file_panel:
            self.file_panel.setVisible(False)
        if self.audit_panel:
            self.audit_panel.setVisible(False)
        if self.execution_panel:
            self.execution_panel.setVisible(False)

        # UI 控件引用
        self.lbl_status = self.findChild(QLabel, "lblStatus")
        self.edit_ip = self.findChild(QLineEdit, "editIp")
        self.edit_port = self.findChild(QLineEdit, "editPort")
        self.list_adb = self.findChild(QListWidget, "listAdbDevices")
        self.btn_ip = self.findChild(QPushButton, "btnIpConnect")
        self.btn_adb = self.findChild(QPushButton, "btnAdbConnect")

        # 连接按钮
        if self.btn_ip:
            self.btn_ip.clicked.connect(self.do_ip_connect)

        if self.btn_adb:
            self.btn_adb.clicked.connect(self.do_adb_connect)

        btn_refresh = self.findChild(QPushButton, "btnRefreshAdb")
        if btn_refresh:
            btn_refresh.clicked.connect(self.do_refresh_adb)

        btn_auto_ip = self.findChild(QPushButton, "btnAutoIp")
        if btn_auto_ip:
            btn_auto_ip.clicked.connect(self.do_auto_ip)

        # 清除按钮
        self.ui.btnClear.clicked.connect(self._clear_log)

        # 日志定时刷新
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._flush_log)
        self.log_timer.start(50)

        # 录制相关变量已迁移到 ExecutionEngine

        # 编辑菜单 - 清库
        self.ui.menuEdit = QMenu("编辑(&E)", self)
        self.ui.actionClearDB = QAction("清库", self)
        self.ui.actionClearDB.triggered.connect(self._clear_database)
        self.ui.menuEdit.addAction(self.ui.actionClearDB)
        self.ui.menubar.addAction(self.ui.menuEdit.menuAction())

        # 退出
        self.ui.actionExit.triggered.connect(self.close)

    def _setup_file_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.file_panel = QWidget(self.side_panel)
        self.file_panel.setObjectName("filePanel")
        panel_layout = QVBoxLayout(self.file_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("事件队列")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        refresh_btn = QPushButton("刷新事件")
        refresh_btn.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        refresh_btn.clicked.connect(self._refresh_events)
        panel_layout.addWidget(refresh_btn)

        self.list_events = QListWidget(self.file_panel)
        self.list_events.setObjectName("listEvents")
        self.list_events.setStyleSheet(
            "QListWidget { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 4px; }"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background-color: #0e639c; color: white; }"
            "QListWidget::item:hover { background-color: #2a2d2e; }"
        )
        self.list_events.itemDoubleClicked.connect(self._open_event_tab)
        panel_layout.addWidget(self.list_events)

        layout.insertWidget(1, self.file_panel)
        self.file_panel.setVisible(False)
        self._refresh_events()

    def _setup_audit_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.audit_panel = QWidget(self.side_panel)
        self.audit_panel.setObjectName("auditPanel")
        panel_layout = QVBoxLayout(self.audit_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("场景审核")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        # 审核状态过滤 radio button（互斥单选）
        filter_row = QHBoxLayout()
        self.rb_audit_group = QButtonGroup(self)
        self.rb_audit_group.setExclusive(True)
        self.rb_unreviewed = QRadioButton("未审核")
        self.rb_unreviewed.setChecked(True)
        self.rb_unreviewed.setStyleSheet("color: #cccccc;")
        self.rb_unreviewed.toggled.connect(self._refresh_audit_list)
        self.rb_audit_group.addButton(self.rb_unreviewed)
        filter_row.addWidget(self.rb_unreviewed)
        self.rb_approved = QRadioButton("审核通过")
        self.rb_approved.setStyleSheet("color: #cccccc;")
        self.rb_approved.toggled.connect(self._refresh_audit_list)
        self.rb_audit_group.addButton(self.rb_approved)
        filter_row.addWidget(self.rb_approved)
        filter_row.addStretch(1)
        panel_layout.addLayout(filter_row)

        btn_refresh = QPushButton("刷新列表", self.audit_panel)
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._refresh_audit_list)
        panel_layout.addWidget(btn_refresh)

        self.audit_list = QTreeWidget(self.audit_panel)
        self.audit_list.setObjectName("auditList")
        self.audit_list.setHeaderLabels(["场景", "类型", "命中", "模型", "状态", "创建时间"])
        self.audit_list.setStyleSheet(
            "QTreeWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; padding: 4px; }"
            "QTreeWidget::item { padding: 4px; border-bottom: 1px solid #333333; }"
            "QTreeWidget::item:selected { background-color: #0e639c; color: white; }"
            "QTreeWidget::item:hover { background-color: #2a2d2e; }"
        )
        self.audit_list.itemClicked.connect(self._open_audit_scene_tab)
        self.audit_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.audit_list.customContextMenuRequested.connect(self._show_audit_context_menu)
        panel_layout.addWidget(self.audit_list, 1)

        layout.insertWidget(2, self.audit_panel)
        self.audit_panel.setVisible(False)

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

    # ------------------------------------------------------------------
    # 执行引擎信号槽
    # ------------------------------------------------------------------
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
        """为任务项启动秒表计时器，每秒更新文本。"""
        import time
        if not hasattr(self, '_task_timers'):
            self._task_timers = {}
        start_time = time.time()
        timer = QTimer(self)
        timer.setInterval(1000)

        def _tick():
            elapsed = int(time.time() - start_time)
            item.setText(0, f"{base_text} ({elapsed}s)")

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

    def _refresh_events(self):
        if self.list_events is None:
            return
        self.list_events.clear()
        added = 0
        try:
            root = Path("screenshots")
            if root.exists():
                physical_folders = []
                event_roots = [root, root / "event_unknown", root / "event_review"]
                for event_root in event_roots:
                    if not event_root.exists():
                        continue
                    physical_folders.extend(
                        p for p in event_root.iterdir()
                        if p.is_dir() and p.name.startswith("physical_") and (p / "index.json").exists()
                    )
                physical_folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for folder in physical_folders:
                    try:
                        data = json.loads((folder / "index.json").read_text(encoding="utf-8"))
                    except Exception:
                        data = {}
                    action_type = data.get("action_type", "physical")
                    status = data.get("status", folder.parent.name if folder.parent != root else "")
                    status_text = {
                        "raw_captured": "待处理",
                        "processing": "处理中",
                        "review_pending": "已处理",
                        "review_approved": "已审核",
                        "needs_model_or_manual": "待人工",
                        "event_unknown": "待处理",
                        "event_review": "已处理",
                    }.get(status, status or "未知")
                    yolo_state = data.get("yolo", {}).get("status")
                    obj_count = len(data.get("yolo", {}).get("objects") or [])
                    if obj_count:
                        mark = f"{obj_count}框"
                    elif data.get("yolo", {}).get("bbox_xyxy"):
                        mark = "1框"
                    elif yolo_state == "waiting_for_label":
                        mark = "无框"
                    else:
                        mark = "-"
                    touch = data.get("touch", {})
                    start = touch.get("start", {})
                    item = QListWidgetItem(
                        f"{action_type} [{status_text}/{mark}]  ({start.get('x', '-')},{start.get('y', '-')})  {folder.name}"
                    )
                    item.setData(256, {"type": "physical_folder", "folder": str(folder)})
                    self.list_events.addItem(item)
                    added += 1

            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            if not db_path.exists():
                if added:
                    return
                self.list_events.addItem("暂无事件数据")
                return
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, index_no, x, y, timestamp_ms,
                       before_image, after_300ms_image, after_800ms_image
                FROM click_event
                ORDER BY timestamp_ms DESC
                """
            )
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                if added:
                    return
                self.list_events.addItem("暂无事件记录")
                return

            for row in rows:
                row_id, session_id, idx, x, y, ts, before_img, after_300, after_800 = row
                from datetime import datetime
                dt = datetime.fromtimestamp(ts / 1000).strftime("%m-%d %H:%M:%S")
                text = f"{session_id} #{idx:03d}  ({x},{y})  {dt}"
                item = QListWidgetItem(text)
                item.setData(256, {
                    "id": row_id,
                    "session_id": session_id,
                    "index_no": idx,
                    "x": x,
                    "y": y,
                    "before_image": before_img,
                    "after_300ms_image": after_300,
                    "after_800ms_image": after_800,
                })
                self.list_events.addItem(item)
        except Exception as e:
            LogManager().append(f"[Event] 刷新事件列表失败: {e}")
            self.list_events.addItem(f"刷新失败: {e}")

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
        layout.addStretch(1)
        outer_layout.addWidget(content)

        tab_idx = self.ui.tabWidget.indexOf(event_tab)
        self.ui.tabWidget.setCurrentIndex(tab_idx)

    def _get_or_create_single_event_tab(self) -> tuple[QWidget, QVBoxLayout]:
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
            if outer_layout.count() > 0:
                old_content = outer_layout.itemAt(0).widget()
                if old_content:
                    old_content.deleteLater()
        return event_tab, outer_layout

    def _open_physical_event_tab(self, folder: Path):
        if not folder.exists() or not folder.is_dir():
            return

        event_tab, outer_layout = self._get_or_create_single_event_tab()
        content = self._build_screenshot_stats_tab(folder)
        outer_layout.addWidget(content)
        self.ui.tabWidget.setCurrentIndex(self.ui.tabWidget.indexOf(event_tab))

    def _refresh_screenshot_folders(self):
        if self.list_screenshot_folders is None:
            return
        self.list_screenshot_folders.clear()
        root = Path("screenshots")
        root.mkdir(exist_ok=True)
        # 只显示用户主动触发的操作目录，过滤掉场景识别内部目录
        valid_prefixes = ("op_", "auto_", "ocr_")
        folders = [
            p for p in root.iterdir()
            if p.is_dir() and p.name.startswith(valid_prefixes)
        ]
        folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if not folders:
            self.list_screenshot_folders.addItem("screenshots 下面还没有文件夹")
            return

        for folder in folders:
            png_count = len(list(folder.glob("*.png")))
            has_index = (folder / "index.json").exists()
            suffix = f"  ({png_count} png"
            if has_index:
                suffix += ", index"
            suffix += ")"
            item = QListWidgetItem(folder.name + suffix)
            item.setData(256, str(folder))
            self.list_screenshot_folders.addItem(item)

    def _open_screenshot_folder_tab(self, item: QListWidgetItem):
        folder_text = item.data(256)
        if not folder_text:
            return
        self._open_screenshot_folder_path(Path(folder_text))

    def _open_screenshot_folder_path(self, folder: Path):
        if not folder.exists() or not folder.is_dir():
            return

        tab_key = str(folder.resolve())
        for index in range(self.ui.tabWidget.count()):
            widget = self.ui.tabWidget.widget(index)
            if widget.property("folder_path") == tab_key:
                self.ui.tabWidget.setCurrentIndex(index)
                return

        tab = self._build_screenshot_stats_tab(folder)
        tab.setProperty("folder_path", tab_key)
        index = self.ui.tabWidget.addTab(tab, f"统计 {folder.name[-10:]}")
        self.ui.tabWidget.setCurrentIndex(index)

    def _build_screenshot_stats_tab(self, folder: Path) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel(str(folder))
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 4px;")
        layout.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(8)
        layout.addLayout(body, 1)

        index_path = folder / "index.json"
        data = {}
        json_text = "No index.json"
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                # 只显示操作信息，过滤掉场景识别/hash相关内容
                display_data = {k: v for k, v in data.items() if k != "scene_index"}
                json_text = json.dumps(display_data, ensure_ascii=False, indent=2)
            except Exception as e:
                json_text = f"index.json read failed: {e}"

        touch = data.get("touch", {})
        yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
        image_names = []
        images = data.get("images", {})
        for label in ["before", "pressed", "after"]:
            name = images.get(label) or f"{label}.png"
            if name and (folder / name).exists():
                image_names.append((label, name))

        used_names = {name for _, name in image_names}
        for path in sorted(folder.glob("*.png")):
            if path.name.startswith("compare_") or path.name.startswith("diff_"):
                continue
            if path.name not in used_names:
                image_names.append((path.stem, path.name))
                used_names.add(path.name)

        left_panel = QWidget(page)
        left_panel.setFixedWidth(184)
        left_panel.setStyleSheet("background-color: #0f0f0f; border: 1px solid #333333;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 8, 8, 8)

        json_view = QTextEdit(left_panel)
        json_view.setReadOnly(True)
        json_view.setFixedHeight(170)
        json_view.setPlainText(json_text)
        json_view.setStyleSheet(
            "QTextEdit { background-color: #111111; color: #d4d4d4; "
            "border: 1px solid #333333; font-family: Consolas, monospace; font-size: 11px; }"
        )
        left_layout.addWidget(json_view)

        detail_holder = QWidget(page)
        detail_layout = QVBoxLayout(detail_holder)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)
        placeholder = QLabel("Select an image")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("background-color: #111111; color: #888888; border: 1px solid #333333;")
        placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout.addWidget(placeholder)
        current_detail = {"widget": placeholder}
        current_thumb = {"widget": None}

        def set_detail(label, name, thumb=None):
            if current_thumb["widget"] is not None:
                current_thumb["widget"].set_selected(False)
            if thumb is not None:
                thumb.set_selected(True)
                current_thumb["widget"] = thumb
            old = current_detail["widget"]
            replacement = AnnotatedImageLabel(folder / name, label, touch, yolo, detail_holder)
            detail_layout.replaceWidget(old, replacement)
            old.deleteLater()
            current_detail["widget"] = replacement

        if not image_names:
            empty = QLabel("No PNG images")
            empty.setStyleSheet("color: #888888; padding: 12px;")
            left_layout.addWidget(empty)
        else:
            thumbs = []
            for label, name in image_names:
                thumb = ImageThumbnailLabel(
                    folder / name,
                    label,
                    None,
                    left_panel,
                )
                thumb._on_click = lambda l=label, n=name, t=thumb: set_detail(l, n, t)
                thumbs.append((thumb, label, name))
                left_layout.addWidget(thumb)

        left_layout.addStretch(1)
        body.addWidget(left_panel, 0)
        body.addWidget(detail_holder, 1)

        if image_names:
            first_thumb, first_label, first_name = thumbs[0]
            QTimer.singleShot(0, lambda: set_detail(first_label, first_name, first_thumb))
        return page

    def _close_tab(self, index: int):
        widget = self.ui.tabWidget.widget(index)
        if widget is None:
            return
        if widget is self.ui.tab:
            self.ui.tabWidget.setCurrentIndex(index)
            return
        self.ui.tabWidget.removeTab(index)
        widget.deleteLater()

    def _update_connect_buttons(self, connected: bool):
        """发射信号，让主线程更新连接按钮文字"""
        self._bridge.buttons_changed.emit(connected)

    def _update_connect_buttons_slot(self, connected: bool):
        """槽函数：在主线程更新按钮文字"""
        if self.btn_ip:
            self.btn_ip.setText("断开连接" if connected else "IP 连接")
        if self.btn_adb:
            self.btn_adb.setText("断开连接" if connected else "连接选中设备")

    def disconnect_device(self):
        self._stop_getevent_listener()
        if self.execution_engine.is_running():
            self.execution_engine.stop()
        if self.client:
            self.client.stop()
            self.client = None
        self._update_connect_buttons(False)
        self._set_status("状态: 已断开")

    def do_ip_connect(self):
        if self.client and self.client.alive:
            self.disconnect_device()
            return
        ip = self.edit_ip.text().strip() if self.edit_ip else ""
        port = self.edit_port.text().strip() if self.edit_port else "5555"
        if not ip:
            self._set_status("状态: 请输入 IP 地址")
            return
        device = f"{ip}:{port}"
        self._set_status(f"状态: 正在连接 {device}...")
        self.connect_device(device)

    def do_refresh_adb(self):
        from adbutils import adb
        try:
            devices = adb.device_list()
            if self.list_adb:
                self.list_adb.clear()
                for d in devices:
                    # 容错：某些设备获取 model 可能失败
                    try:
                        model = d.prop.model
                    except Exception:
                        model = "未知型号"
                    item = QListWidgetItem(f"{d.serial}  ({model})")
                    item.setData(256, d.serial)  # 存储 serial
                    self.list_adb.addItem(item)
            self._set_status(f"状态: 发现 {len(devices)} 个设备")
        except Exception as e:
            self._set_status(f"状态: 刷新失败 - {e}")

    def do_adb_connect(self):
        if self.client and self.client.alive:
            self.disconnect_device()
            return
        device_serial = None
        if self.list_adb:
            item = self.list_adb.currentItem()
            if item:
                device_serial = item.data(256)
            elif self.list_adb.count() > 0:
                self.list_adb.setCurrentRow(0)
                device_serial = self.list_adb.item(0).data(256)
        if not device_serial:
            self._set_status("状态: 请先刷新并选择设备")
            return
        self._set_status(f"状态: 正在连接 {device_serial}...")
        self.connect_device(device_serial)

    def _get_device_resolution(self, device_serial: str):
        """通过 adb 获取设备真实分辨率，绕过 scrcpy 库的协议解析 bug"""
        try:
            from adbutils import adb
            d = adb.device(serial=device_serial)
            # 先尝试 wm size
            output = d.shell("wm size")
            LogManager().append(f"[ADB] wm size output: {output.strip()}")
            m = re.search(r'(\d+)x(\d+)', output)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                LogManager().append(f"[ADB] parsed resolution from wm size: ({w}, {h})")
                return (w, h)
            # fallback: dumpsys
            output = d.shell("dumpsys window displays | grep -E 'init|DisplayDeviceInfo'")
            m = re.search(r'(\d+)\s*x\s*(\d+)', output)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                LogManager().append(f"[ADB] parsed resolution from dumpsys: ({w}, {h})")
                return (w, h)
        except Exception as e:
            LogManager().append(f"[ADB] get resolution failed: {e}")
        return None

    def connect_device(self, device):
        if self.client:
            self.client.stop()
            self.client = None

        # 清理设备上可能残留的 scrcpy server，避免连到旧的乱序 socket
        try:
            from adbutils import adb
            d = adb.device(serial=device)
            d.shell("pkill -f 'app_process.*scrcpy' 2>/dev/null || true")
        except Exception:
            pass

        # 通过 adb 直接获取设备真实分辨率
        self._device_resolution = self._get_device_resolution(device)

        def on_frame(frame):
            """scrcpy 回调线程：只做引用保存，零处理，零阻塞。"""
            if frame is not None:
                self._pending_frame = frame
                self._frame_flush_count += 1

        def on_init():
            # 优先使用 scrcpy 握手时的分辨率（和视频流方向 guaranteed 一致）
            cr = self.client.resolution
            LogManager().append(f"[Scrcpy] on_init, handshake resolution: {cr}")
            if cr and len(cr) == 2 and all(isinstance(v, int) and 0 < v < 10000 for v in cr):
                self._device_resolution = cr
                LogManager().append(f"[Scrcpy] using handshake resolution: {cr}")
            elif self._device_resolution is None:
                self._device_resolution = self._get_device_resolution(device)
                LogManager().append(f"[Scrcpy] fallback to adb resolution: {self._device_resolution}")
            else:
                LogManager().append(f"[Scrcpy] using pre-fetched adb resolution: {self._device_resolution}")
            self._start_getevent_listener(device)
            self._update_connect_buttons(True)
            self._set_status("状态: 已连接")

        def on_disconnect():
            self._stop_getevent_listener()
            self._update_connect_buttons(False)
            self._set_status("状态: 已断开")

        def run():
            try:
                self.client = scrcpy.Client(
                    device=device,
                    max_width=self._scrcpy_max_width,
                    bitrate=self._scrcpy_bitrate,
                    max_fps=self._scrcpy_max_fps,
                    block_frame=True,
                )
                self._adb_device = self.client.device
                self.client.add_listener(scrcpy.EVENT_INIT, on_init)
                self.client.add_listener(scrcpy.EVENT_FRAME, on_frame)
                self.client.add_listener(scrcpy.EVENT_DISCONNECT, on_disconnect)
                self.client.start(daemon_threaded=True)
            except Exception as e:
                import traceback
                self._update_connect_buttons(False)
                self._set_status(f"状态: 连接失败 - {e}")
                LogManager().append(f"[ERROR] 连接失败:\n{traceback.format_exc()}")

        threading.Thread(target=run, daemon=True).start()

    def _flush_pending_frame(self):
        """主线程 QTimer：消费最新帧，做 BGR→RGB、显示、录制、FPS 统计。"""
        frame = self._pending_frame
        if frame is None:
            return
        self._pending_frame = None
        if self.video_widget is None:
            return

        import numpy as np
        rgb = np.ascontiguousarray(frame[..., ::-1])
        try:
            self.video_widget.set_frame(rgb)
        except RuntimeError:
            pass

        # 录制写入
        self.execution_engine.write_frame(frame, rgb)

        # FPS 统计
        now = time.time()
        if now - self._frame_flush_last_time >= 1.0:
            fps = self._frame_flush_count
            self._frame_flush_count = 0
            self._frame_flush_last_time = now
            fh, fw = frame.shape[:2]
            self._set_status(f"状态: 已连接 | FPS: {fps} | Frame: {fw}x{fh}", log=False)

    def _clear_database(self):
        """清理数据库、game_agent_data、screenshots 的所有内容。"""
        reply = QMessageBox.question(
            self, "确认清库",
            "确定要清库吗？\n\n这将删除所有截图、事件记录和场景数据，不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # 先停止 unknown 处理器，释放数据库和文件句柄
            self._unknown_processor.stop()
            import time
            time.sleep(0.5)

            # 1. 清理 screenshots
            screenshot_dir = Path("screenshots")
            if screenshot_dir.exists():
                for item in screenshot_dir.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        import shutil
                        shutil.rmtree(item)

            # 2. 清理 game_agent_data
            game_data_dir = Path("game_agent_data")
            if game_data_dir.exists():
                import shutil
                shutil.rmtree(game_data_dir)

            # 3. 重置 AgentDataManager 单例，让 ExecutionEngine 重新初始化数据库
            from agent_data import AgentDataManager
            AgentDataManager._instance = None
            self.execution_engine.dm = AgentDataManager()

            # 4. 重新创建 UnknownFolderProcessor（确保 SceneIndex 也是新的）
            self._unknown_processor = UnknownFolderProcessor(interval=5)
            self._unknown_processor.start()

            # 5. 刷新 UI
            self._refresh_events()
            self._refresh_audit_list()

            self._set_status("状态: 清库完成")
            LogManager().append("[ClearDB] 数据库已清空")
        except Exception as e:
            LogManager().append(f"[ClearDB] 清库失败: {e}")
            self._set_status(f"状态: 清库失败 - {e}")

    def do_auto_ip(self):
        import re
        from adbutils import adb

        try:
            device = adb.device()  # 获取第一个设备
            # 尝试多种方式获取 IP
            output = device.shell("ip addr show wlan0")
            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/', output)
            if not match:
                output = device.shell("ifconfig wlan0")
                match = re.search(r'addr:(\d+\.\d+\.\d+\.\d+)', output)
            if not match:
                output = device.shell("ip route")
                match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', output)

            if match:
                ip = match.group(1)
                edit_ip = self.findChild(QLineEdit, "editIp")
                if edit_ip:
                    edit_ip.setText(ip)
                self._set_status(f"状态: 已自动获取 IP {ip}")
            else:
                self._set_status("状态: 无法获取 IP，请手动输入")
        except Exception as e:
            self._set_status(f"状态: 获取 IP 失败 - {e}")

    def _set_status(self, text, log=True):
        # 根据状态文字判断颜色
        if "连接失败" in text or "失败" in text or "错误" in text:
            color = "#f44747"  # 红色
        elif "已连接" in text:
            color = "#4ec9b0"  # 绿色
        elif "已断开" in text:
            color = "#ce9178"  # 橙色
        else:
            color = "#888888"  # 灰色

        # 发射信号，让主线程更新状态栏
        self._bridge.status_changed.emit(text, color)
        if log:
            LogManager().append(text)

    def _show_touch_feedback_slot(self, points, hold_ms: int):
        if self.video_widget:
            self.video_widget.show_touch_feedback(points, hold_ms=hold_ms)

    def _update_status_ui(self, text, color):
        # 状态栏只显示连接状态，防止 FPS 被识别/执行等临时信息覆盖
        if not text.startswith("状态:"):
            return
        if self.lbl_status:
            self.lbl_status.setText(text)
            self.lbl_status.setStyleSheet(f"color: {color}; padding: 5px 10px;")

    def _flush_log(self):
        logs = LogManager().get_and_clear()
        if logs and self.ui.textOutput:
            self.ui.textOutput.append("\n".join(logs))

    def _clear_log(self):
        LogManager().clear()
        self.ui.textOutput.clear()

    def _map_frame_to_device(self, frame_x: int, frame_y: int):
        """把帧坐标映射到设备屏幕坐标，根据帧宽高比自动判断横竖屏"""
        frame = self.video_widget._frame
        if frame is None or self._device_resolution is None:
            LogManager().append(f"[TouchMap] skip: frame={frame is not None}, resolution={self._device_resolution}")
            return None, None
        fh, fw = frame.shape[:2]
        dw, dh = self._device_resolution  # wm size 返回的固定值，如 (900, 1600)

        # 视频帧宽高比反映设备当前方向
        if fw > fh:
            # 横屏：实际宽 = max(dw,dh)，高 = min(dw,dh)
            screen_w = max(dw, dh)
            screen_h = min(dw, dh)
            orientation = "landscape"
        else:
            # 竖屏：实际宽 = min(dw,dh)，高 = max(dw,dh)
            screen_w = min(dw, dh)
            screen_h = max(dw, dh)
            orientation = "portrait"

        x = int(frame_x * screen_w / fw)
        y = int(frame_y * screen_h / fh)
        x = max(0, min(x, screen_w - 1))
        y = max(0, min(y, screen_h - 1))
        LogManager().append(
            f"[TouchMap] frame({fw}x{fh}) -> device({screen_w}x{screen_h}, {orientation}) | "
            f"input({frame_x},{frame_y}) -> output({x},{y})"
        )
        return x, y

    def _map_device_to_frame(self, device_x: int, device_y: int):
        frame = self.video_widget._frame if self.video_widget else None
        if frame is None or self._device_resolution is None:
            return None, None

        fh, fw = frame.shape[:2]
        dw, dh = self._device_resolution
        if fw > fh:
            screen_w = max(dw, dh)
            screen_h = min(dw, dh)
        else:
            screen_w = min(dw, dh)
            screen_h = max(dw, dh)

        fx = int(device_x * fw / max(1, screen_w))
        fy = int(device_y * fh / max(1, screen_h))
        fx = max(0, min(fx, fw - 1))
        fy = max(0, min(fy, fh - 1))
        return fx, fy

    @staticmethod
    def _parse_abs_range(line: str):
        min_match = re.search(r"\bmin\s+(-?\d+)", line)
        max_match = re.search(r"\bmax\s+(-?\d+)", line)
        if not min_match or not max_match:
            return None
        return int(min_match.group(1)), int(max_match.group(1))

    def _get_touch_input_info(self, device):
        try:
            output = device.shell("getevent -lp", timeout=5)
        except Exception as e:
            LogManager().append(f"[GetEvent] getevent -lp failed: {e}")
            return None

        devices = {}
        current = None
        for line in output.splitlines():
            match = re.search(r"add device \d+:\s+(\S+)", line)
            if match:
                current = match.group(1)
                devices.setdefault(current, {})
                continue
            if not current:
                continue

            if "ABS_MT_POSITION_X" in line or re.search(r"\b0035\b", line):
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["x"] = parsed
                    devices[current]["mt_x"] = True
            elif "ABS_MT_POSITION_Y" in line or re.search(r"\b0036\b", line):
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["y"] = parsed
                    devices[current]["mt_y"] = True
            elif "ABS_X" in line and "x" not in devices[current]:
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["x"] = parsed
            elif "ABS_Y" in line and "y" not in devices[current]:
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["y"] = parsed

        for path, info in devices.items():
            if "x" in info and "y" in info and info.get("mt_x") and info.get("mt_y"):
                LogManager().append(f"[GetEvent] touch device: {path}, x={info['x']}, y={info['y']}")
                return path, info["x"][0], info["x"][1], info["y"][0], info["y"][1]

        for path, info in devices.items():
            if "x" in info and "y" in info:
                LogManager().append(f"[GetEvent] touch device: {path}, x={info['x']}, y={info['y']}")
                return path, info["x"][0], info["x"][1], info["y"][0], info["y"][1]

        LogManager().append("[GetEvent] no touch input device found")
        return None

    def _raw_touch_to_device(self, raw_x, raw_y, touch_info):
        if raw_x is None or raw_y is None or touch_info is None or self._device_resolution is None:
            return None, None

        _, min_x, max_x, min_y, max_y = touch_info
        frame = self.video_widget._frame if self.video_widget else None
        dw, dh = self._device_resolution
        landscape = frame is not None and frame.shape[1] > frame.shape[0]
        if landscape:
            screen_w = max(dw, dh)
            screen_h = min(dw, dh)
        else:
            screen_w = min(dw, dh)
            screen_h = max(dw, dh)

        nx = (raw_x - min_x) / max(1, max_x - min_x)
        ny = (raw_y - min_y) / max(1, max_y - min_y)
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))
        if landscape:
            # Touch panels usually keep portrait raw axes while scrcpy rotates the video.
            # Rotate raw coordinates clockwise into the current landscape screen space.
            x = int(ny * (screen_w - 1))
            y = int((1.0 - nx) * (screen_h - 1))
        else:
            x = int(nx * (screen_w - 1))
            y = int(ny * (screen_h - 1))
        return x, y

    def _start_getevent_listener(self, device_serial: str):
        self._stop_getevent_listener()
        self._getevent_stop = threading.Event()
        self._getevent_generation += 1
        generation = self._getevent_generation
        self._getevent_thread = threading.Thread(
            target=self._getevent_loop,
            args=(device_serial, self._getevent_stop, generation),
            daemon=True,
        )
        self._getevent_thread.start()

    def _stop_getevent_listener(self):
        self._getevent_generation += 1
        if hasattr(self, "_getevent_stop") and self._getevent_stop:
            self._getevent_stop.set()
        conn = getattr(self, "_getevent_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._getevent_conn = None

    @staticmethod
    def _getevent_value(line: str):
        parts = line.strip().split()
        if not parts:
            return None
        value = parts[-1]
        if value == "DOWN":
            return 1
        if value == "UP":
            return 0
        try:
            return int(value, 16)
        except ValueError:
            try:
                return int(value)
            except ValueError:
                return None

    def _getevent_loop(self, device_serial: str, stop_event: threading.Event, generation: int):
        try:
            from adbutils import adb
            from adbutils.errors import AdbTimeout

            device = adb.device(serial=device_serial)
            touch_info = self._get_touch_input_info(device)
            if not touch_info:
                return

            path = touch_info[0]
            conn = device.shell(["getevent", "-lt", path], stream=True, timeout=None, encoding=None)
            self._getevent_conn = conn
            try:
                conn.conn.settimeout(0.05)
            except Exception:
                pass
            LogManager().append(f"[GetEvent] listening physical touches on {path}")

            buffer = ""
            raw_x = None
            raw_y = None
            is_down = False
            active = False

            while not stop_event.is_set():
                if generation != self._getevent_generation:
                    break
                try:
                    chunk = conn.recv(128)
                except (socket.timeout, AdbTimeout):
                    continue
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")
                lines = buffer.splitlines()
                if buffer and not buffer.endswith(("\n", "\r")):
                    buffer = lines.pop() if lines else buffer
                else:
                    buffer = ""

                for line in lines:
                    value = self._getevent_value(line)
                    if value is None:
                        continue

                    if "ABS_MT_POSITION_X" in line or re.search(r"\b0035\b", line):
                        raw_x = value
                    elif "ABS_MT_POSITION_Y" in line or re.search(r"\b0036\b", line):
                        raw_y = value
                    elif "BTN_TOUCH" in line or re.search(r"\b014a\b", line):
                        is_down = value != 0
                    elif "ABS_MT_TRACKING_ID" in line or re.search(r"\b0039\b", line):
                        is_down = value != 0xFFFFFFFF

                    if "SYN_REPORT" in line or re.search(r"\b0000\s+0000\b", line):
                        device_x, device_y = self._raw_touch_to_device(raw_x, raw_y, touch_info)
                        if device_x is None:
                            continue
                        if is_down and not active:
                            active = True
                            self._on_physical_touch(device_x, device_y, scrcpy.ACTION_DOWN)
                        elif is_down and active:
                            self._on_physical_touch(device_x, device_y, scrcpy.ACTION_MOVE)
                        elif not is_down and active:
                            active = False
                            self._on_physical_touch(device_x, device_y, scrcpy.ACTION_UP)
        except Exception as e:
            if not stop_event.is_set():
                LogManager().append(f"[GetEvent] listener stopped: {e}")
        finally:
            if generation == self._getevent_generation and getattr(self, "_getevent_conn", None) is not None:
                try:
                    self._getevent_conn.close()
                except Exception:
                    pass
                self._getevent_conn = None

    def _take_screenshot_sync(self, label: str, action_type: str = "", op_dir: Path = None) -> Path:
        """同步截取设备屏幕并保存到指定操作目录。调用者需确保在后台线程中执行"""
        if self._adb_device is None:
            return None
        try:
            import json
            from datetime import datetime
            now = datetime.now()
            ts = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]
            time_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            screenshot_dir = Path("screenshots")
            screenshot_dir.mkdir(exist_ok=True)

            if op_dir is None:
                op_dir = screenshot_dir / f"op_{ts}"
                op_dir.mkdir(exist_ok=True)

            local_path = op_dir / f"{label}.png"
            with self._screenshot_lock:
                img = self._adb_device.screenshot()
            if img:
                img.save(str(local_path))

            if label == "after":
                index_path = op_dir / "index.json"
                data = {
                    "time": time_str,
                    "action_type": action_type,
                    "before": "before.png",
                    "after": "after.png"
                }
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

            return op_dir
        except Exception:
            return None

    def _save_video_frame_sync(self, label: str, op_dir: Path) -> Path:
        """Save the latest scrcpy video frame as a PNG without waiting for adb screencap."""
        try:
            from PIL import Image

            frame = self.video_widget._frame if self.video_widget else None
            if frame is None:
                return None
            op_dir.mkdir(parents=True, exist_ok=True)
            local_path = op_dir / f"{label}.png"
            Image.fromarray(frame.copy()).save(str(local_path))
            return local_path
        except Exception as e:
            LogManager().append(f"[WARN] save frame failed: {e}")
            return None

    def _save_video_frame_async(self, label: str, op_dir: Path, frame=None) -> None:
        """Save a video frame in the background so input delivery is not blocked."""
        if frame is None:
            frame = self.video_widget._frame if self.video_widget else None
        if frame is None:
            return
        def _save():
            try:
                from PIL import Image

                op_dir.mkdir(parents=True, exist_ok=True)
                Image.fromarray(frame.copy()).save(str(op_dir / f"{label}.png"))
            except Exception as e:
                LogManager().append(f"[WARN] save frame failed: {e}")

        threading.Thread(target=_save, daemon=True).start()

    def _image_change_score(self, first_path: Path, second_path: Path, center=None) -> dict:
        try:
            from PIL import Image
            import numpy as np

            first = Image.open(first_path).convert("RGB")
            second = Image.open(second_path).convert("RGB").resize(first.size)

            def score(a, b):
                a = a.resize((160, 90))
                b = b.resize((160, 90))
                aa = np.asarray(a, dtype=np.int16)
                bb = np.asarray(b, dtype=np.int16)
                return round(float(np.mean(np.abs(aa - bb)) / 255.0), 6)

            result = {"global": score(first, second)}
            if center:
                x, y = center
                radius = 90
                left = max(0, int(x - radius))
                top = max(0, int(y - radius))
                right = min(first.width, int(x + radius))
                bottom = min(first.height, int(y + radius))
                if right > left and bottom > top:
                    result["local"] = score(
                        first.crop((left, top, right, bottom)),
                        second.crop((left, top, right, bottom)),
                    )
            return result
        except Exception as e:
            LogManager().append(f"[WARN] compare frames failed: {e}")
            return {}

    def _write_yolo_event_annotation(self, op_dir: Path, data: dict) -> dict:
        try:
            import shutil
            from PIL import Image
            from agent_data import GAME_DATA_DIR

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"error": "before image missing"}
            image_path = op_dir / before_name
            if not image_path.exists():
                return {"error": f"image not found: {image_path}"}

            with Image.open(image_path) as img:
                width, height = img.size

            touch = data.get("touch", {})
            start = touch.get("frame_start", {})
            end = touch.get("frame_end", start)
            sx, sy = int(start.get("x", 0)), int(start.get("y", 0))
            ex, ey = int(end.get("x", sx)), int(end.get("y", sy))

            click_target = data.get("click_target", {})
            if click_target.get("status") == "needs_model_or_manual":
                return {
                    "status": "waiting_for_label",
                    "reason": click_target.get("reason", "click target is not identified"),
                }
            target_bbox = click_target.get("bbox_xyxy")
            if target_bbox and len(target_bbox) == 4:
                x1, y1, x2, y2 = [int(v) for v in target_bbox]
            else:
                action_type = data.get("action_type", "")
                if "swipe" in action_type:
                    pad = max(48, int(min(width, height) * 0.05))
                    x1, x2 = sorted((sx, ex))
                    y1, y2 = sorted((sy, ey))
                    x1 -= pad
                    y1 -= pad
                    x2 += pad
                    y2 += pad
                else:
                    box_size = max(64, min(128, int(min(width, height) * 0.09)))
                    half = box_size // 2
                    x1, y1 = sx - half, sy - half
                    x2, y2 = sx + half, sy + half

            class_name = click_target.get("element_name") or "tap_target"
            objects = [{
                "class_name": class_name,
                "bbox_xyxy": [x1, y1, x2, y2],
                "source": click_target.get("status", "click_target"),
                "role": "clicked_target",
            }]
            for obj in data.get("gpt_yolo_objects", {}).get("objects", []):
                name = obj.get("class_name") or obj.get("name")
                bbox = obj.get("bbox_xyxy")
                if not name or not bbox or len(bbox) != 4:
                    continue
                objects.append({
                    "class_name": name,
                    "bbox_xyxy": bbox,
                    "source": "gpt-5.5",
                    "role": obj.get("role", "ui_element"),
                })

            label_lines = []
            normalized_objects = []
            seen = set()
            for obj in objects:
                bx1, by1, bx2, by2 = [int(v) for v in obj["bbox_xyxy"]]
                bx1 = max(0, min(width - 1, bx1))
                by1 = max(0, min(height - 1, by1))
                bx2 = max(bx1 + 1, min(width, bx2))
                by2 = max(by1 + 1, min(height, by2))
                key = (obj["class_name"], bx1 // 8, by1 // 8, bx2 // 8, by2 // 8)
                if key in seen:
                    continue
                seen.add(key)
                class_id = self._ensure_yolo_class(obj["class_name"])
                x_center = ((bx1 + bx2) / 2) / width
                y_center = ((by1 + by2) / 2) / height
                box_w = (bx2 - bx1) / width
                box_h = (by2 - by1) / height
                label_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}")
                normalized_objects.append({
                    "class_id": class_id,
                    "class_name": obj["class_name"],
                    "bbox_xyxy": [int(bx1), int(by1), int(bx2), int(by2)],
                    "source": obj.get("source", ""),
                    "role": obj.get("role", ""),
                })
            label_text = "\n".join(label_lines) + "\n"

            event_key = op_dir.name
            local_yolo_dir = op_dir / "yolo"
            local_images = local_yolo_dir / "images"
            local_labels = local_yolo_dir / "labels"
            local_images.mkdir(parents=True, exist_ok=True)
            local_labels.mkdir(parents=True, exist_ok=True)
            local_image = local_images / f"{event_key}.png"
            local_label = local_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(local_image))
            local_label.write_text(label_text, encoding="utf-8")
            classes_text = self._yolo_classes_text()
            (local_yolo_dir / "classes.txt").write_text(classes_text, encoding="utf-8")

            dataset_images = GAME_DATA_DIR / "yolo_events" / "images" / "train"
            dataset_labels = GAME_DATA_DIR / "yolo_events" / "labels" / "train"
            dataset_images.mkdir(parents=True, exist_ok=True)
            dataset_labels.mkdir(parents=True, exist_ok=True)
            dataset_image = dataset_images / f"{event_key}.png"
            dataset_label = dataset_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(dataset_image))
            dataset_label.write_text(label_text, encoding="utf-8")
            (GAME_DATA_DIR / "yolo_events" / "classes.txt").write_text(classes_text, encoding="utf-8")
            (GAME_DATA_DIR / "yolo_events" / "data.yaml").write_text(
                self._yolo_data_yaml(),
                encoding="utf-8",
            )

            return {
                "class_id": normalized_objects[0]["class_id"] if normalized_objects else 0,
                "class_name": normalized_objects[0]["class_name"] if normalized_objects else class_name,
                "image_width": width,
                "image_height": height,
                "bbox_xyxy": normalized_objects[0]["bbox_xyxy"] if normalized_objects else [int(x1), int(y1), int(x2), int(y2)],
                "objects": normalized_objects,
                "label": label_text.strip(),
                "local_image": str(local_image),
                "local_label": str(local_label),
                "dataset_image": str(dataset_image),
                "dataset_label": str(dataset_label),
            }
        except Exception as e:
            LogManager().append(f"[WARN] write yolo annotation failed: {e}")
            return {"error": str(e)}

    def _load_yolo_classes(self) -> list[str]:
        try:
            from agent_data import GAME_DATA_DIR

            path = GAME_DATA_DIR / "yolo_events" / "classes.txt"
            if not path.exists():
                return ["tap_target"]
            names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            return names or ["tap_target"]
        except Exception:
            return ["tap_target"]

    def _ensure_yolo_class(self, class_name: str) -> int:
        from agent_data import GAME_DATA_DIR

        safe_name = re.sub(r"\s+", "_", (class_name or "tap_target").strip())[:32] or "tap_target"
        names = self._load_yolo_classes()
        if safe_name not in names:
            names.append(safe_name)
            path = GAME_DATA_DIR / "yolo_events" / "classes.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(names) + "\n", encoding="utf-8")
        return names.index(safe_name)

    def _yolo_classes_text(self) -> str:
        return "\n".join(self._load_yolo_classes()) + "\n"

    def _yolo_data_yaml(self) -> str:
        names = self._load_yolo_classes()
        lines = ["path: .", "train: images/train", "val: images/train", "names:"]
        lines.extend(f"  {idx}: {name}" for idx, name in enumerate(names))
        return "\n".join(lines) + "\n"

    def _click_bbox(self, image_size: tuple[int, int], data: dict) -> list[int]:
        width, height = image_size
        touch = data.get("touch", {})
        start = touch.get("frame_start", {})
        end = touch.get("frame_end", start)
        sx, sy = int(start.get("x", 0)), int(start.get("y", 0))
        ex, ey = int(end.get("x", sx)), int(end.get("y", sy))
        if "swipe" in data.get("action_type", ""):
            pad = max(48, int(min(width, height) * 0.05))
            x1, x2 = sorted((sx, ex))
            y1, y2 = sorted((sy, ey))
            x1 -= pad
            y1 -= pad
            x2 += pad
            y2 += pad
        else:
            box_size = max(96, min(180, int(min(width, height) * 0.14)))
            half = box_size // 2
            x1, y1 = sx - half, sy - half
            x2, y2 = sx + half, sy + half
        return [
            max(0, min(width - 1, int(x1))),
            max(0, min(height - 1, int(y1))),
            max(1, min(width, int(x2))),
            max(1, min(height, int(y2))),
        ]

    def _analyze_click_target(self, op_dir: Path, data: dict, scene_result: dict | None) -> dict:
        try:
            from PIL import Image
            from scene_index import image_fingerprint
            from agent_data import AgentDataManager

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"status": "no_before_image"}
            before_path = op_dir / before_name
            if not before_path.exists():
                return {"status": "before_image_missing"}

            with Image.open(before_path).convert("RGB") as img:
                bbox = self._click_bbox(img.size, data)
                x1, y1, x2, y2 = bbox
                crop_dir = op_dir / "crops"
                crop_dir.mkdir(parents=True, exist_ok=True)
                crop_path = crop_dir / "click_target.png"
                img.crop((x1, y1, x2, y2)).save(str(crop_path))

            fingerprint = image_fingerprint(crop_path)
            dm = AgentDataManager()
            matched = dm.find_ui_element_by_hash(fingerprint)
            if matched:
                return {
                    "status": "hash_matched",
                    "element_id": matched["id"],
                    "element_name": matched.get("element_name") or "tap_target",
                    "action_effect": matched.get("action_effect") or "",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "hash": fingerprint,
                    "match_confidence": matched["confidence"],
                }

            llm_result = self._describe_click_target_with_llm(crop_path, data, scene_result)
            element_name = (llm_result.get("element_name") or "").strip()
            if (
                not element_name
                or element_name == "tap_target"
                or llm_result.get("error")
                or not llm_result.get("parse_ok", False)
            ):
                return {
                    "status": "needs_model_or_manual",
                    "reason": "click target was not confidently identified",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "hash": fingerprint,
                    "llm": llm_result,
                }
            action_effect = llm_result.get("action_effect") or ""
            class_id = self._ensure_yolo_class(element_name)
            scene_id = scene_result.get("scene_id") if scene_result else None
            scene_key = scene_result.get("scene_key", "") if scene_result else ""
            element_id = dm.upsert_ui_element(
                scene_id=scene_id,
                scene_key=scene_key,
                element_type=llm_result.get("element_type") or "click_target",
                element_name=element_name,
                text=llm_result.get("text") or "",
                bbox_xyxy=bbox,
                source=llm_result.get("source") or "gpt-5.5",
                confidence=float(llm_result.get("confidence") or 0.6),
                fingerprint=fingerprint,
                image_path=crop_path,
                yolo_class_id=class_id,
                action_effect=action_effect,
            )
            return {
                "status": "llm_labeled",
                "element_id": element_id,
                "element_name": element_name,
                "element_type": llm_result.get("element_type") or "click_target",
                "action_effect": action_effect,
                "bbox_xyxy": bbox,
                "crop_image": str(crop_path),
                "hash": fingerprint,
                "llm": llm_result,
            }
        except Exception as e:
            LogManager().append(f"[WARN] analyze click target failed: {e}")
            return {"status": "error", "error": str(e)}

    def _describe_click_target_with_llm(self, crop_path: Path, data: dict, scene_result: dict | None) -> dict:
        try:
            from llm_client import QwenVLClient

            scene_text = ""
            if scene_result:
                scene_text = scene_result.get("description") or scene_result.get("scene_key") or ""
            prompt = (
                "这是一张游戏截图中用户点击位置附近的局部裁剪图。"
                "请判断被点击的图标/按钮是什么，以及点击它通常会产生什么作用。"
                "只输出 JSON，不要解释："
                '{"element_name":"短名称","element_type":"button/icon/menu/item/unknown",'
                '"text":"图中可见文字，没有就空字符串","action_effect":"点击作用",'
                '"confidence":0.0}'
                f"\n当前场景线索：{scene_text}"
            )
            raw = QwenVLClient().describe_image(crop_path, prompt=prompt)
            parsed = {}
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(1))
            else:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
            if not isinstance(parsed, dict):
                parsed = {}
            parsed["parse_ok"] = bool(parsed)
            parsed["raw"] = raw[:500]
            parsed["source"] = "gpt-5.5"
            return parsed
        except Exception as e:
            return {
                "element_name": "tap_target",
                "element_type": "unknown",
                "action_effect": "",
                "confidence": 0.2,
                "source": "fallback",
                "error": str(e),
            }

    def _analyze_yolo_objects_with_gpt55(self, op_dir: Path, data: dict, scene_result: dict | None) -> dict:
        try:
            from llm_client import QwenVLClient
            from PIL import Image

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"status": "no_before_image", "objects": []}
            before_path = op_dir / before_name
            if not before_path.exists():
                return {"status": "before_image_missing", "objects": []}

            with Image.open(before_path) as img:
                width, height = img.size

            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            scene_text = ""
            if scene_result:
                scene_text = scene_result.get("description") or scene_result.get("scene_key") or ""
            prompt = (
                "你是游戏 UI 的 YOLO 标注助手。请分析整张截图，尽量多标注可点击、可识别、对自动化有用的 UI 元素。"
                "必须重点标注用户点击点所在的图标/按钮，也要标注周围其它按钮、图标、菜单、卡片、文字按钮、关闭按钮、开始按钮、奖励入口等。"
                "不要标注背景、纯装饰、无法稳定复现的光效。bbox 用原图像素坐标，不要用归一化坐标。"
                "元素名要短，适合作为 YOLO class，例如 start_button、close_button、plant_card、shop_icon。"
                "只输出 JSON，不要解释："
                '{"objects":[{"class_name":"英文或拼音短类名","name":"中文名","bbox_xyxy":[x1,y1,x2,y2],'
                '"role":"clicked_target/ui_element","action_effect":"点击作用","confidence":0.0}]}'
                f"\n图像尺寸：{width}x{height}"
                f"\n用户点击点：({click_x},{click_y})"
                f"\n当前场景线索：{scene_text}"
            )
            raw = QwenVLClient(model="openai/gpt-5.5").describe_image(before_path, prompt=prompt, timeout=180)
            parsed = {}
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(1))
            else:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
            objects = []
            for obj in parsed.get("objects", []) if isinstance(parsed, dict) else []:
                bbox = obj.get("bbox_xyxy") or obj.get("bbox")
                name = obj.get("class_name") or obj.get("name")
                if not name or not bbox or len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                x1 = max(0, min(width - 1, x1))
                y1 = max(0, min(height - 1, y1))
                x2 = max(x1 + 1, min(width, x2))
                y2 = max(y1 + 1, min(height, y2))
                safe_name = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(name)).strip("_")[:32]
                objects.append({
                    "class_name": safe_name or "ui_element",
                    "name": obj.get("name", ""),
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "role": obj.get("role", "ui_element"),
                    "action_effect": obj.get("action_effect", ""),
                    "confidence": obj.get("confidence", 0.5),
                })
            LogManager().append(f"[EventUnknown] gpt-5.5 YOLO 标注候选 {op_dir.name}: {len(objects)}")
            return {
                "status": "ok" if objects else "empty",
                "model": "openai/gpt-5.5",
                "objects": objects,
                "raw": raw[:800],
            }
        except Exception as e:
            LogManager().append(f"[WARN] gpt yolo objects failed: {e}")
            return {"status": "error", "objects": [], "error": str(e)}

    def _queue_scene_for_unknown_processor(self, image_path: Path, event_key: str, label: str) -> str | None:
        try:
            import shutil

            if not image_path.exists():
                return None
            unknown_dir = Path("screenshots") / "unknown"
            unknown_dir.mkdir(parents=True, exist_ok=True)
            target = unknown_dir / f"{event_key}_{label}{image_path.suffix}"
            if not target.exists():
                shutil.copy2(str(image_path), str(target))
            return str(target)
        except Exception as e:
            LogManager().append(f"[WARN] queue scene unknown failed: {e}")
            return None

    def _event_unknown_loop(self):
        event_dir = Path("screenshots") / "event_unknown"
        event_dir.mkdir(parents=True, exist_ok=True)
        while not self._event_unknown_stop.is_set():
            self._process_event_unknown_once(event_dir)
            self._event_unknown_stop.wait(3)

    def _process_event_unknown_once(self, event_dir: Path):
        for folder in sorted(event_dir.glob("physical_*"), key=lambda p: p.stat().st_mtime):
            if self._event_unknown_stop.is_set():
                break
            if not folder.is_dir() or not (folder / ".ready").exists():
                continue
            self._process_event_unknown_folder(folder)

    def _process_event_unknown_folder(self, op_dir: Path):
        index_path = op_dir / "index.json"
        if not index_path.exists():
            return
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            LogManager().append(f"[EventUnknown] index 读取失败 {op_dir.name}: {e}")
            return
        if data.get("status") in ("review_pending", "review_approved", "processing"):
            return

        data["status"] = "processing"
        index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        LogManager().append(f"[EventUnknown] 开始处理 {op_dir.name}")

        before_path = op_dir / (data.get("images", {}).get("before") or "before.png")
        after_name = data.get("images", {}).get("after") or "after_300ms.png"
        after_path = op_dir / after_name

        if before_path.exists():
            try:
                from scene_index import SceneIndex

                data["scene_index"] = SceneIndex().ensure_scene(before_path, threshold=0.92)
                if not data["scene_index"].get("matched"):
                    queued = self._queue_scene_for_unknown_processor(before_path, op_dir.name, "before")
                    if queued:
                        data["scene_index"]["queued_unknown"] = queued
            except Exception as e:
                data["scene_index"] = {"error": str(e)}

        if after_path.exists():
            try:
                from scene_index import SceneIndex

                after_scene = SceneIndex().ensure_scene(after_path, threshold=0.92)
                if not after_scene.get("matched"):
                    queued = self._queue_scene_for_unknown_processor(after_path, op_dir.name, "after")
                    if queued:
                        after_scene["queued_unknown"] = queued
                data["after_scene_index"] = after_scene
            except Exception as e:
                data["after_scene_index"] = {"error": str(e)}

        data["click_target"] = self._analyze_click_target(
            op_dir,
            data,
            data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
        )
        data["gpt_yolo_objects"] = self._analyze_yolo_objects_with_gpt55(
            op_dir,
            data,
            data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
        )
        data["yolo"] = self._write_yolo_event_annotation(op_dir, data)
        try:
            from agent_data import AgentDataManager

            event_id = AgentDataManager().record_physical_event(
                event_key=op_dir.name,
                action_type=data.get("action_type", ""),
                timestamp_ms=int(time.time() * 1000),
                duration_ms=int(data.get("duration_ms") or 0),
                touch=data.get("touch", {}),
                folder_path=op_dir,
                images=data.get("images", {}),
                index_path=index_path,
                yolo=data.get("yolo"),
            )
            data["db"] = {"physical_event_id": event_id}
        except Exception as e:
            data["db"] = {"error": str(e)}
            LogManager().append(f"[EventUnknown] 入库失败 {op_dir.name}: {e}")

        target_status = "review_pending"
        click_status = data.get("click_target", {}).get("status")
        if click_status in ("error", "no_before_image", "before_image_missing"):
            target_status = "needs_model_or_manual"
        data["status"] = target_status
        index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        LogManager().append(f"[EventUnknown] 处理完成 {op_dir.name} -> {target_status}")
        self._bridge.events_changed.emit()

    def _write_touch_index(
        self,
        op_dir: Path,
        action_type: str,
        duration_ms: int,
        start,
        end,
        frame_start,
        frame_end,
        pressed_delay_ms: int,
        after_delay_ms: int,
    ) -> None:
        try:
            import json
            from datetime import datetime

            before_path = op_dir / "before.png"
            pressed_path = op_dir / "pressed.png"
            after_path = op_dir / "after.png"
            after_300ms_path = op_dir / "after_300ms.png"

            # 优先使用 after.png，session 模式下使用 after_300ms.png
            compare_after_path = after_path if after_path.exists() else after_300ms_path

            before_pressed = (
                self._image_change_score(before_path, pressed_path, frame_start)
                if before_path.exists() and pressed_path.exists()
                else {}
            )
            before_after = (
                self._image_change_score(before_path, compare_after_path, frame_start)
                if before_path.exists() and compare_after_path.exists()
                else {}
            )

            local_change = before_pressed.get("local", before_pressed.get("global", 0.0))
            global_change = before_pressed.get("global", 0.0)
            pressed_changed = local_change >= 0.025 or global_change >= 0.006
            if duration_ms < pressed_delay_ms:
                pressed_state = "too_fast_to_capture_pressed"
            elif pressed_changed:
                pressed_state = "visual_change_detected"
            else:
                pressed_state = "no_visual_change_detected"

            data = {
                "status": "raw_captured",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "action_type": action_type,
                "duration_ms": duration_ms,
                "pressed_delay_ms": pressed_delay_ms,
                "after_delay_ms": after_delay_ms,
                "touch": {
                    "start": {"x": start[0], "y": start[1]},
                    "end": {"x": end[0], "y": end[1]},
                    "frame_start": {"x": frame_start[0], "y": frame_start[1]},
                    "frame_end": {"x": frame_end[0], "y": frame_end[1]},
                },
                "images": {
                    "before": "before.png",
                    "pressed": "pressed.png" if pressed_path.exists() else None,
                    "after": "after.png" if after_path.exists() else None,
                },
                "change": {
                    "before_pressed": before_pressed,
                    "before_after": before_after,
                    "pressed_state": pressed_state,
                },
            }
            if op_dir.parent.name == "event_unknown":
                index_path = op_dir / "index.json"
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                (op_dir / ".ready").write_text(
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    encoding="utf-8",
                )
                LogManager().append(f"[EventUnknown] 原始事件已入队: {op_dir.name}")
                self._bridge.events_changed.emit()
                return
            if before_path.exists():
                try:
                    from scene_index import SceneIndex

                    data["scene_index"] = SceneIndex().ensure_scene(
                        before_path,
                        threshold=0.92,
                    )
                    if not data["scene_index"].get("matched"):
                        queued = self._queue_scene_for_unknown_processor(before_path, op_dir.name, "before")
                        if queued:
                            data["scene_index"]["queued_unknown"] = queued
                except Exception as e:
                    data["scene_index"] = {"error": str(e)}
            if compare_after_path.exists():
                try:
                    from scene_index import SceneIndex

                    after_scene = SceneIndex().ensure_scene(compare_after_path, threshold=0.92)
                    if not after_scene.get("matched"):
                        queued = self._queue_scene_for_unknown_processor(compare_after_path, op_dir.name, "after")
                        if queued:
                            after_scene["queued_unknown"] = queued
                    data["after_scene_index"] = after_scene
                except Exception as e:
                    data["after_scene_index"] = {"error": str(e)}
            data["click_target"] = self._analyze_click_target(
                op_dir,
                data,
                data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
            )
            data["yolo"] = self._write_yolo_event_annotation(op_dir, data)
            index_path = op_dir / "index.json"
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                from agent_data import AgentDataManager

                event_id = AgentDataManager().record_physical_event(
                    event_key=op_dir.name,
                    action_type=action_type,
                    timestamp_ms=int(time.time() * 1000),
                    duration_ms=duration_ms,
                    touch=data["touch"],
                    folder_path=op_dir,
                    images=data["images"],
                    index_path=index_path,
                    yolo=data.get("yolo"),
                )
                data["db"] = {"physical_event_id": event_id}
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                LogManager().append(f"[WARN] record physical event db failed: {e}")
        except Exception as e:
            LogManager().append(f"[WARN] write touch index failed: {e}")

    def _send_scrcpy_touch(self, frame_x: int, frame_y: int, action: int) -> bool:
        if not (self.client and self.client.alive):
            return False
        try:
            self.client.control.touch(frame_x, frame_y, action)
            return True
        except Exception as e:
            LogManager().append(f"[WARN] scrcpy touch failed: {e}")
            return False

    def _on_physical_touch(self, device_x: int, device_y: int, action: int):
        frame_x, frame_y = self._map_device_to_frame(device_x, device_y)
        if frame_x is None:
            return

        if action == scrcpy.ACTION_DOWN:
            from datetime import datetime

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            op_dir = Path("screenshots") / "event_unknown" / f"physical_{ts}"
            op_dir.mkdir(parents=True, exist_ok=True)

            self._physical_touch_start = (device_x, device_y)
            self._physical_touch_last = (device_x, device_y)
            self._physical_touch_frame_start = (frame_x, frame_y)
            self._physical_touch_frame_last = (frame_x, frame_y)
            self._physical_touch_time = time.time()
            self._physical_op_dir = op_dir

            self._save_video_frame_async("before", op_dir)
            self._bridge.touch_feedback.emit([(frame_x, frame_y)], 1500)

            def _capture_pressed():
                time.sleep(0.08)
                self._save_video_frame_sync("pressed", op_dir)

            threading.Thread(target=_capture_pressed, daemon=True).start()
            LogManager().append(f"[GetEvent] DOWN device=({device_x},{device_y}) frame=({frame_x},{frame_y})")

        elif action == scrcpy.ACTION_MOVE:
            self._physical_touch_last = (device_x, device_y)
            self._physical_touch_frame_last = (frame_x, frame_y)
            if self._physical_touch_frame_start:
                self._bridge.touch_feedback.emit(
                    [self._physical_touch_frame_start, (frame_x, frame_y)],
                    1500,
                )

        elif action == scrcpy.ACTION_UP:
            if self._physical_touch_start is None:
                return

            sx, sy = self._physical_touch_start
            ex, ey = self._physical_touch_last or (device_x, device_y)
            frame_start = self._physical_touch_frame_start or (frame_x, frame_y)
            frame_end = self._physical_touch_frame_last or (frame_x, frame_y)
            duration_ms = int((time.time() - self._physical_touch_time) * 1000)
            op_dir = self._physical_op_dir

            dx = abs(ex - sx)
            dy = abs(ey - sy)
            action_type = "tap" if dx < 8 and dy < 8 else "swipe"
            self._bridge.touch_feedback.emit([frame_start, frame_end], 2000)

            def _exec():
                try:
                    if op_dir:
                        time.sleep(0.12)
                        self._save_video_frame_sync("after", op_dir)
                        self._write_touch_index(
                            op_dir,
                            f"physical_{action_type}",
                            duration_ms,
                            (sx, sy),
                            (ex, ey),
                            frame_start,
                            frame_end,
                            80,
                            120,
                        )
                        LogManager().append(
                            f"[GetEvent] UP {action_type} device=({sx},{sy})->({ex},{ey}) "
                            f"duration={duration_ms}ms -> {op_dir}"
                        )
                        self._bridge.events_changed.emit()
                except Exception as e:
                    LogManager().append(f"[GetEvent] record physical touch failed: {e}")

            threading.Thread(target=_exec, daemon=True).start()
            self._physical_touch_start = None
            self._physical_touch_last = None
            self._physical_touch_frame_start = None
            self._physical_touch_frame_last = None
            self._physical_op_dir = None

    def _on_touch(self, frame_x: int, frame_y: int, action: int):
        if not self._projection_control_enabled:
            return
        device_x, device_y = self._map_frame_to_device(frame_x, frame_y)
        if device_x is None:
            return

        session_active = self.execution_engine.dm.is_session_active()

        if action == 0:          # DOWN
            from datetime import datetime

            self._touch_start = (device_x, device_y)
            self._touch_last = (device_x, device_y)
            self._touch_frame_start = (frame_x, frame_y)
            self._touch_frame_last = (frame_x, frame_y)
            self._touch_time = time.time()

            if session_active:
                click_dir = self.execution_engine.dm.get_click_dir()
                idx = self.execution_engine.dm.click_counter + 1
                op_dir = click_dir / f"click_{idx:06d}"
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                op_dir = Path("screenshots") / f"op_{ts}"

            op_dir.mkdir(parents=True, exist_ok=True)
            self._op_dir_for_touch = op_dir

            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_DOWN)
            frame = self.video_widget._frame if self.video_widget else None
            self._save_video_frame_async("before", op_dir, frame)

            def _capture_pressed():
                time.sleep(0.08)
                self._save_video_frame_sync("pressed", op_dir)

            threading.Thread(
                target=_capture_pressed,
                daemon=True
            ).start()
        elif action == 2:        # MOVE
            self._touch_last = (device_x, device_y)
            self._touch_frame_last = (frame_x, frame_y)
            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_MOVE)
        elif action == 1:        # UP
            if self._touch_start is None:
                return
            sx, sy = self._touch_start
            ex, ey = self._touch_last
            frame_start = self._touch_frame_start or (frame_x, frame_y)
            frame_end = self._touch_frame_last or (frame_x, frame_y)
            duration_ms = int((time.time() - self._touch_time) * 1000)
            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_UP)

            dx = abs(ex - sx)
            dy = abs(ey - sy)
            is_tap = dx < 8 and dy < 8
            op_dir = self._op_dir_for_touch
            self._op_dir_for_touch = None

            def _exec():
                try:
                    if session_active and op_dir:
                        # Session 模式：委托给 ExecutionEngine
                        self.execution_engine.on_click_up(
                            sx, sy, op_dir,
                            lambda: self.video_widget._frame if self.video_widget else None
                        )
                        # 同时保留 index.json（向后兼容）
                        self._write_touch_index(
                            op_dir,
                            "tap" if is_tap else "swipe",
                            duration_ms,
                            (sx, sy),
                            (ex, ey),
                            frame_start,
                            frame_end,
                            80,
                            120,
                        )
                    else:
                        # 非 Session 模式：原有逻辑
                        if is_tap:
                            if op_dir:
                                time.sleep(0.12)
                                self._save_video_frame_sync("after", op_dir)
                                self._write_touch_index(
                                    op_dir,
                                    "tap",
                                    duration_ms,
                                    (sx, sy),
                                    (ex, ey),
                                    frame_start,
                                    frame_end,
                                    80,
                                    120,
                                )
                        else:
                            if op_dir:
                                time.sleep(0.12)
                                self._save_video_frame_sync("after", op_dir)
                                self._write_touch_index(
                                    op_dir,
                                    "swipe",
                                    duration_ms,
                                    (sx, sy),
                                    (ex, ey),
                                    frame_start,
                                    frame_end,
                                    80,
                                    120,
                                )
                except Exception:
                    pass

            threading.Thread(target=_exec, daemon=True).start()
            self._touch_start = None
            self._touch_frame_start = None
            self._touch_frame_last = None

    def _on_scroll(self, frame_x: int, frame_y: int, h: int, v: int):
        if not self._projection_control_enabled:
            return
        device_x, device_y = self._map_frame_to_device(frame_x, frame_y)
        if device_x is None:
            return
        ex = device_x - h * 8
        ey = device_y - v * 8
        if abs(ex - device_x) < 30 and abs(ey - device_y) < 30:
            return

        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        op_dir = Path("screenshots") / f"op_{ts}"
        op_dir.mkdir(parents=True, exist_ok=True)
        self._save_video_frame_async("before", op_dir)

        sent = False
        if self.client and self.client.alive:
            try:
                self.client.control.scroll(frame_x, frame_y, h, v)
                sent = True
            except Exception as e:
                LogManager().append(f"[WARN] scrcpy scroll failed: {e}")

        def _exec():
            try:
                if not sent and self._adb_device is not None:
                    self._adb_device.shell(f"input swipe {device_x} {device_y} {ex} {ey} 150")
                time.sleep(0.12)
                self._save_video_frame_sync("after", op_dir)
            except Exception:
                pass

        threading.Thread(target=_exec, daemon=True).start()
        return
        # 滚轮一格 angleDelta 约 120，映射为滚动像素
        ex = device_x - h * 8
        ey = device_y - v * 8
        if abs(ex - device_x) < 30 and abs(ey - device_y) < 30:
            return  # 移动太小，忽略，避免像点击

        # 主线程先把操作目录建好
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        op_dir = Path("screenshots") / f"op_{ts}"
        op_dir.mkdir(parents=True, exist_ok=True)

        def _exec():
            try:
                self._take_screenshot_sync("before", "滚轮", op_dir)
                self._adb_device.shell(f"input swipe {device_x} {device_y} {ex} {ey} 150")
                self._take_screenshot_sync("after", "滚轮", op_dir)
            except Exception:
                pass

        threading.Thread(target=_exec, daemon=True).start()

    # ------------------------------------------------------------------
    # 自动化决策
    # ------------------------------------------------------------------
    def do_auto_step(self):
        """执行一步自动化：截图 -> 视觉解读 -> 决策 -> 执行"""
        if not (self.client and self.client.alive):
            self._set_status("状态: 请先连接设备")
            self._auto_timer.stop()
            if self.btn_auto_run:
                self.btn_auto_run.setChecked(False)
                self.btn_auto_run.setText("开始连续执行")
            return

        frame = self.video_widget._frame if self.video_widget else None
        if frame is None:
            self._set_status("状态: 暂无视频帧")
            return

        try:
            from PIL import Image
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            op_dir = Path("screenshots") / f"auto_{ts}"
            op_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = op_dir / "frame.png"
            Image.fromarray(frame.copy()).save(str(screenshot_path))
        except Exception as e:
            self._set_status(f"状态: 截图失败 - {e}")
            return

        goal = self.edit_goal.text().strip() if self.edit_goal else ""

        def _run():
            try:
                result = self.decision_engine.run_step(screenshot_path, goal=goal)
                decision = result.get("decision", {})
                scene_desc = result.get("scene_description", "")
                self._bridge.decision_ready.emit({
                    "decision": decision,
                    "scene_description": scene_desc,
                    "screenshot_path": str(screenshot_path),
                })
            except Exception as e:
                import traceback
                self._bridge.status_changed.emit(f"决策失败: {e}", "#f44747")
                LogManager().append(f"[ERROR] auto_step:\n{traceback.format_exc()}")

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_audit_list(self):
        """从 scene_index.sqlite 读取场景列表并展示，支持按审核状态单选过滤。"""
        self.audit_list.clear()
        try:
            from scene_index import SceneIndex
            si = SceneIndex()
            # 单选：未审核=0, 审核通过=1
            status_filter = 1 if self.rb_approved.isChecked() else 0
            with si._connect() as conn:
                rows = conn.execute(
                    "SELECT id, scene_key, scene_type, hits, model_name, review_status, created_at, image_path FROM scenes WHERE review_status = ? ORDER BY hits DESC",
                    (status_filter,),
                ).fetchall()
            for row_id, scene_key, scene_type, hits, model_name, review_status, created_at, image_path in rows:
                item = QTreeWidgetItem()
                item.setText(0, str(scene_key))
                item.setText(1, str(scene_type or ""))
                item.setText(2, str(hits))
                item.setText(3, str(model_name))
                item.setText(4, "审核通过" if review_status else "未审核")
                item.setText(5, str(created_at))
                item.setData(0, 256, row_id)          # 存储 id
                item.setData(0, 257, str(image_path)) # 存储图片路径
                self.audit_list.addTopLevelItem(item)
        except Exception as e:
            LogManager().append(f"[Audit] 刷新场景列表失败: {e}")

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

    def _show_audit_context_menu(self, position):
        """右键菜单：重新识别。"""
        item = self.audit_list.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        action_ollama = menu.addAction("重新 Ollama 识别")
        action_qwen = menu.addAction("重新 qwen-vl-max 识别")
        action = menu.exec(self.audit_list.viewport().mapToGlobal(position))
        if action == action_ollama:
            self._reclassify_scene(item, "ollama")
        elif action == action_qwen:
            self._reclassify_scene(item, "qwen")

    def _reclassify_scene(self, item: QTreeWidgetItem, engine: str):
        """用指定引擎重新识别场景，更新数据库。在后台线程执行。"""
        row_id = item.data(0, 256)
        image_path_str = item.data(0, 257)
        old_name = item.text(0)
        if not image_path_str:
            self._set_status("审核: 该场景没有图片路径")
            return
        image_path = Path(image_path_str)
        if not image_path.exists():
            self._set_status(f"审核: 图片不存在 {image_path}")
            return

        self._set_status(f"审核: 正在用 {engine} 重新识别 '{old_name}'...")

        def _run():
            try:
                from scene_index import SceneIndex, classify_image_with_ollama, classify_image_with_qwen
                from datetime import datetime

                if engine == "ollama":
                    result = classify_image_with_ollama(image_path)
                else:
                    result = classify_image_with_qwen(image_path)

                if not result or not result.get("name") or result.get("name") == "未知":
                    self._set_status(f"审核: {engine} 重新识别失败，结果无效")
                    return

                new_name = result["name"]
                desc = result.get("desc", "")
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                si = SceneIndex()
                with si._connect() as conn:
                    conn.execute(
                        "UPDATE scenes SET scene_key = ?, description = ?, model_name = ?, updated_at = ? WHERE id = ?",
                        (new_name, desc, engine, now, row_id),
                    )

                self._set_status(f"审核: '{old_name}' → '{new_name}' ({engine})")
                self._refresh_audit_list()
            except Exception as e:
                import traceback
                LogManager().append(f"[Audit] 重新识别失败:\n{traceback.format_exc()}")
                self._set_status(f"审核: 重新识别失败 - {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _toggle_auto_run(self):
        if not self.btn_auto_run:
            return
        if self.btn_auto_run.isChecked():
            self.btn_auto_run.setText("停止连续执行")
            self.do_auto_step()
            self._auto_timer.start(3500)
        else:
            self.btn_auto_run.setText("开始连续执行")
            self._auto_timer.stop()

    def _execute_decision_slot(self, payload: dict):
        """主线程槽：接收决策结果并执行"""
        decision = payload.get("decision", {})
        scene_desc = payload.get("scene_description", "")
        action = decision.get("action", "none")
        params = decision.get("params", {})
        reasoning = decision.get("reasoning", "")

        if self.lbl_decision_result:
            text = f"画面: {scene_desc[:40]}\n动作: {action} | {reasoning[:80]}"
            self.lbl_decision_result.setText(text)

        self.execute_decision(action, params)
        self._set_status(f"自动: {action} | {reasoning[:60]}", log=False)

    def execute_decision(self, action: str, params: dict):
        """将决策转化为实际的屏幕操作（比例坐标 -> 帧坐标）"""
        if not (self.client and self.client.alive):
            return

        frame = self.video_widget._frame if self.video_widget else None
        if frame is None:
            return

        fh, fw = frame.shape[:2]
        if fw <= 0 or fh <= 0:
            return

        if action == "tap":
            rx = params.get("rx", 0.5)
            ry = params.get("ry", 0.5)
            fx = int(max(0.0, min(1.0, rx)) * (fw - 1))
            fy = int(max(0.0, min(1.0, ry)) * (fh - 1))
            self._send_scrcpy_touch(fx, fy, scrcpy.ACTION_DOWN)
            QTimer.singleShot(80, lambda: self._send_scrcpy_touch(fx, fy, scrcpy.ACTION_UP))

        elif action == "swipe":
            rx1 = params.get("rx1", 0.5)
            ry1 = params.get("ry1", 0.5)
            rx2 = params.get("rx2", 0.5)
            ry2 = params.get("ry2", 0.5)
            duration_ms = params.get("duration_ms", 300)
            x1 = int(max(0.0, min(1.0, rx1)) * (fw - 1))
            y1 = int(max(0.0, min(1.0, ry1)) * (fh - 1))
            x2 = int(max(0.0, min(1.0, rx2)) * (fw - 1))
            y2 = int(max(0.0, min(1.0, ry2)) * (fh - 1))

            self._send_scrcpy_touch(x1, y1, scrcpy.ACTION_DOWN)
            steps = max(3, duration_ms // 50)
            for i in range(1, steps + 1):
                t = i / steps
                mx = int(x1 + (x2 - x1) * t)
                my = int(y1 + (y2 - y1) * t)
                delay = int(duration_ms * t)
                QTimer.singleShot(delay, lambda mx=mx, my=my: self._send_scrcpy_touch(mx, my, scrcpy.ACTION_MOVE))
            QTimer.singleShot(duration_ms + 50, lambda: self._send_scrcpy_touch(x2, y2, scrcpy.ACTION_UP))

        elif action == "scroll":
            rx = params.get("rx", 0.5)
            ry = params.get("ry", 0.5)
            rdx = params.get("rdx", 0.0)
            rdy = params.get("rdy", 0.0)
            x = int(max(0.0, min(1.0, rx)) * (fw - 1))
            y = int(max(0.0, min(1.0, ry)) * (fh - 1))
            dx = int(rdx * fw)
            dy = int(rdy * fh)
            self._send_scrcpy_touch(x, y, scrcpy.ACTION_DOWN)
            QTimer.singleShot(50, lambda: self._send_scrcpy_touch(x + dx, y + dy, scrcpy.ACTION_MOVE))
            QTimer.singleShot(100, lambda: self._send_scrcpy_touch(x + dx, y + dy, scrcpy.ACTION_UP))

        elif action == "wait":
            # 纯等待，不操作
            pass

    # ------------------------------------------------------------------
    # 视频录制
    # ------------------------------------------------------------------
    def do_start_record(self):
        if not (self.client and self.client.alive):
            self._set_status("状态: 请先连接设备")
            return
        if self._video_writer is not None:
            self._set_status("状态: 正在录制中")
            return

        frame = self.video_widget._frame if self.video_widget else None
        if frame is None:
            self._set_status("状态: 暂无视频帧，无法开始录制")
            return

        try:
            import cv2
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            record_dir = Path("recordings")
            record_dir.mkdir(exist_ok=True)
            self._record_path = record_dir / f"scrcpy_{ts}.mp4"

            h, w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._video_writer = cv2.VideoWriter(
                str(self._record_path), fourcc, self._record_fps, (w, h)
            )

            if self.btn_record:
                self.btn_record.setEnabled(False)
            if self.btn_stop_record:
                self.btn_stop_record.setEnabled(True)
            self._set_status(f"状态: 开始录制 -> {self._record_path.name}")
        except Exception as e:
            self._video_writer = None
            self._set_status(f"状态: 录制启动失败 - {e}")

    def do_stop_record(self):
        if self._video_writer is None:
            self._set_status("状态: 未在录制")
            return

        try:
            self._video_writer.release()
            self._video_writer = None
            if self.btn_record:
                self.btn_record.setEnabled(True)
            if self.btn_stop_record:
                self.btn_stop_record.setEnabled(False)
            self._set_status(f"状态: 录制已保存 -> {self._record_path.name}")
        except Exception as e:
            self._set_status(f"状态: 停止录制失败 - {e}")

    def do_ocr(self):
        """对当前视频帧执行 OCR 识别，并将结果输出到日志。"""
        frame = self.video_widget._frame if self.video_widget else None
        if frame is None:
            self._set_status("状态: 暂无视频帧")
            return

        try:
            from ocr_client import OCRClient
            from PIL import Image
            from datetime import datetime

            # 保存当前帧用于 OCR（也可直接传 numpy 数组）
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            ocr_dir = Path("screenshots") / f"ocr_{ts}"
            ocr_dir.mkdir(parents=True, exist_ok=True)
            frame_path = ocr_dir / "frame.png"
            Image.fromarray(frame.copy()).save(str(frame_path))

            ocr = OCRClient()
            result = ocr.recognize(frame_path)
            text = ocr.to_text(frame_path=frame_path)

            if text:
                LogManager().append(f"[OCR] 识别结果 ({len(result)} 个区域):")
                for item in result:
                    LogManager().append(
                        f"  [{item['score']:.2f}] {item['text']}"
                    )
                self._set_status(f"OCR: 识别到 {len(result)} 个文字区域")
            else:
                self._set_status("OCR: 未识别到文字")
        except Exception as e:
            import traceback
            self._set_status(f"OCR 识别失败: {e}")
            LogManager().append(f"[ERROR] OCR:\n{traceback.format_exc()}")

    def closeEvent(self, event):
        if hasattr(self, '_event_unknown_stop'):
            self._event_unknown_stop.set()
            if getattr(self, '_event_unknown_thread', None):
                self._event_unknown_thread.join(timeout=2)
        self._stop_getevent_listener()
        # 停止 unknown 后台处理器
        if hasattr(self, '_unknown_processor'):
            self._unknown_processor.stop()
        # 停止 ExecutionEngine 录制
        if self.execution_engine.is_running():
            self.execution_engine.stop()
        # 释放主窗口自己的录制器
        if self._video_writer is not None:
            try:
                self._video_writer.release()
            except Exception:
                pass
            self._video_writer = None
        if self.client:
            self.client.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
