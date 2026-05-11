import re
import struct
import sys
import threading
import time
import json
import socket
import sqlite3
import os
from pathlib import Path
from datetime import datetime

# 自动加载 .env 文件中的环境变量
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        if "=" in _line:
            _key, _val = _line.split("=", 1)
            _key = _key.strip()
            if _key and _key not in os.environ:
                os.environ[_key] = _val.strip()

import scrcpy
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QButtonGroup, QToolButton,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QHBoxLayout, QTextEdit, QSizePolicy, QMenu, QMessageBox,
    QRadioButton, QComboBox, QSpinBox, QDialog, QTableWidget, QTableWidgetItem,
    QDoubleSpinBox, QCheckBox, QSlider, QToolTip, QFileDialog,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsTextItem, QGraphicsItem,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import QTimer, QObject, Signal, Qt, QUrl
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QBrush, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from ui_main_window import Ui_MainWindow
from video_widget import VideoGLWidget
from log_manager import LogManager
from decision_engine import DecisionEngine
from execution_engine import ExecutionEngine
from scene_index import UnknownFolderProcessor, SceneIndex, image_fingerprint
from reanalyze_logger import get_logger
from ui.dialogs.todo_tools import (
    show_batch_scene_register,
    show_cloud_sync,
    show_fast_feature,
    show_migration_tool,
    show_rl_stats,
    show_yolo_class_merge,
    switch_game,
)

# UI widgets (extracted from main.py)
from ui.widgets.signal_bridge import SignalBridge
from ui.widgets.image_labels import AnnotatedImageLabel, ImageThumbnailLabel, YoloReviewImageLabel
from ui.widgets.bbox_canvas import BBoxCanvas
from ui.widgets.charts import BarChartWidget, PieChartWidget

# UI dialogs (extracted from main.py)
from ui.dialogs.bbox_editor import BBoxEditorDialog
from ui.dialogs.rule_edit import RuleEditDialog
from ui.dialogs.video_replay import VideoReplayDialog, TimelineWidget
from ui.dialogs.scene_graph import SceneGraphDialog
from ui.dialogs.rule_stats import RuleStatsDialog, RuntimeRuleDebugDialog
from ui.dialogs.data_quality import DataQualityDialog
from ui.dialogs.auto_replay import AutoReplayDialog
from ui.dialogs.behavior_tree import BehaviorTreeDialog
from ui.dialogs.semantic_agg import SemanticAggregationDialog
from ui.dialogs.kickoff_dashboard import KickoffDashboardDialog




















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
        self._record_events_path = None
        self._record_meta_path = None
        self._record_started_perf = 0.0
        self._record_started_ms = 0
        self._record_frame_count = 0
        self._record_last_frame_perf = 0.0
        self._last_ui_feedback = {}

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
        self._unknown_processor = UnknownFolderProcessor(interval=5, allow_cloud_fallback=True)
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
        self._bridge.overlay_changed.connect(self._set_runtime_feedback_slot)
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
        self._setup_rule_panel()

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

        # 修改 btnExt 为"规则"
        btn_ext = self.findChild(QToolButton, "btnExt")
        if btn_ext:
            btn_ext.setText("规")
            btn_ext.setToolTip("规则管理")
            btn_ext.setVisible(True)

        def on_activity_clicked(btn):
            if not self.side_panel:
                return
            name = btn.objectName()
            self.side_panel.setVisible(name in ("btnAndroid", "btnSearch", "btnRun", "btnGit", "btnExt"))
            if self.ui.tabConnect:
                self.ui.tabConnect.setVisible(name == "btnAndroid")
            if self.file_panel:
                self.file_panel.setVisible(name == "btnSearch")
            if self.audit_panel:
                self.audit_panel.setVisible(name == "btnRun")
            if self.execution_panel:
                self.execution_panel.setVisible(name == "btnGit")
            if self.rule_panel:
                self.rule_panel.setVisible(name == "btnExt")
            if name == "btnSearch":
                self._refresh_events()
            if name == "btnExt":
                self._refresh_rule_list()

        for name in ["btnAndroid", "btnSearch", "btnGit", "btnRun", "btnExt"]:
            btn = self.findChild(QToolButton, name)
            if btn:
                btn.clicked.connect(lambda checked, b=btn: on_activity_clicked(b))
                if name == "btnExt":
                    btn.setVisible(True)

        if self.side_panel:
            self.side_panel.setVisible(True)
        if self.file_panel:
            self.file_panel.setVisible(False)
        if self.audit_panel:
            self.audit_panel.setVisible(False)
        if self.execution_panel:
            self.execution_panel.setVisible(False)
        if getattr(self, "rule_panel", None):
            self.rule_panel.setVisible(False)

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

        # 工具菜单 - 视频回放 / Scene Graph
        self.ui.menuTools = QMenu("工具(&T)", self)
        self.ui.actionVideoReplay = QAction("视频回放", self)
        self.ui.actionVideoReplay.triggered.connect(self._show_video_replay)
        self.ui.menuTools.addAction(self.ui.actionVideoReplay)
        self.ui.actionSceneGraph = QAction("Scene Graph", self)
        self.ui.actionSceneGraph.triggered.connect(self._show_scene_graph)
        self.ui.menuTools.addAction(self.ui.actionSceneGraph)
        self.ui.actionRuleStats = QAction("规则统计", self)
        self.ui.actionRuleStats.triggered.connect(self._show_rule_stats)
        self.ui.menuTools.addAction(self.ui.actionRuleStats)
        self.ui.actionRuleDebug = QAction("规则调试", self)
        self.ui.actionRuleDebug.triggered.connect(self._show_rule_debug)
        self.ui.menuTools.addAction(self.ui.actionRuleDebug)
        self.ui.actionDataQuality = QAction("数据质量", self)
        self.ui.actionDataQuality.triggered.connect(self._show_data_quality)
        self.ui.menuTools.addAction(self.ui.actionDataQuality)
        self.ui.actionAutoReplay = QAction("自动回放", self)
        self.ui.actionAutoReplay.triggered.connect(self._show_auto_replay)
        self.ui.menuTools.addAction(self.ui.actionAutoReplay)
        self.ui.actionBehaviorTree = QAction("行为树", self)
        self.ui.actionBehaviorTree.triggered.connect(self._show_behavior_tree)
        self.ui.menuTools.addAction(self.ui.actionBehaviorTree)
        self.ui.actionSemantic = QAction("语义聚合", self)
        self.ui.actionSemantic.triggered.connect(self._show_semantic_aggregation)
        self.ui.menuTools.addAction(self.ui.actionSemantic)
        self.ui.actionKickoff = QAction("启动仪表盘", self)
        self.ui.actionKickoff.triggered.connect(self._show_kickoff_dashboard)
        self.ui.menuTools.addAction(self.ui.actionKickoff)

        self.ui.menuTools.addSeparator()
        self.ui.actionYoloClassMerge = QAction("YOLO类别合并", self)
        self.ui.actionYoloClassMerge.triggered.connect(self._show_yolo_class_merge)
        self.ui.menuTools.addAction(self.ui.actionYoloClassMerge)
        self.ui.actionBatchSceneReg = QAction("批量场景注册", self)
        self.ui.actionBatchSceneReg.triggered.connect(self._show_batch_scene_register)
        self.ui.menuTools.addAction(self.ui.actionBatchSceneReg)
        self.ui.actionFastFeature = QAction("FastFeature分析", self)
        self.ui.actionFastFeature.triggered.connect(self._show_fast_feature)
        self.ui.menuTools.addAction(self.ui.actionFastFeature)
        self.ui.actionMigration = QAction("历史数据迁移", self)
        self.ui.actionMigration.triggered.connect(self._show_migration_tool)
        self.ui.menuTools.addAction(self.ui.actionMigration)
        self.ui.actionCloudSync = QAction("云端同步", self)
        self.ui.actionCloudSync.triggered.connect(self._show_cloud_sync)
        self.ui.menuTools.addAction(self.ui.actionCloudSync)
        self.ui.actionRLStats = QAction("RL策略统计", self)
        self.ui.actionRLStats.triggered.connect(self._show_rl_stats)
        self.ui.menuTools.addAction(self.ui.actionRLStats)

        # Game switch menu
        self.ui.menuGame = QMenu("游戏(&G)", self)
        self.ui.actionSwitchGame = QAction("切换游戏...", self)
        self.ui.actionSwitchGame.triggered.connect(self._switch_game)
        self.ui.menuGame.addAction(self.ui.actionSwitchGame)
        self.ui.menubar.addAction(self.ui.menuGame.menuAction())

        self.ui.menubar.addAction(self.ui.menuTools.menuAction())

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

        # 搜索框
        search_row = QHBoxLayout()
        self.edit_event_search = QLineEdit()
        self.edit_event_search.setPlaceholderText("搜索事件...")
        self.edit_event_search.setStyleSheet(
            "QLineEdit { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 4px; }"
        )
        self.edit_event_search.textChanged.connect(self._on_event_search_changed)
        search_row.addWidget(self.edit_event_search)
        btn_clear_search = QPushButton("×")
        btn_clear_search.setFixedWidth(28)
        btn_clear_search.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 2px; }"
            "QPushButton:hover { background-color: #f44747; color: white; }"
        )
        btn_clear_search.clicked.connect(lambda: self.edit_event_search.clear())
        search_row.addWidget(btn_clear_search)
        panel_layout.addLayout(search_row)

        self.event_stats_label = QLabel("事件统计: waiting")
        self.event_stats_label.setWordWrap(True)
        self.event_stats_label.setStyleSheet("background-color: #111111; color: #dcdcaa; border: 1px solid #333333; padding: 6px; font-weight: bold;")
        panel_layout.addWidget(self.event_stats_label)

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
        kind_row = QHBoxLayout()
        self.rb_audit_scene = QRadioButton("Scene")
        self.rb_audit_scene.setChecked(True)
        self.rb_audit_scene.setStyleSheet("color: #cccccc;")
        self.rb_audit_yolo = QRadioButton("YOLO")
        self.rb_audit_yolo.setStyleSheet("color: #cccccc;")
        self.rb_audit_kind_group = QButtonGroup(self)
        self.rb_audit_kind_group.setExclusive(True)
        self.rb_audit_kind_group.addButton(self.rb_audit_scene)
        self.rb_audit_kind_group.addButton(self.rb_audit_yolo)
        self.rb_audit_scene.toggled.connect(self._refresh_audit_list)
        self.rb_audit_yolo.toggled.connect(self._refresh_audit_list)
        kind_row.addWidget(self.rb_audit_scene)
        kind_row.addWidget(self.rb_audit_yolo)
        kind_row.addStretch(1)
        panel_layout.addLayout(kind_row)

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

        btn_history = QPushButton("Reanalyze 历史", self.audit_panel)
        btn_history.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_history.clicked.connect(self._show_reanalyze_history)

        audit_btn_row = QHBoxLayout()
        audit_btn_row.addWidget(btn_refresh)
        audit_btn_row.addWidget(btn_history)
        panel_layout.addLayout(audit_btn_row)

        # 批量操作按钮行（YOLO 模式显示）
        self.batch_btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        self.btn_select_all.clicked.connect(self._audit_select_all)
        self.batch_btn_row.addWidget(self.btn_select_all)

        self.btn_batch_approve = QPushButton("批量批准")
        self.btn_batch_approve.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; border: 1px solid #555555; padding: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        self.btn_batch_approve.clicked.connect(self._batch_approve_selected)
        self.batch_btn_row.addWidget(self.btn_batch_approve)

        self.btn_batch_compile = QPushButton("批量编译")
        self.btn_batch_compile.setStyleSheet(
            "QPushButton { background-color: #6a9955; color: white; border: 1px solid #555555; padding: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #7ab868; }"
        )
        self.btn_batch_compile.clicked.connect(self._batch_compile_selected)
        self.batch_btn_row.addWidget(self.btn_batch_compile)
        self.batch_btn_row.addStretch(1)
        panel_layout.addLayout(self.batch_btn_row)

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
        self.audit_list.itemClicked.connect(self._open_audit_item)
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

    def _setup_rule_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.rule_panel = QWidget(self.side_panel)
        self.rule_panel.setObjectName("rulePanel")
        panel_layout = QVBoxLayout(self.rule_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("规则管理")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        # 统计栏
        self.rule_stats_label = QLabel("规则统计: loading")
        self.rule_stats_label.setWordWrap(True)
        self.rule_stats_label.setStyleSheet(
            "background-color: #111111; color: #9cdcfe; border: 1px solid #333333; padding: 6px; font-weight: bold;"
        )
        panel_layout.addWidget(self.rule_stats_label)

        # 搜索框
        search_row = QHBoxLayout()
        self.rule_search_edit = QLineEdit()
        self.rule_search_edit.setPlaceholderText("搜索规则...")
        self.rule_search_edit.setStyleSheet(
            "QLineEdit { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
        )
        self.rule_search_edit.returnPressed.connect(self._refresh_rule_list)
        search_row.addWidget(self.rule_search_edit)

        btn_search = QPushButton("搜索")
        btn_search.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_search.clicked.connect(self._refresh_rule_list)
        search_row.addWidget(btn_search)
        panel_layout.addLayout(search_row)

        # 过滤 radio
        filter_row = QHBoxLayout()
        self.rb_rule_all = QRadioButton("全部")
        self.rb_rule_all.setChecked(True)
        self.rb_rule_all.setStyleSheet("color: #cccccc;")
        self.rb_rule_enabled = QRadioButton("已启用")
        self.rb_rule_enabled.setStyleSheet("color: #cccccc;")
        self.rb_rule_disabled = QRadioButton("已禁用")
        self.rb_rule_disabled.setStyleSheet("color: #cccccc;")
        self.rb_rule_group = QButtonGroup(self)
        self.rb_rule_group.setExclusive(True)
        self.rb_rule_group.addButton(self.rb_rule_all)
        self.rb_rule_group.addButton(self.rb_rule_enabled)
        self.rb_rule_group.addButton(self.rb_rule_disabled)
        for rb in [self.rb_rule_all, self.rb_rule_enabled, self.rb_rule_disabled]:
            rb.toggled.connect(self._refresh_rule_list)
            filter_row.addWidget(rb)
        filter_row.addStretch(1)
        panel_layout.addLayout(filter_row)

        # 规则表格
        self.rule_table = QTableWidget(self.rule_panel)
        self.rule_table.setColumnCount(9)
        self.rule_table.setHorizontalHeaderLabels(
            ["ID", "场景", "元素", "动作", "作用", "置信度", "命中", "启用", "来源"]
        )
        self.rule_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rule_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.rule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rule_table.setColumnWidth(0, 40)
        self.rule_table.setColumnWidth(1, 90)
        self.rule_table.setColumnWidth(2, 90)
        self.rule_table.setColumnWidth(3, 60)
        self.rule_table.setColumnWidth(4, 80)
        self.rule_table.setColumnWidth(5, 50)
        self.rule_table.setColumnWidth(6, 40)
        self.rule_table.setColumnWidth(7, 40)
        self.rule_table.horizontalHeader().setStretchLastSection(True)
        self.rule_table.itemDoubleClicked.connect(self._open_rule_edit_dialog)
        self.rule_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rule_table.customContextMenuRequested.connect(self._show_rule_context_menu)
        panel_layout.addWidget(self.rule_table, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._refresh_rule_list)
        btn_row.addWidget(btn_refresh)

        btn_add = QPushButton("新建")
        btn_add.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_add.clicked.connect(self._open_rule_create_dialog)
        btn_row.addWidget(btn_add)
        btn_row.addStretch(1)
        panel_layout.addLayout(btn_row)

        layout.insertWidget(4, self.rule_panel)
        self.rule_panel.setVisible(False)

    def _refresh_rule_list(self):
        if not getattr(self, "rule_table", None):
            return
        self.rule_table.setRowCount(0)
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            search = self.rule_search_edit.text().strip() if getattr(self, "rule_search_edit", None) else ""
            if self.rb_rule_enabled.isChecked():
                filter_enabled = True
            elif self.rb_rule_disabled.isChecked():
                filter_enabled = False
            else:
                filter_enabled = None
            rules = dm.list_all_runtime_rules(search=search, filter_enabled=filter_enabled)
            stats = dm.get_runtime_rule_stats()
            self.rule_stats_label.setText(
                f"总计 {stats['total']} | 已启用 {stats['enabled']} | "
                f"已禁用 {stats['disabled']} | 总命中 {stats['total_hits']}"
            )
            self.rule_table.setRowCount(len(rules))
            for row, rule in enumerate(rules):
                self.rule_table.setItem(row, 0, QTableWidgetItem(str(rule["id"])))
                self.rule_table.setItem(row, 1, QTableWidgetItem(rule["scene_key"] or ""))
                self.rule_table.setItem(row, 2, QTableWidgetItem(rule["element_name"] or ""))
                self.rule_table.setItem(row, 3, QTableWidgetItem(rule["action_type"] or ""))
                self.rule_table.setItem(row, 4, QTableWidgetItem(rule["action_effect"] or ""))
                conf_item = QTableWidgetItem(f"{rule['confidence']:.2f}" if rule.get('confidence') else "-")
                self.rule_table.setItem(row, 5, conf_item)
                self.rule_table.setItem(row, 6, QTableWidgetItem(str(rule.get("hits", 0))))
                enabled_item = QTableWidgetItem("是" if rule.get("enabled") else "否")
                if not rule.get("enabled"):
                    enabled_item.setForeground(QBrush(QColor("#f44747")))
                self.rule_table.setItem(row, 7, enabled_item)
                self.rule_table.setItem(row, 8, QTableWidgetItem(rule["source"] or ""))
                # 存储 rule_id
                for col in range(9):
                    item = self.rule_table.item(row, col)
                    if item:
                        item.setData(256, rule["id"])
                # 禁用行整体变灰
                if not rule.get("enabled"):
                    for col in range(9):
                        item = self.rule_table.item(row, col)
                        if item:
                            item.setForeground(QBrush(QColor("#888888")))
        except Exception as e:
            LogManager().append(f"[RulePanel] 刷新规则列表失败: {e}")
            self.rule_stats_label.setText(f"加载失败: {e}")

    def _show_rule_context_menu(self, position):
        item = self.rule_table.itemAt(position)
        if not item:
            return
        rule_id = item.data(256)
        if not rule_id:
            return
        menu = QMenu(self)
        action_edit = menu.addAction("编辑")
        action_toggle = menu.addAction("启用/禁用")
        action_delete = menu.addAction("删除")
        action = menu.exec(self.rule_table.viewport().mapToGlobal(position))
        if action == action_edit:
            self._open_rule_edit_dialog_by_id(rule_id)
        elif action == action_toggle:
            self._toggle_rule_enabled(rule_id)
        elif action == action_delete:
            self._delete_rule(rule_id)

    def _toggle_rule_enabled(self, rule_id: int):
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            rule = dm.get_runtime_rule(rule_id)
            if rule is None:
                return
            dm.toggle_runtime_rule_enabled(rule_id, not rule.get("enabled", True))
            self._refresh_rule_list()
        except Exception as e:
            LogManager().append(f"[RulePanel] 切换启用状态失败: {e}")

    def _delete_rule(self, rule_id: int):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除规则 #{rule_id} 吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            if dm.delete_runtime_rule(rule_id):
                self._refresh_rule_list()
        except Exception as e:
            LogManager().append(f"[RulePanel] 删除规则失败: {e}")

    def _open_rule_edit_dialog(self, item: QTableWidgetItem):
        rule_id = item.data(256)
        if rule_id:
            self._open_rule_edit_dialog_by_id(rule_id)

    def _open_rule_edit_dialog_by_id(self, rule_id: int):
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            rule = dm.get_runtime_rule(rule_id)
            if rule is None:
                return
            dialog = RuleEditDialog(rule, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                data = dialog.get_data()
                dm.update_runtime_rule(
                    rule_id=rule_id,
                    element_name=data.get("element_name"),
                    action_type=data.get("action_type"),
                    action_effect=data.get("action_effect"),
                    user_intent=data.get("user_intent"),
                    bbox_xyxy=data.get("bbox_xyxy"),
                    next_scene_key=data.get("next_scene_key"),
                    confidence=data.get("confidence"),
                    enabled=data.get("enabled"),
                )
                self._refresh_rule_list()
        except Exception as e:
            LogManager().append(f"[RulePanel] 打开编辑对话框失败: {e}")

    def _open_rule_create_dialog(self):
        # 新建规则：使用空数据，rule_id=None
        dummy_rule = {
            "id": None,
            "rule_key": "",
            "scene_key": "",
            "element_name": "",
            "action_type": "tap",
            "action_effect": "",
            "user_intent": "",
            "bbox_xyxy": [0, 0, 100, 100],
            "next_scene_key": "",
            "confidence": 0.9,
            "enabled": True,
            "source": "manual",
        }
        dialog = RuleEditDialog(dummy_rule, self, is_create=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                from agent_data import AgentDataManager
                dm = AgentDataManager()
                # 生成 rule_key
                rule_key = data.get("rule_key") or "|".join([
                    data.get("scene_key", ""),
                    data.get("action_type", "tap"),
                    data.get("element_name", ""),
                    data.get("next_scene_key", ""),
                ])
                dm.upsert_runtime_rule(
                    rule_key=rule_key,
                    scene_id=None,
                    scene_key=data.get("scene_key", ""),
                    element_id=None,
                    element_name=data.get("element_name", ""),
                    action_type=data.get("action_type", "tap"),
                    action_effect=data.get("action_effect", ""),
                    user_intent=data.get("user_intent", ""),
                    bbox_xyxy=data.get("bbox_xyxy", [0, 0, 100, 100]),
                    next_scene_id=None,
                    next_scene_key=data.get("next_scene_key", ""),
                    source_event="manual_create",
                    source="manual",
                    confidence=data.get("confidence", 0.9),
                )
                # 更新 enabled 状态
                conn = sqlite3.connect(str(dm.db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE runtime_rule SET enabled = ? WHERE rule_key = ?",
                    (1 if data.get("enabled", True) else 0, rule_key),
                )
                conn.commit()
                conn.close()
                self._refresh_rule_list()
            except Exception as e:
                LogManager().append(f"[RulePanel] 创建规则失败: {e}")

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
        stats = {"total": 0, "pending": 0, "processing": 0, "approved": 0, "rule_hits": 0, "runtime_indexed": 0, "recorded": 0, "boxes": 0}
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
                    stats["total"] += 1
                    action_type = data.get("action_type", "physical")
                    status = data.get("status", folder.parent.name if folder.parent != root else "")
                    if status in ("raw_captured", "needs_model_or_manual", "review_pending", "event_unknown"):
                        stats["pending"] += 1
                    elif status == "processing":
                        stats["processing"] += 1
                    elif status == "review_approved":
                        stats["approved"] += 1
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
                    stats["boxes"] += obj_count
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
                    badges = []
                    if data.get("click_target", {}).get("status") == "runtime_rule_matched":
                        stats["rule_hits"] += 1
                    runtime_stats = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
                    if runtime_stats.get("elements", 0) or runtime_stats.get("rules", 0):
                        stats["runtime_indexed"] += 1
                    if isinstance(data.get("recording"), dict) and data["recording"].get("video_offset_ms") is not None:
                        stats["recorded"] += 1
                    click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
                    if click_target.get("status") == "runtime_rule_matched":
                        badges.append(f"规则:{click_target.get('element_name', '') or 'hit'}")
                    runtime_index = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
                    if runtime_index:
                        badges.append(f"索引:E{runtime_index.get('elements', 0)}/R{runtime_index.get('rules', 0)}")
                    recording = data.get("recording", {}) if isinstance(data.get("recording"), dict) else {}
                    if recording.get("video_offset_ms") is not None:
                        badges.append(f"录像@{self._format_seconds(recording.get('video_offset_ms'))}")
                    if badges:
                        item.setText(item.text() + "  |  " + "  ".join(badges))
                    item.setData(256, {"type": "physical_folder", "folder": str(folder)})
                    self.list_events.addItem(item)
                    added += 1

            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            if not db_path.exists():
                self._update_event_stats_label(stats)
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
                self._update_event_stats_label(stats)
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
            self._update_event_stats_label(stats)
        except Exception as e:
            LogManager().append(f"[Event] 刷新事件列表失败: {e}")
            self.list_events.addItem(f"刷新失败: {e}")

    def _on_event_search_changed(self, text: str):
        text = text.strip().lower()
        for i in range(self.list_events.count()):
            item = self.list_events.item(i)
            if item:
                item.setHidden(bool(text) and text not in item.text().lower())

    def _update_event_stats_label(self, stats: dict):
        label = getattr(self, "event_stats_label", None)
        if not label:
            return
        text = (
            f"事件 {stats.get('total', 0)} | 待审核 {stats.get('pending', 0)} | "
            f"处理中 {stats.get('processing', 0)} | 已审核 {stats.get('approved', 0)}\n"
            f"规则命中 {stats.get('rule_hits', 0)} | 已编译 {stats.get('runtime_indexed', 0)} | "
            f"录像同步 {stats.get('recorded', 0)} | 框 {stats.get('boxes', 0)}"
        )
        label.setText(text)
        if stats.get("pending", 0) > 0:
            color = "#ffcc00"
        elif stats.get("rule_hits", 0) or stats.get("runtime_indexed", 0):
            color = "#4ec9b0"
        else:
            color = "#dcdcaa"
        label.setStyleSheet(
            f"background-color: #111111; color: {color}; border: 1px solid #333333; "
            "padding: 6px; font-weight: bold;"
        )

    def _build_event_video_player(self, recording: dict, parent=None):
        if not isinstance(recording, dict):
            return None
        video_path = recording.get("video_path") or ""
        offset_ms = recording.get("video_offset_ms")
        if not video_path or offset_ms is None:
            return None

        video_file = Path(video_path)
        box = QWidget(parent)
        box.setStyleSheet("background-color: #151515; border: 1px solid #333333;")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel(f"视频回放 @{self._format_seconds(offset_ms)}")
        title.setStyleSheet("color: #9cdcfe; font-weight: bold; border: none;")
        layout.addWidget(title)

        if not video_file.exists():
            missing = QLabel(f"视频不存在\n{video_file.name}")
            missing.setWordWrap(True)
            missing.setStyleSheet("color: #f44747; border: none;")
            layout.addWidget(missing)
            return box

        video = QVideoWidget(box)
        video.setMinimumHeight(116)
        video.setStyleSheet("background-color: #000000; border: 1px solid #222222;")
        layout.addWidget(video)

        player = QMediaPlayer(box)
        audio = QAudioOutput(box)
        audio.setVolume(0.0)
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        player.setSource(QUrl.fromLocalFile(str(video_file.resolve())))
        box._player = player
        box._audio = audio

        controls = QHBoxLayout()
        btn_jump = QPushButton("跳到事件", box)
        btn_play = QPushButton("播放", box)
        btn_pause = QPushButton("暂停", box)
        for btn in [btn_jump, btn_play, btn_pause]:
            btn.setStyleSheet(
                "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
                "QPushButton:hover { background-color: #505050; }"
            )
            controls.addWidget(btn)
        layout.addLayout(controls)

        def jump_to_event():
            player.pause()
            player.setPosition(max(0, int(offset_ms)))

        btn_jump.clicked.connect(jump_to_event)
        btn_play.clicked.connect(player.play)
        btn_pause.clicked.connect(player.pause)
        QTimer.singleShot(350, jump_to_event)
        return box

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

        summary_row = QHBoxLayout()
        summary_row.setSpacing(6)

        def add_badge(text: str, color: str = "#9cdcfe"):
            badge = QLabel(text)
            badge.setStyleSheet(
                f"background-color: #252526; color: {color}; border: 1px solid #3c3c3c; "
                "padding: 5px 8px; font-weight: bold;"
            )
            summary_row.addWidget(badge)

        scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
        click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
        recording = data.get("recording", {}) if isinstance(data.get("recording"), dict) else {}
        runtime_index = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
        add_badge(f"状态: {data.get('status', 'unknown')}", "#dcdcaa")
        add_badge(f"操作: {data.get('action_type', '-')}", "#cccccc")
        if scene:
            add_badge(f"场景: {scene.get('scene_key') or '-'}", "#4ec9b0" if scene.get("matched") else "#ffcc00")
        if click_target:
            target_text = click_target.get("element_name") or click_target.get("status") or "-"
            color = "#4ec9b0" if click_target.get("status") == "runtime_rule_matched" else "#9cdcfe"
            add_badge(f"目标: {target_text}", color)
        if runtime_index:
            add_badge(f"索引: E{runtime_index.get('elements', 0)} R{runtime_index.get('rules', 0)}", "#4ec9b0")
        if recording.get("video_offset_ms") is not None:
            add_badge(f"录像: {recording.get('kind', '')} @{self._format_seconds(recording.get('video_offset_ms'))}", "#9cdcfe")
        summary_row.addStretch(1)
        layout.addLayout(summary_row)

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

        if folder.name.startswith("physical_"):
            actions_row = QHBoxLayout()
            btn_approve = QPushButton("Approve + Train", left_panel)
            btn_approve.setEnabled(data.get("status") != "review_approved")
            btn_approve.setToolTip("Approve this YOLO candidate, add it to the training set, then start YOLO training.")
            btn_approve.clicked.connect(lambda checked=False, f=folder: self._approve_physical_event(f))
            actions_row.addWidget(btn_approve)
            left_layout.addLayout(actions_row)
        video_panel = self._build_event_video_player(recording, left_panel)
        if video_panel is not None:
            left_layout.addWidget(video_panel)

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
            replacement = AnnotatedImageLabel(folder / name, label, touch, yolo, data, detail_holder)
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
        if self._video_writer is not None:
            now = time.perf_counter()
            min_interval = 1.0 / max(1, self._record_fps)
            if not self._record_last_frame_perf or now - self._record_last_frame_perf >= min_interval:
                try:
                    self._video_writer.write(frame)
                    self._record_frame_count += 1
                    self._record_last_frame_perf = now
                except Exception as e:
                    LogManager().append(f"[WARN] manual recording frame write failed: {e}")
        self._update_video_feedback_overlay()

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
            self._unknown_processor = UnknownFolderProcessor(interval=5, allow_cloud_fallback=True)
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

    def _set_runtime_feedback_slot(self, payload):
        self._last_ui_feedback = payload if isinstance(payload, dict) else {}
        self._update_video_feedback_overlay()

    def _format_seconds(self, ms) -> str:
        try:
            return f"{int(ms) / 1000:.1f}s"
        except Exception:
            return "-"

    def _update_video_feedback_overlay(self):
        if not self.video_widget or not hasattr(self.video_widget, "set_status_lines"):
            return
        lines = []
        ctx = self._active_recording_context() if hasattr(self, "_active_recording_context") else {}
        if ctx:
            kind = "手动" if ctx.get("kind") == "manual" else "Session"
            lines.append(f"录像 {kind} @{self._format_seconds(ctx.get('video_offset_ms'))}")
        feedback = self._last_ui_feedback or {}
        rule = feedback.get("rule") or ""
        if rule:
            lines.append(f"规则 {rule}")
        scene = feedback.get("scene") or ""
        if scene:
            lines.append(f"场景 {scene}")
        status = feedback.get("status") or ""
        if status:
            lines.append(str(status))
        self.video_widget.set_status_lines(lines)
        if getattr(self, "runtime_feedback_label", None):
            text = " | ".join(lines) if lines else "Runtime: waiting"
            self.runtime_feedback_label.setText(text)
            color = "#4ec9b0" if any(line.startswith("规则") for line in lines) else "#9cdcfe"
            self.runtime_feedback_label.setStyleSheet(
                f"background-color: #111111; color: {color}; border: 1px solid #333333; "
                "padding: 6px; font-weight: bold;"
            )

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
            for obj in data.get("yolo_detected_objects", {}).get("objects", []):
                name = obj.get("class_name") or obj.get("name")
                bbox = obj.get("bbox_xyxy")
                if not name or not bbox or len(bbox) != 4:
                    continue
                objects.append({
                    "class_name": name,
                    "bbox_xyxy": bbox,
                    "source": "trained_yolo",
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

            return {
                "status": "candidate",
                "review_state": "pending",
                "class_id": normalized_objects[0]["class_id"] if normalized_objects else 0,
                "class_name": normalized_objects[0]["class_name"] if normalized_objects else class_name,
                "image_width": width,
                "image_height": height,
                "bbox_xyxy": normalized_objects[0]["bbox_xyxy"] if normalized_objects else [int(x1), int(y1), int(x2), int(y2)],
                "objects": normalized_objects,
                "label": label_text.strip(),
                "local_image": str(local_image),
                "local_label": str(local_label),
            }
        except Exception as e:
            LogManager().append(f"[WARN] write yolo annotation failed: {e}")
            return {"error": str(e)}

    def _promote_yolo_event_annotation(self, op_dir: Path, data: dict) -> dict:
        try:
            import shutil
            from datetime import datetime
            from agent_data import GAME_DATA_DIR

            yolo = data.get("yolo") if isinstance(data.get("yolo"), dict) else {}
            local_image_value = yolo.get("local_image") or ""
            local_label_value = yolo.get("local_label") or ""
            local_image = Path(local_image_value) if local_image_value else None
            local_label = Path(local_label_value) if local_label_value else None
            if local_image is None or local_label is None or not local_image.exists() or not local_label.exists():
                yolo = self._write_yolo_event_annotation(op_dir, data)
                local_image_value = yolo.get("local_image") or ""
                local_label_value = yolo.get("local_label") or ""
                local_image = Path(local_image_value) if local_image_value else None
                local_label = Path(local_label_value) if local_label_value else None
            if local_image is None or local_label is None or not local_image.exists() or not local_label.exists():
                return {"status": "error", "error": "local yolo candidate missing"}

            event_key = op_dir.name
            dataset_images = GAME_DATA_DIR / "yolo_events" / "images" / "train"
            dataset_labels = GAME_DATA_DIR / "yolo_events" / "labels" / "train"
            dataset_images.mkdir(parents=True, exist_ok=True)
            dataset_labels.mkdir(parents=True, exist_ok=True)

            dataset_image = dataset_images / f"{event_key}{local_image.suffix or '.png'}"
            dataset_label = dataset_labels / f"{event_key}.txt"
            shutil.copy2(str(local_image), str(dataset_image))
            shutil.copy2(str(local_label), str(dataset_label))
            (GAME_DATA_DIR / "yolo_events" / "classes.txt").write_text(
                self._yolo_classes_text(),
                encoding="utf-8",
            )
            (GAME_DATA_DIR / "yolo_events" / "data.yaml").write_text(
                self._yolo_data_yaml(),
                encoding="utf-8",
            )

            promoted = dict(yolo)
            promoted.update({
                "status": "approved",
                "review_state": "approved",
                "approved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "dataset_image": str(dataset_image),
                "dataset_label": str(dataset_label),
            })
            return promoted
        except Exception as e:
            LogManager().append(f"[WARN] promote yolo annotation failed: {e}")
            return {"status": "error", "error": str(e)}

    def _approve_physical_event(self, folder: Path):
        index_path = folder / "index.json"
        if not index_path.exists():
            self._set_status(f"YOLO review: index not found {folder.name}")
            return
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            promoted = self._promote_yolo_event_annotation(folder, data)
            if promoted.get("status") == "error":
                self._set_status(f"YOLO review: approve failed - {promoted.get('error')}")
                return

            data["yolo"] = promoted
            data["status"] = "review_approved"
            index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            try:
                from agent_data import AgentDataManager

                AgentDataManager().record_physical_event(
                    event_key=folder.name,
                    action_type=data.get("action_type", ""),
                    timestamp_ms=int(time.time() * 1000),
                    duration_ms=int(data.get("duration_ms") or 0),
                    touch=data.get("touch", {}),
                    folder_path=folder,
                    images=data.get("images", {}),
                    index_path=index_path,
                    yolo=promoted,
                )
            except Exception as e:
                LogManager().append(f"[WARN] update approved physical event db failed: {e}")

            self._set_status(f"YOLO review: approved {folder.name}, training started")
            self._bridge.events_changed.emit()
            self._open_physical_event_tab(folder)
            self._start_yolo_training_async()
        except Exception as e:
            self._set_status(f"YOLO review: approve failed - {e}")

    def _start_yolo_training_async(self):
        def _train():
            try:
                from agent_data import GAME_DATA_DIR
                from ultralytics import YOLO

                yolo_dir = GAME_DATA_DIR / "yolo_events"
                data_yaml = yolo_dir / "data.yaml"
                if not data_yaml.exists():
                    LogManager().append("[YOLO] skip train: data.yaml missing")
                    return
                label_count = len(list((yolo_dir / "labels" / "train").glob("*.txt")))
                if label_count <= 0:
                    LogManager().append("[YOLO] skip train: no approved labels")
                    return

                best = yolo_dir / "runs" / "train" / "weights" / "best.pt"
                model_path = str(best) if best.exists() else "yolo11n.pt"
                LogManager().append(f"[YOLO] train start labels={label_count} model={model_path}")
                model = YOLO(model_path)
                model.train(
                    data=str(data_yaml),
                    epochs=20,
                    imgsz=640,
                    project=str(yolo_dir / "runs"),
                    name="train",
                    exist_ok=True,
                )
                LogManager().append("[YOLO] train done")
            except ImportError:
                LogManager().append("[YOLO] ultralytics not installed; run: pip install ultralytics")
            except Exception as e:
                LogManager().append(f"[YOLO] train failed: {e}")

        threading.Thread(target=_train, daemon=True).start()
    def _compile_runtime_index_from_review(
        self,
        folder: Path,
        data: dict,
        image_path: Path,
        approved_objects: list[dict],
        source: str = "human_review",
    ) -> dict:
        """Write approved scene UI and action hints into the realtime SQLite index."""
        try:
            from PIL import Image
            from agent_data import AgentDataManager
            from scene_index import image_fingerprint

            dm = AgentDataManager()
            scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
            after_scene = data.get("after_scene_index", {}) if isinstance(data.get("after_scene_index"), dict) else {}
            scene_id = scene.get("scene_id") if scene.get("matched") else None
            scene_key = scene.get("scene_key") or folder.name
            next_scene_id = after_scene.get("scene_id") if after_scene.get("matched") else None
            next_scene_key = after_scene.get("scene_key") or ""
            user_intent = str(data.get("gpt_user_intent") or "").strip()
            action_type = str(data.get("action_type") or "tap").strip()
            click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}

            compiled_elements = 0
            compiled_rules = 0
            crop_dir = folder / "runtime_crops"
            crop_dir.mkdir(parents=True, exist_ok=True)

            with Image.open(image_path).convert("RGB") as img:
                width, height = img.size
                for idx, obj in enumerate(approved_objects):
                    bbox = obj.get("bbox_xyxy") or []
                    if len(bbox) != 4:
                        continue
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    x1 = max(0, min(width - 1, x1))
                    y1 = max(0, min(height - 1, y1))
                    x2 = max(x1 + 1, min(width, x2))
                    y2 = max(y1 + 1, min(height, y2))
                    class_name = self._safe_yolo_class_name(obj.get("class_name") or "ui_element")
                    crop_path = crop_dir / f"{idx + 1:03d}_{class_name}.png"
                    img.crop((x1, y1, x2, y2)).save(str(crop_path))
                    fingerprint = image_fingerprint(crop_path)
                    class_id = int(obj.get("class_id") if obj.get("class_id") is not None else self._ensure_yolo_class(class_name))
                    confidence = float(obj.get("confidence") or 0.9)
                    role = str(obj.get("role") or "ui_element")
                    action_effect = str(obj.get("action_effect") or click_target.get("action_effect") or "")
                    element_id = dm.upsert_ui_element(
                        scene_id=scene_id,
                        scene_key=scene_key,
                        element_type=role,
                        element_name=class_name,
                        text=str(obj.get("name") or obj.get("text") or ""),
                        bbox_xyxy=[x1, y1, x2, y2],
                        source=source,
                        confidence=confidence,
                        fingerprint=fingerprint,
                        image_path=crop_path,
                        yolo_class_id=class_id,
                        action_effect=action_effect,
                    )
                    compiled_elements += 1

                    is_clicked = role == "clicked_target"
                    if not is_clicked:
                        tx = data.get("touch", {}).get("frame_start", {}).get("x")
                        ty = data.get("touch", {}).get("frame_start", {}).get("y")
                        try:
                            is_clicked = x1 <= int(tx) <= x2 and y1 <= int(ty) <= y2
                        except Exception:
                            is_clicked = False
                    if is_clicked or action_effect:
                        rule_key = "|".join([
                            str(scene_id or scene_key),
                            action_type,
                            class_name,
                            str(next_scene_id or next_scene_key),
                        ])
                        dm.upsert_runtime_rule(
                            rule_key=rule_key,
                            scene_id=scene_id,
                            scene_key=scene_key,
                            element_id=element_id,
                            element_name=class_name,
                            action_type=action_type,
                            action_effect=action_effect,
                            user_intent=user_intent,
                            bbox_xyxy=[x1, y1, x2, y2],
                            next_scene_id=next_scene_id,
                            next_scene_key=next_scene_key,
                            source_event=folder.name,
                            source=source,
                            confidence=confidence,
                        )
                        compiled_rules += 1

            return {"elements": compiled_elements, "rules": compiled_rules}
        except Exception as e:
            LogManager().append(f"[RuntimeIndex] compile failed {folder.name}: {e}")
            return {"error": str(e), "elements": 0, "rules": 0}

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
        from yolo_class_manager import YoloClassManager

        mgr = YoloClassManager(GAME_DATA_DIR / "yolo_events" / "classes.txt")
        return mgr.ensure(class_name)

    def _yolo_classes_text(self) -> str:
        from agent_data import GAME_DATA_DIR
        from yolo_class_manager import YoloClassManager
        mgr = YoloClassManager(GAME_DATA_DIR / "yolo_events" / "classes.txt")
        return "\n".join(mgr.names) + "\n"

    def _yolo_data_yaml(self) -> str:
        from agent_data import GAME_DATA_DIR
        from yolo_class_manager import YoloClassManager
        mgr = YoloClassManager(GAME_DATA_DIR / "yolo_events" / "classes.txt")
        return mgr.to_data_yaml()

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

    def _detect_yolo_objects(self, op_dir: Path, data: dict) -> dict:
        try:
            from agent_data import GAME_DATA_DIR
            from ultralytics import YOLO

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"status": "no_before_image", "objects": []}
            before_path = op_dir / before_name
            if not before_path.exists():
                return {"status": "before_image_missing", "objects": []}

            model_path = GAME_DATA_DIR / "yolo_events" / "runs" / "train" / "weights" / "best.pt"
            if not model_path.exists():
                return {"status": "no_model", "objects": []}

            model = YOLO(str(model_path))
            results = model.predict(str(before_path), conf=0.25, verbose=False)
            objects = []
            for result in results:
                names = getattr(result, "names", {}) or {}
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    xyxy = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0].item()) if box.cls is not None else 0
                    conf = float(box.conf[0].item()) if box.conf is not None else 0.0
                    objects.append({
                        "class_id": cls_id,
                        "class_name": str(names.get(cls_id, f"class_{cls_id}")),
                        "bbox_xyxy": [int(v) for v in xyxy],
                        "confidence": round(conf, 4),
                        "source": "yolo",
                    })
            return {"status": "ok", "model": str(model_path), "objects": objects}
        except ImportError:
            return {"status": "ultralytics_missing", "objects": []}
        except Exception as e:
            LogManager().append(f"[WARN] yolo detect failed: {e}")
            return {"status": "error", "objects": [], "error": str(e)}

    def _yolo_object_at_touch(self, data: dict, pad: int = 8) -> dict | None:
        touch = data.get("touch", {})
        start = touch.get("frame_start", {})
        try:
            x = int(start.get("x", 0))
            y = int(start.get("y", 0))
        except Exception:
            return None

        best = None
        for obj in data.get("detected_yolo_objects", {}).get("objects", []):
            bbox = obj.get("bbox_xyxy")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            if x1 - pad <= x <= x2 + pad and y1 - pad <= y <= y2 + pad:
                area = max(1, (x2 - x1) * (y2 - y1))
                score = float(obj.get("confidence") or 0.0)
                rank = (score, -area)
                if best is None or rank > best[0]:
                    best = (rank, obj)
        return best[1] if best else None

    def _detect_yolo_click_target(self, image_path: Path, data: dict) -> dict | None:
        try:
            from agent_data import GAME_DATA_DIR

            weights_dir = GAME_DATA_DIR / "yolo_events" / "runs" / "detect" / "train" / "weights"
            model_path = weights_dir / "best.pt"
            if not model_path.exists():
                model_path = weights_dir / "last.pt"
            if not model_path.exists():
                return None
            try:
                from ultralytics import YOLO
            except Exception:
                return None

            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            model = YOLO(str(model_path))
            results = model.predict(str(image_path), conf=0.25, verbose=False)
            if not results:
                return None
            names = getattr(results[0], "names", {}) or {}
            objects = []
            best = None
            boxes = getattr(results[0], "boxes", None)
            if boxes is None:
                return None
            for box in boxes:
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = [int(v) for v in xyxy]
                conf = float(box.conf[0]) if getattr(box, "conf", None) is not None else 0.0
                class_id = int(box.cls[0]) if getattr(box, "cls", None) is not None else 0
                class_name = str(names.get(class_id, f"class_{class_id}"))
                obj = {
                    "class_id": class_id,
                    "class_name": class_name,
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "confidence": conf,
                    "source": "trained_yolo",
                }
                objects.append(obj)
                if x1 <= click_x <= x2 and y1 <= click_y <= y2:
                    area = max(1, (x2 - x1) * (y2 - y1))
                    score = conf / area
                    if best is None or score > best[0]:
                        best = (score, obj)
            if not best:
                return None
            obj = best[1]
            return {
                "status": "yolo_matched",
                "element_name": obj["class_name"],
                "element_type": "ui_element",
                "action_effect": "",
                "bbox_xyxy": obj["bbox_xyxy"],
                "confidence": obj["confidence"],
                "model_path": str(model_path),
                "objects": objects,
            }
        except Exception as e:
            LogManager().append(f"[YOLO] click detect failed: {e}")
            return None

    def _analyze_click_target(self, op_dir: Path, data: dict, scene_result: dict | None, collect_debug: bool = False) -> dict:
        debug_info = {
            "scene_result": scene_result,
            "click": {},
            "steps": [],
        }
        try:
            from PIL import Image
            from scene_index import image_fingerprint
            from agent_data import AgentDataManager

            before_name = data.get("images", {}).get("before")
            if not before_name:
                result = {"status": "no_before_image"}
                if collect_debug:
                    result["_debug"] = debug_info
                return result
            before_path = op_dir / before_name
            if not before_path.exists():
                result = {"status": "before_image_missing"}
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            debug_info["click"] = {"x": click_x, "y": click_y}
            dm = AgentDataManager()

            # Step 1: Runtime Rule
            step_rules = {
                "name": "runtime_rule",
                "candidates": [],
                "matched": False,
            }
            matched_rule = None
            if scene_result and scene_result.get("matched"):
                rules = dm.list_runtime_rules_for_scene(
                    scene_id=scene_result.get("scene_id"),
                    scene_key=scene_result.get("scene_key", ""),
                )
                for rule in rules:
                    bbox = rule.get("bbox_xyxy") or []
                    candidate = {
                        "id": rule.get("id"),
                        "element_name": rule.get("element_name") or "tap_target",
                        "bbox_xyxy": bbox,
                        "confidence": rule.get("confidence") or 0.9,
                        "hits": rule.get("hits", 0),
                        "enabled": rule.get("enabled", True),
                    }
                    if len(bbox) != 4:
                        candidate["reason"] = "invalid_bbox"
                        step_rules["candidates"].append(candidate)
                        continue
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    candidate["contains_click"] = x1 <= click_x <= x2 and y1 <= click_y <= y2
                    step_rules["candidates"].append(candidate)
                    if candidate["contains_click"] and matched_rule is None:
                        matched_rule = rule
                        step_rules["matched"] = True
            debug_info["steps"].append(step_rules)

            if matched_rule:
                rule = matched_rule
                bbox = rule.get("bbox_xyxy") or []
                result = {
                    "status": "runtime_rule_matched",
                    "rule_id": rule.get("id"),
                    "element_id": rule.get("element_id"),
                    "element_name": rule.get("element_name") or "tap_target",
                    "element_type": "runtime_rule",
                    "action_effect": rule.get("action_effect") or "",
                    "user_intent": rule.get("user_intent") or "",
                    "bbox_xyxy": bbox,
                    "confidence": rule.get("confidence") or 0.9,
                    "source_event": rule.get("source_event") or "",
                }
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            # Step 2: YOLO
            yolo_match = self._detect_yolo_click_target(before_path, data)
            step_yolo = {
                "name": "yolo",
                "matched": bool(yolo_match),
                "objects": yolo_match.get("objects", []) if yolo_match else [],
                "best_match": yolo_match if yolo_match else None,
            }
            debug_info["steps"].append(step_yolo)
            if yolo_match:
                data["yolo_detected_objects"] = {"objects": yolo_match.get("objects", [])}
                result = yolo_match
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            with Image.open(before_path).convert("RGB") as img:
                bbox = self._click_bbox(img.size, data)
                x1, y1, x2, y2 = bbox
                crop_dir = op_dir / "crops"
                crop_dir.mkdir(parents=True, exist_ok=True)
                crop_path = crop_dir / "click_target.png"
                img.crop((x1, y1, x2, y2)).save(str(crop_path))

            yolo_hit = self._yolo_object_at_touch(data)
            if yolo_hit:
                bbox = [int(v) for v in yolo_hit["bbox_xyxy"]]
                element_name = yolo_hit.get("class_name") or "tap_target"
                class_id = self._ensure_yolo_class(element_name)
                return {
                    "status": "yolo_matched",
                    "element_name": element_name,
                    "element_type": "ui_element",
                    "action_effect": "",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "source": "yolo",
                    "yolo_class_id": class_id,
                    "confidence": yolo_hit.get("confidence", 0.0),
                }

            fingerprint = image_fingerprint(crop_path)

            # Step 3: Hash
            matched = dm.find_ui_element_by_hash(fingerprint)
            step_hash = {
                "name": "hash",
                "matched": bool(matched),
                "fingerprint_summary": {k: str(v)[:32] for k, v in (fingerprint or {}).items()},
                "best_match": {
                    "id": matched.get("id"),
                    "element_name": matched.get("element_name"),
                    "confidence": matched.get("confidence"),
                } if matched else None,
            }
            debug_info["steps"].append(step_hash)
            if matched:
                result = {
                    "status": "hash_matched",
                    "element_id": matched["id"],
                    "element_name": matched.get("element_name") or "tap_target",
                    "action_effect": matched.get("action_effect") or "",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "hash": fingerprint,
                    "match_confidence": matched["confidence"],
                }
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            # Step 4: LLM
            llm_result = self._describe_click_target_with_llm(
                before_path,
                data,
                scene_result,
                fallback_crop_path=crop_path,
                fallback_bbox=bbox,
            )
            step_llm = {
                "name": "llm",
                "matched": False,
                "result_summary": {
                    "element_name": llm_result.get("element_name"),
                    "element_type": llm_result.get("element_type"),
                    "confidence": llm_result.get("confidence"),
                    "parse_ok": llm_result.get("parse_ok", False),
                    "error": llm_result.get("error"),
                },
            }
            element_name = (llm_result.get("element_name") or "").strip()
            if (
                not element_name
                or element_name == "tap_target"
                or llm_result.get("error")
                or not llm_result.get("parse_ok", False)
            ):
                step_llm["reason"] = "low_confidence_or_parse_error"
                debug_info["steps"].append(step_llm)
                result = {
                    "status": "needs_model_or_manual",
                    "reason": "click target was not confidently identified",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "hash": fingerprint,
                    "llm": llm_result,
                }
                if collect_debug:
                    result["_debug"] = debug_info
                return result
            step_llm["matched"] = True
            debug_info["steps"].append(step_llm)
            action_effect = llm_result.get("action_effect") or ""
            precise_bbox = llm_result.get("bbox_xyxy")
            if precise_bbox and len(precise_bbox) == 4:
                bbox = [int(v) for v in precise_bbox]
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
            result = {
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
            if collect_debug:
                result["_debug"] = debug_info
            return result
        except Exception as e:
            LogManager().append(f"[WARN] analyze click target failed: {e}")
            result = {"status": "error", "error": str(e)}
            if collect_debug:
                result["_debug"] = debug_info
            return result

    def _describe_click_target_with_llm(
        self,
        image_path: Path,
        data: dict,
        scene_result: dict | None,
        fallback_crop_path: Path | None = None,
        fallback_bbox: list[int] | None = None,
    ) -> dict:
        try:
            from llm_client import QwenVLClient
            from PIL import Image

            scene_text = ""
            if scene_result:
                scene_text = scene_result.get("description") or scene_result.get("scene_key") or ""
            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            with Image.open(image_path) as img:
                width, height = img.size
            vision_width, vision_height = self._llm_vision_image_size(width, height)
            scale_x = width / max(1, vision_width)
            scale_y = height / max(1, vision_height)
            prompt = (
                "这是一张游戏截图。请根据用户点击点，精确找出被点击的 UI 元素完整边界。"
                "bbox_xyxy 必须使用原图像素坐标 [x1,y1,x2,y2]，要框住完整按钮/图标/可点击区域，"
                "不要只框点击点附近的小区域。"
                "只输出 JSON，不要解释："
                '{"element_name":"短名称","element_type":"button/icon/menu/item/unknown",'
                '"text":"图中可见文字，没有就空字符串","action_effect":"点击作用",'
                '"bbox_xyxy":[x1,y1,x2,y2],"confidence":0.0}'
                f"\n图像尺寸：{width}x{height}"
                f"\n用户点击点：({click_x},{click_y})"
                f"\n当前场景线索：{scene_text}"
            )
            raw = QwenVLClient().describe_image(image_path, prompt=prompt)
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
            bbox = parsed.get("bbox_xyxy") or parsed.get("bbox")
            if bbox and len(bbox) == 4:
                raw_x1, raw_y1, raw_x2, raw_y2 = [float(v) for v in bbox]
                x1 = int(round(raw_x1 * scale_x))
                y1 = int(round(raw_y1 * scale_y))
                x2 = int(round(raw_x2 * scale_x))
                y2 = int(round(raw_y2 * scale_y))
                parsed["bbox_xyxy_model"] = [raw_x1, raw_y1, raw_x2, raw_y2]
                parsed["bbox_xyxy"] = [
                    max(0, min(width - 1, x1)),
                    max(0, min(height - 1, y1)),
                    max(1, min(width, x2)),
                    max(1, min(height, y2)),
                ]
                if parsed["bbox_xyxy"][2] <= parsed["bbox_xyxy"][0] or parsed["bbox_xyxy"][3] <= parsed["bbox_xyxy"][1]:
                    parsed["bbox_xyxy"] = fallback_bbox or []
            elif fallback_bbox:
                parsed["bbox_xyxy"] = fallback_bbox
            parsed["parse_ok"] = bool(parsed)
            parsed["raw"] = raw[:500]
            parsed["source"] = "gpt-5.5"
            return parsed
        except Exception as e:
            if fallback_crop_path:
                try:
                    raw = QwenVLClient().describe_image(
                        fallback_crop_path,
                        prompt=(
                            "这是一张游戏截图中用户点击位置附近的局部裁剪图。"
                            "请判断被点击的图标/按钮是什么，以及点击它通常会产生什么作用。"
                            "只输出 JSON，不要解释："
                            '{"element_name":"短名称","element_type":"button/icon/menu/item/unknown",'
                            '"text":"图中可见文字，没有就空字符串","action_effect":"点击作用","confidence":0.0}'
                        ),
                    )
                    m = re.search(r"\{.*\}", raw, re.DOTALL)
                    parsed = json.loads(m.group(0)) if m else {}
                    parsed["bbox_xyxy"] = fallback_bbox or []
                    parsed["parse_ok"] = bool(parsed)
                    parsed["raw"] = raw[:500]
                    parsed["source"] = "gpt-5.5-crop-fallback"
                    return parsed
                except Exception:
                    pass
            return {
                "element_name": "tap_target",
                "element_type": "unknown",
                "action_effect": "",
                "bbox_xyxy": fallback_bbox or [],
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
            user_intent = ""
            if isinstance(parsed, dict):
                user_intent = str(parsed.get("user_intent") or "").strip()
                if user_intent:
                    LogManager().append(f"[GPT-5.5 Reanalyze] user_intent: {user_intent}")
                    data["gpt_user_intent"] = user_intent
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

    def _event_unknown_should_process(self, folder: Path, data: dict) -> bool:
        status = data.get("status", "")
        if status == "review_approved":
            return False

        attempts = int(data.get("auto_process_attempts") or 0)
        if status == "processing":
            try:
                stale = time.time() - folder.stat().st_mtime > 60
            except Exception:
                stale = True
            if stale:
                LogManager().append(f"[EventUnknown] recover stale processing event: {folder.name}")
                return True
            return False

        if status in ("raw_captured", "", None):
            return True

        if status == "needs_model_or_manual":
            return attempts < 2

        if status == "review_pending":
            scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
            yolo = data.get("gpt_yolo_objects", {}) if isinstance(data.get("gpt_yolo_objects"), dict) else {}
            click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
            needs_scene = not scene or (not scene.get("matched") and not scene.get("queued_unknown"))
            needs_intent = not str(data.get("gpt_user_intent") or "").strip()
            needs_objects = yolo.get("status") in ("", None, "empty", "error", "no_before_image", "before_image_missing")
            needs_click = click_target.get("status") == "needs_model_or_manual"
            return attempts < 1 and (needs_scene or needs_intent or needs_objects or needs_click)

        return False

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
        if not self._event_unknown_should_process(op_dir, data):
            return

        data["auto_process_attempts"] = int(data.get("auto_process_attempts") or 0) + 1
        data["auto_process_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
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

        data["detected_yolo_objects"] = self._detect_yolo_objects(op_dir, data)
        data["click_target"] = self._analyze_click_target(
            op_dir,
            data,
            data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
        )
        click_status = data.get("click_target", {}).get("status")
        if click_status == "runtime_rule_matched":
            if data["click_target"].get("user_intent"):
                data["gpt_user_intent"] = data["click_target"]["user_intent"]
            data["gpt_yolo_objects"] = {
                "status": "skipped_runtime_rule",
                "objects": [],
                "reason": "runtime rule matched",
            }
        elif click_status == "yolo_matched":
            data["gpt_yolo_objects"] = {"status": "skipped_yolo_hit", "objects": []}
        else:
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
        gpt_status = data.get("gpt_yolo_objects", {}).get("status") if isinstance(data.get("gpt_yolo_objects"), dict) else ""
        if click_status in ("error", "no_before_image", "before_image_missing"):
            target_status = "needs_model_or_manual"
        elif click_status == "needs_model_or_manual" and gpt_status not in ("ok",):
            target_status = "needs_model_or_manual"
        data["status"] = target_status
        index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        LogManager().append(f"[EventUnknown] 处理完成 {op_dir.name} -> {target_status}")
        scene_name = ""
        if isinstance(data.get("scene_index"), dict):
            scene_name = data["scene_index"].get("scene_key") or ""
        click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
        rule_name = click_target.get("element_name", "") if click_target.get("status") == "runtime_rule_matched" else ""
        self._bridge.overlay_changed.emit({
            "scene": scene_name,
            "rule": rule_name,
            "status": "规则命中" if rule_name else ("待审核" if target_status == "review_pending" else target_status),
        })
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
            recording_ctx = self._active_recording_context()
            if recording_ctx:
                data["recording"] = {
                    "kind": recording_ctx.get("kind", ""),
                    "video_path": recording_ctx.get("video_path", ""),
                    "events_path": recording_ctx.get("events_path", ""),
                    "meta_path": recording_ctx.get("meta_path", ""),
                    "video_offset_ms": recording_ctx.get("video_offset_ms"),
                    "started_timestamp_ms": recording_ctx.get("started_timestamp_ms"),
                    "session_id": recording_ctx.get("session_id", ""),
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
                self._append_recording_event(op_dir, data)
                self._bridge.overlay_changed.emit({"scene": "", "rule": "", "status": "待处理"})
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
            scene_name = ""
            if isinstance(data.get("scene_index"), dict):
                scene_name = data["scene_index"].get("scene_key") or ""
            click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
            click_status = click_target.get("status", "")
            rule_name = click_target.get("element_name", "") if click_status == "runtime_rule_matched" else ""
            self._bridge.overlay_changed.emit({
                "scene": scene_name,
                "rule": rule_name,
                "status": "规则命中" if rule_name else ("待审核" if data.get("status") == "raw_captured" else str(data.get("status", ""))),
            })
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
            self._append_recording_event(op_dir, data)
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
        is_yolo = getattr(self, "rb_audit_yolo", None) and self.rb_audit_yolo.isChecked()
        if getattr(self, "batch_btn_row", None):
            # 批量按钮只在 YOLO 模式下显示
            for i in range(self.batch_btn_row.count()):
                w = self.batch_btn_row.itemAt(i).widget()
                if w:
                    w.setVisible(is_yolo)
        if is_yolo:
            self._refresh_yolo_audit_list()
            return
        self.audit_list.setHeaderLabels(["场景", "类型", "命中", "模型", "状态", "创建时间"])
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

    def _open_audit_item(self, item: QTreeWidgetItem):
        item_type = item.data(0, 258)
        if item_type == "yolo_event":
            folder = item.data(0, 257)
            if folder:
                self._open_yolo_audit_tab(Path(folder))
            return
        self._open_audit_scene_tab(item)

    def _refresh_yolo_audit_list(self):
        self.audit_list.setHeaderLabels(["", "Event", "Action", "Boxes", "Status", "Source", "Runtime", "Recording", "Time"])
        self.audit_list.setColumnWidth(0, 28)
        show_approved = self.rb_approved.isChecked()
        roots = [Path("screenshots") / "event_unknown", Path("screenshots") / "event_review", Path("screenshots")]
        folders = []
        for root in roots:
            if not root.exists():
                continue
            folders.extend(
                p for p in root.iterdir()
                if p.is_dir() and p.name.startswith("physical_") and (p / "index.json").exists()
            )
        seen = set()
        unique = []
        for folder in folders:
            key = str(folder.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique.append(folder)
        unique.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for folder in unique:
            try:
                data = json.loads((folder / "index.json").read_text(encoding="utf-8"))
            except Exception:
                data = {}
            status = data.get("status", "")
            if show_approved and status != "review_approved":
                continue
            if not show_approved and status not in ("review_pending", "needs_model_or_manual", "raw_captured", "processing"):
                continue
            yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
            objects = yolo.get("objects") or []
            if not objects and yolo.get("bbox_xyxy"):
                objects = [yolo]
            item = QTreeWidgetItem()
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setText(1, folder.name)
            item.setText(2, str(data.get("action_type", "")))
            item.setText(3, str(len(objects)))
            item.setText(4, str(status or "unknown"))
            item.setText(5, str(data.get("gpt_yolo_objects", {}).get("model") or yolo.get("status") or ""))
            runtime_index = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
            if runtime_index:
                runtime_text = f"E{runtime_index.get('elements', 0)} R{runtime_index.get('rules', 0)}"
            else:
                click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
                runtime_text = "rule hit" if click_target.get("status") == "runtime_rule_matched" else ""
            recording = data.get("recording", {}) if isinstance(data.get("recording"), dict) else {}
            recording_text = ""
            if recording.get("video_offset_ms") is not None:
                recording_text = f"{recording.get('kind', '')} @{self._format_seconds(recording.get('video_offset_ms'))}"
            item.setText(6, runtime_text)
            item.setText(7, recording_text)
            item.setText(8, str(data.get("time", "")))
            item.setData(0, 257, str(folder))
            item.setData(0, 258, "yolo_event")
            item.setData(1, 257, str(folder))
            item.setData(1, 258, "yolo_event")
            self.audit_list.addTopLevelItem(item)

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

    def _open_yolo_audit_tab(self, folder: Path):
        index_path = folder / "index.json"
        if not index_path.exists():
            self._set_status(f"YOLO audit: missing index.json in {folder.name}")
            return
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._set_status(f"YOLO audit: index read failed - {e}")
            return

        image_name = data.get("images", {}).get("before") or "before.png"
        image_path = folder / image_name
        if not image_path.exists():
            self._set_status(f"YOLO audit: image missing - {image_path}")
            return

        objects = self._yolo_objects_from_event(data)
        if not objects:
            objects = [{
                "class_name": data.get("click_target", {}).get("element_name") or "tap_target",
                "bbox_xyxy": data.get("click_target", {}).get("bbox_xyxy") or [0, 0, 80, 80],
                "role": "clicked_target",
                "source": "manual",
            }]
        selected = {"index": 0}

        audit_tab = None
        for i in range(self.ui.tabWidget.count()):
            if self.ui.tabWidget.tabText(i) == "YOLO Audit":
                audit_tab = self.ui.tabWidget.widget(i)
                break
        if audit_tab is None:
            audit_tab = QWidget()
            audit_tab.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
            self.ui.tabWidget.addTab(audit_tab, "YOLO Audit")
            layout = QHBoxLayout(audit_tab)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(10)
        else:
            layout = audit_tab.layout()
            while layout.count():
                child = layout.takeAt(0)
                widget = child.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()

        form = QWidget(audit_tab)
        form.setFixedWidth(240)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        title = QLabel(f"YOLO Review\n{folder.name}")
        title.setStyleSheet("font-weight: bold; color: #cccccc;")
        form_layout.addWidget(title)

        object_table = QTableWidget(form)
        object_table.setColumnCount(8)
        object_table.setHorizontalHeaderLabels(["通过", "Label", "Role", "x1", "y1", "x2", "y2", "Source"])
        object_table.setMinimumHeight(220)
        object_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        object_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        object_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        object_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 3px; }"
        )
        object_table.setColumnWidth(0, 28)
        object_table.setColumnWidth(1, 48)
        object_table.setColumnWidth(2, 44)
        for col in [3, 4, 5, 6]:
            object_table.setColumnWidth(col, 32)
        object_table.setColumnWidth(7, 56)
        form_layout.addWidget(object_table)

        object_combo = QComboBox(form)
        object_combo.setStyleSheet("QComboBox { background-color: #3c3c3c; color: #cccccc; }")
        form_layout.addWidget(object_combo)

        label_edit = QLineEdit(form)
        label_edit.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        legacy_label_title = QLabel("Label")
        form_layout.addWidget(legacy_label_title)
        form_layout.addWidget(label_edit)

        spin_widgets = {}
        legacy_spin_rows = []
        for name in ["x1", "y1", "x2", "y2"]:
            row = QHBoxLayout()
            row_label = QLabel(name)
            row.addWidget(row_label)
            spin = QSpinBox(form)
            spin.setRange(0, 10000)
            spin.setStyleSheet("QSpinBox { background-color: #3c3c3c; color: #cccccc; }")
            row.addWidget(spin, 1)
            spin_widgets[name] = spin
            legacy_spin_rows.append((row_label, spin))
            form_layout.addLayout(row)
        object_combo.setVisible(False)
        legacy_label_title.setVisible(False)
        label_edit.setVisible(False)
        for row_label, spin in legacy_spin_rows:
            row_label.setVisible(False)
            spin.setVisible(False)

        image_label = YoloReviewImageLabel(image_path, objects, selected["index"], audit_tab)
        table_syncing = {"value": False}

        def ensure_review_flags():
            for obj in objects:
                if "review_approved" not in obj:
                    obj["review_approved"] = obj.get("review_status") == "approved"

        def refill_table():
            ensure_review_flags()
            table_syncing["value"] = True
            object_table.setRowCount(len(objects))
            for row, obj in enumerate(objects):
                approved = QTableWidgetItem("")
                approved.setFlags(approved.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                approved.setCheckState(Qt.CheckState.Checked if obj.get("review_approved") else Qt.CheckState.Unchecked)
                object_table.setItem(row, 0, approved)
                row_color = QColor("#17324d") if obj.get("review_approved") else QColor("#2a2a2a")
                values = [
                    obj.get("class_name") or "ui_element",
                    obj.get("role") or "ui_element",
                    *(obj.get("bbox_xyxy") or [0, 0, 80, 80]),
                    obj.get("source") or "",
                ]
                for col, value in enumerate(values, start=1):
                    item = QTableWidgetItem(str(value))
                    item.setBackground(QBrush(row_color))
                    if col == 7:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    object_table.setItem(row, col, item)
                approved.setBackground(QBrush(row_color))
            if objects:
                object_table.selectRow(max(0, min(selected["index"], len(objects) - 1)))
            table_syncing["value"] = False

        def apply_table_to_objects():
            if table_syncing["value"]:
                return
            for row, obj in enumerate(objects):
                if row >= object_table.rowCount():
                    continue
                check_item = object_table.item(row, 0)
                obj["review_approved"] = bool(check_item and check_item.checkState() == Qt.CheckState.Checked)
                label_item = object_table.item(row, 1)
                role_item = object_table.item(row, 2)
                obj["class_name"] = self._safe_yolo_class_name(label_item.text() if label_item else obj.get("class_name"))
                obj["role"] = (role_item.text().strip() if role_item else obj.get("role")) or "ui_element"
                bbox = []
                for col in [3, 4, 5, 6]:
                    item = object_table.item(row, col)
                    try:
                        bbox.append(int(float(item.text()))) if item else bbox.append(0)
                    except Exception:
                        bbox.append(0)
                x1, y1, x2, y2 = bbox
                obj["bbox_xyxy"] = [x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)]
            if objects:
                image_label.set_objects(objects, selected["index"])

        def refill_combo():
            object_combo.blockSignals(True)
            object_combo.clear()
            for idx, obj in enumerate(objects):
                label = obj.get("class_name") or "ui_element"
                role = obj.get("role") or ""
                object_combo.addItem(f"{idx + 1}. {label} {role}".strip())
            object_combo.setCurrentIndex(max(0, min(selected["index"], len(objects) - 1)))
            object_combo.blockSignals(False)

        def load_selected():
            if not objects:
                return
            idx = max(0, min(selected["index"], len(objects) - 1))
            selected["index"] = idx
            obj = objects[idx]
            label_edit.setText(str(obj.get("class_name") or "ui_element"))
            bbox = obj.get("bbox_xyxy") or [0, 0, 80, 80]
            for key, value in zip(["x1", "y1", "x2", "y2"], bbox):
                spin_widgets[key].setValue(int(value))
            image_label.set_objects(objects, idx)
            refill_combo()
            refill_table()

        def save_current_to_memory():
            if not objects:
                return
            apply_table_to_objects()
            if object_table.isVisible():
                image_label.set_objects(objects, selected["index"])
                refill_combo()
                refill_table()
                return
            idx = selected["index"]
            x1 = spin_widgets["x1"].value()
            y1 = spin_widgets["y1"].value()
            x2 = max(x1 + 1, spin_widgets["x2"].value())
            y2 = max(y1 + 1, spin_widgets["y2"].value())
            objects[idx]["class_name"] = self._safe_yolo_class_name(label_edit.text())
            objects[idx]["bbox_xyxy"] = [x1, y1, x2, y2]
            objects[idx]["source"] = objects[idx].get("source") or "manual_review"
            objects[idx]["review_status"] = "edited"
            objects[idx]["modified"] = True
            image_label.set_objects(objects, idx)
            refill_combo()
            refill_table()

        def on_table_cell_changed(row, col):
            if table_syncing["value"]:
                return
            apply_table_to_objects()
            if 0 <= row < len(objects):
                objects[row]["modified"] = True
                selected["index"] = row
                load_selected()

        def on_table_selection_changed():
            rows = object_table.selectionModel().selectedRows() if object_table.selectionModel() else []
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(objects):
                selected["index"] = row
                load_selected()

        object_table.cellChanged.connect(on_table_cell_changed)
        object_table.itemSelectionChanged.connect(on_table_selection_changed)

        def on_combo_changed(index):
            if index < 0:
                return
            save_current_to_memory()
            selected["index"] = index
            load_selected()

        object_combo.currentIndexChanged.connect(on_combo_changed)

        btn_reanalyze = QPushButton("GPT-5.5 Reanalyze", form)
        btn_reanalyze.setStyleSheet("QPushButton { background-color: #6a9955; color: white; padding: 6px; }")
        form_layout.addWidget(btn_reanalyze)

        btn_reanalyze_qwen = QPushButton("Qwen-VL Reanalyze", form)
        btn_reanalyze_qwen.setStyleSheet("QPushButton { background-color: #7b68ee; color: white; padding: 6px; }")
        btn_reanalyze_qwen.setToolTip("使用阿里云 qwen-vl-max 进行 UI 标注（更便宜）")
        form_layout.addWidget(btn_reanalyze_qwen)

        btn_open_bbox_editor = QPushButton("Open BBox Editor", form)
        btn_open_bbox_editor.setStyleSheet("QPushButton { background-color: #3c3c3c; color: white; padding: 6px; }")
        form_layout.addWidget(btn_open_bbox_editor)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Box", form)
        btn_delete = QPushButton("Delete", form)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_delete)
        form_layout.addLayout(btn_row)

        def add_box():
            objects.append({
                "class_name": "ui_element",
                "bbox_xyxy": [20, 20, 120, 120],
                "role": "ui_element",
                "source": "manual_review",
                "review_approved": False,
                "modified": True,
            })
            selected["index"] = len(objects) - 1
            load_selected()

        def delete_box():
            if not objects:
                return
            objects.pop(selected["index"])
            selected["index"] = max(0, min(selected["index"], len(objects) - 1))
            if objects:
                load_selected()
            else:
                refill_combo()
                refill_table()
                image_label.set_objects(objects, 0)

        btn_add.clicked.connect(add_box)
        btn_delete.clicked.connect(delete_box)

        btn_save = QPushButton("Save Annotation", form)
        btn_approve = QPushButton("Approve", form)
        btn_train = QPushButton("Train YOLO", form)
        for btn in [btn_save, btn_approve, btn_train]:
            btn.setStyleSheet("QPushButton { background-color: #0e639c; color: white; padding: 6px; }")
            form_layout.addWidget(btn)

        status = QLabel("", form)
        status.setWordWrap(True)
        status.setStyleSheet("color: #9cdcfe;")
        form_layout.addWidget(status)
        form_layout.addStretch(1)

        def save_annotation(approved=False):
            save_current_to_memory()
            result = self._save_yolo_review(folder, data, image_path, objects, approved=approved)
            status.setText(result)
            self._set_status(result)
            self._refresh_audit_list()

        def reanalyze_with_model(model_name: str):
            label = "GPT-5.5" if model_name == "gpt55" else "Qwen-VL"
            btn = btn_reanalyze if model_name == "gpt55" else btn_reanalyze_qwen
            method = self._reanalyze_yolo_objects_with_gpt55 if model_name == "gpt55" else self._reanalyze_yolo_objects_with_qwen_vl_max
            model_key = "openai/gpt-5.5" if model_name == "gpt55" else "qwen-vl-max"

            status.setText(f"{label} analyzing full UI...")
            btn_reanalyze.setEnabled(False)
            btn_reanalyze_qwen.setEnabled(False)
            self._set_status(f"{label} reanalyze: request started")
            LogManager().append(f"[{label} Reanalyze] button clicked: folder={folder}, image={image_path}")

            token = f"{folder.resolve()}:{time.time()}:{model_name}"

            def _apply_result(payload):
                if payload.get("token") != token:
                    return
                try:
                    self._bridge.yolo_reanalyze_ready.disconnect(_apply_result)
                except Exception:
                    pass
                result = payload.get("result", {})
                btn_reanalyze.setEnabled(True)
                btn_reanalyze_qwen.setEnabled(True)
                if result.get("error"):
                    status.setText(f"{label} failed: {result['error']}")
                    self._set_status(f"{label} failed: {result['error']}")
                    return
                new_objects = result.get("objects") or []
                if not new_objects:
                    status.setText(f"{label} returned no UI boxes. See log/raw response files.")
                    self._set_status(f"{label} returned no UI boxes")
                    return
                for obj in new_objects:
                    obj["review_approved"] = False
                objects.clear()
                objects.extend(new_objects)
                selected["index"] = 0
                user_intent = result.get("user_intent", "")
                if user_intent:
                    data["gpt_user_intent"] = user_intent
                data["gpt_yolo_objects"] = {
                    "status": "ok",
                    "model": model_key,
                    "objects": new_objects,
                    "raw": result.get("raw", ""),
                }
                load_selected()
                intent_text = f" | Intent: {user_intent}" if user_intent else ""
                status.setText(f"{label} found {len(new_objects)} UI boxes.{intent_text} Review then Save/Approve.")
                self._set_status(f"{label} found {len(new_objects)} UI boxes{intent_text}")

            self._bridge.yolo_reanalyze_ready.connect(_apply_result)

            def _run():
                result = method(folder, data, image_path)
                self._bridge.yolo_reanalyze_ready.emit({"token": token, "result": result})

            threading.Thread(target=_run, daemon=True).start()

        btn_save.clicked.connect(lambda: save_annotation(False))
        btn_approve.clicked.connect(lambda: save_annotation(True))
        btn_train.clicked.connect(self._train_yolo_incremental)
        btn_reanalyze.clicked.connect(lambda: reanalyze_with_model("gpt55"))
        btn_reanalyze_qwen.clicked.connect(lambda: reanalyze_with_model("qwen_vl"))

        def open_bbox_editor():
            save_current_to_memory()
            dialog = BBoxEditorDialog(image_path, objects, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                objects.clear()
                objects.extend(dialog.edited_objects())
                for obj in objects:
                    if "review_approved" not in obj:
                        obj["review_approved"] = False
                    obj["modified"] = True
                selected["index"] = min(selected["index"], max(0, len(objects) - 1))
                load_selected()
                status.setText(f"BBox editor applied {len(objects)} boxes. Save/Approve to write labels.")
                self._set_status(f"BBox editor applied {len(objects)} boxes")

        btn_open_bbox_editor.clicked.connect(open_bbox_editor)

        layout.addWidget(form)
        layout.addWidget(image_label, 1)
        load_selected()
        self.ui.tabWidget.setCurrentIndex(self.ui.tabWidget.indexOf(audit_tab))

    def _safe_yolo_class_name(self, value: str) -> str:
        from yolo_class_manager import normalize_class_name
        return normalize_class_name(value)

    def _clean_llm_context_text(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        mojibake_marks = sum(text.count(mark) for mark in ["�", "锛", "绋", "鐧", "娓", "浣", "蹇", "鏍"])
        if mojibake_marks >= 2:
            return ""
        return text[:200]

    def _llm_vision_image_size(self, width: int, height: int) -> tuple[int, int]:
        max_edge = 1024
        if max(width, height) <= max_edge:
            return width, height
        ratio = max_edge / max(width, height)
        return int(width * ratio), int(height * ratio)

    def _build_reanalyze_prompt(self, image_path: Path, data: dict):
        """构建 Reanalyze prompt，返回 (prompt, width, height, vision_w, vision_h, scale_x, scale_y, click_x, click_y, scene_text)"""
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
        vision_width, vision_height = self._llm_vision_image_size(width, height)
        scale_x = width / max(1, vision_width)
        scale_y = height / max(1, vision_height)

        touch = data.get("touch", {}).get("frame_start", {})
        click_x = int(touch.get("x", 0))
        click_y = int(touch.get("y", 0))
        scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
        scene_text = self._clean_llm_context_text(scene.get("description") or scene.get("scene_key") or "")
        prompt = (
            "You are a precise UI annotation engine for YOLO training. Analyze the attached game screenshot.\n"
            "Return ONLY valid JSON. Do not use markdown. Do not explain.\n"
            "Task A: Infer the player's intent for this operation. Based on the scene, the click point, and the UI "
            "state, determine what the player is trying to accomplish with this tap. Return this as user_intent "
            "(one concise Chinese sentence, max 30 chars).\n"
            "Task B: find the complete clickable UI element containing the click point. Put it FIRST in the objects "
            "array and set role to clicked_target.\n"
            "Task C: find the parent panel/dialog/card/container that contains the clicked target. Put it SECOND "
            "in the objects array and set role to clicked_target_panel. The panel box should cover the full visible "
            "panel rectangle, not the whole screen and not just the button.\n"
            "Task D: label the other visible, stable, automation-useful UI elements. Include buttons, text links, "
            "input boxes, checkboxes, tabs, close/back/confirm/cancel controls, and menu icons. Ignore background "
            "art, decoration, loading effects, and non-clickable illustrations.\n"
            "Use the coordinate system of the image sent to you for bbox_xyxy: [x1,y1,x2,y2]. Every box must cover the full "
            "clickable UI area, not a 100x100 patch around the click. Keep boxes tight but complete.\n"
            "Use short stable snake_case class_name values in English or pinyin. Limit to 30 objects.\n"
            "JSON schema: "
            '{"user_intent":"玩家想要登录游戏","objects":['
            '{"class_name":"sms_code_button","name":"get code",'
            '"bbox_xyxy":[x1,y1,x2,y2],"role":"clicked_target",'
            '"action_effect":"what tapping does","confidence":0.0},'
            '{"class_name":"login_panel","name":"login panel",'
            '"bbox_xyxy":[x1,y1,x2,y2],"role":"clicked_target_panel",'
            '"action_effect":"parent container","confidence":0.0}]}\n'
            f"Image size sent to you: {vision_width}x{vision_height}\n"
            f"The program will scale your bbox values back to the original screenshot size: {width}x{height}\n"
            f"User click point: ({click_x},{click_y})\n"
            f"Optional scene hint: {scene_text or 'none'}"
        )
        return prompt, width, height, vision_width, vision_height, scale_x, scale_y, click_x, click_y, scene_text

    @staticmethod
    def _fix_json_text(text: str) -> str:
        """修复模型返回的常见 JSON 格式错误（如 bbox_xyxy 漏掉方括号）。"""
        # 修复 "bbox_xyxy":x1,y1,x2,y2 为 "bbox_xyxy":[x1,y1,x2,y2]
        text = re.sub(
            r'"bbox_xyxy"\s*:\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)',
            r'"bbox_xyxy":[\1,\2,\3,\4]',
            text,
        )
        # 修复 "bbox":x1,y1,x2,y2 为 "bbox":[x1,y1,x2,y2]
        text = re.sub(
            r'"bbox"\s*:\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)',
            r'"bbox":[\1,\2,\3,\4]',
            text,
        )
        return text

    def _process_reanalyze_response(
        self, raw: str, width: int, height: int, scale_x: float, scale_y: float, click_x: int, click_y: int
    ) -> tuple[list[dict], str]:
        """解析 Reanalyze 的 raw response，返回 (objects, user_intent)"""
        parsed: dict = {}
        user_intent = ""
        try:
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                json_text = self._fix_json_text(m.group(1))
                parsed = json.loads(json_text)
            else:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    json_text = self._fix_json_text(m.group(0))
                    parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                user_intent = str(parsed.get("user_intent") or "").strip()
        except Exception as parse_err:
            LogManager().append(f"[Reanalyze] JSON parse warning: {parse_err}")
        objects = []
        for obj in parsed.get("objects", []) if isinstance(parsed, dict) else []:
            bbox = obj.get("bbox_xyxy") or obj.get("bbox")
            name = obj.get("class_name") or obj.get("name")
            if not name or not bbox or len(bbox) != 4:
                continue
            raw_x1, raw_y1, raw_x2, raw_y2 = [float(v) for v in bbox]
            x1 = int(round(raw_x1 * scale_x))
            y1 = int(round(raw_y1 * scale_y))
            x2 = int(round(raw_x2 * scale_x))
            y2 = int(round(raw_y2 * scale_y))
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(x1 + 1, min(width, x2))
            y2 = max(y1 + 1, min(height, y2))
            objects.append({
                "class_name": self._safe_yolo_class_name(name),
                "name": obj.get("name", ""),
                "bbox_xyxy_model": [raw_x1, raw_y1, raw_x2, raw_y2],
                "bbox_xyxy": [x1, y1, x2, y2],
                "role": obj.get("role", "ui_element"),
                "action_effect": obj.get("action_effect", ""),
                "confidence": float(obj.get("confidence") or 0.5),
                "modified": False,
            })

        def click_contains(item):
            x1, y1, x2, y2 = item["bbox_xyxy"]
            return x1 <= click_x <= x2 and y1 <= click_y <= y2

        def object_area(item):
            x1, y1, x2, y2 = item["bbox_xyxy"]
            return max(1, (x2 - x1) * (y2 - y1))

        target_candidates = [
            item for item in objects
            if click_contains(item) and str(item.get("role", "")) != "clicked_target_panel"
        ]
        panel_candidates = [
            item for item in objects
            if click_contains(item) and str(item.get("role", "")) == "clicked_target_panel"
        ]
        if target_candidates:
            target = min(target_candidates, key=object_area)
            target["role"] = "clicked_target"
        if not panel_candidates:
            larger = [
                item for item in objects
                if click_contains(item) and item is not (target_candidates[0] if target_candidates else None)
                and object_area(item) >= (object_area(target_candidates[0]) * 2 if target_candidates else 1)
            ]
            if larger:
                panel = max(larger, key=object_area)
                panel["role"] = "clicked_target_panel"
                panel["class_name"] = panel.get("class_name") or "clicked_panel"

        def sort_key(item):
            role = str(item.get("role", ""))
            if role == "clicked_target":
                return (0, object_area(item))
            if role == "clicked_target_panel":
                return (1, -object_area(item))
            return (2, -float(item.get("confidence") or 0))

        objects.sort(key=sort_key)
        return objects, user_intent

    def _reanalyze_yolo_objects_with_gpt55(self, folder: Path, data: dict, image_path: Path) -> dict:
        t0 = time.time()
        logger = get_logger()
        prompt = ""
        raw = ""
        used_model = ""
        user_intent = ""
        try:
            from llm_client import QwenVLClient

            prompt, width, height, vision_width, vision_height, scale_x, scale_y, click_x, click_y, scene_text = \
                self._build_reanalyze_prompt(image_path, data)

            debug_dir = folder / "gpt55_reanalyze"
            debug_dir.mkdir(parents=True, exist_ok=True)
            request_payload = {
                "model": "openai/gpt-5.5",
                "image_path": str(image_path),
                "original_image_size": [width, height],
                "vision_image_size": [vision_width, vision_height],
                "scale_to_original": [scale_x, scale_y],
                "click_point": [click_x, click_y],
                "scene_text": scene_text,
                "prompt": prompt,
            }
            (debug_dir / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            LogManager().append(
                "[GPT-5.5 Reanalyze] request\n"
                f"  image={image_path}\n"
                f"  original_size={width}x{height}\n"
                f"  vision_size={vision_width}x{vision_height}\n"
                f"  scale_to_original=({scale_x:.6f},{scale_y:.6f})\n"
                f"  click=({click_x},{click_y})\n"
                f"  prompt_file={debug_dir / 'prompt.txt'}\n"
                f"{prompt}"
            )
            client = QwenVLClient(model="openai/gpt-5.5")
            image_b64 = client._prepare_image(image_path)
            models = [client.model] + [m for m in client.FALLBACK_MODELS if m != client.model]
            raw = ""
            errors = []
            for model in models:
                try:
                    LogManager().append(f"[GPT-5.5 Reanalyze] calling model={model} max_tokens=4096")
                    raw = client._call_vision_api(model, image_b64, prompt, 4096, 180)
                    LogManager().append(f"[GPT-5.5 Reanalyze] model={model} raw_len={len(raw)}")
                    if raw.strip():
                        used_model = model
                        break
                    errors.append(f"{model}: empty response")
                except Exception as call_error:
                    errors.append(f"{model}: {call_error}")
                    LogManager().append(f"[GPT-5.5 Reanalyze] model={model} failed: {call_error}")
            if not raw.strip():
                error_text = "\n".join(errors) or "empty response"
                (debug_dir / "response_error.txt").write_text(error_text, encoding="utf-8")
                LogManager().append(f"[GPT-5.5 Reanalyze] all models failed/empty\n{error_text}")
                duration_ms = (time.time() - t0) * 1000
                logger.append(
                    image_path=str(image_path),
                    folder=str(folder),
                    prompt=prompt,
                    raw_response="",
                    model=", ".join(models),
                    objects=[],
                    error=error_text,
                    duration_ms=duration_ms,
                    metadata={"debug_dir": str(debug_dir)},
                )
                return {"error": error_text, "objects": []}
            (debug_dir / "response_raw.txt").write_text(raw, encoding="utf-8")
            LogManager().append(
                "[GPT-5.5 Reanalyze] raw response\n"
                f"  response_file={debug_dir / 'response_raw.txt'}\n"
                f"{raw}"
            )
            objects, user_intent = self._process_reanalyze_response(raw, width, height, scale_x, scale_y, click_x, click_y)
            for obj in objects:
                obj["source"] = "gpt-5.5-reanalyze"
            parsed_payload = {
                "objects": objects,
                "object_count": len(objects),
            }
            (debug_dir / "parsed_objects.json").write_text(
                json.dumps(parsed_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            LogManager().append(
                "[GPT-5.5 Reanalyze] parsed objects\n"
                f"  parsed_file={debug_dir / 'parsed_objects.json'}\n"
                f"{json.dumps(parsed_payload, ensure_ascii=False, indent=2)}"
            )
            duration_ms = (time.time() - t0) * 1000
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model or "openai/gpt-5.5",
                objects=objects,
                error="",
                duration_ms=duration_ms,
                metadata={
                    "debug_dir": str(debug_dir),
                    "original_size": [width, height],
                    "vision_size": [vision_width, vision_height],
                    "click_point": [click_x, click_y],
                    "user_intent": user_intent,
                },
            )
            return {"objects": objects, "raw": raw[:1200], "user_intent": user_intent}
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            error_str = str(e)
            LogManager().append(f"[Audit] GPT-5.5 reanalyze failed: {e}")
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model or "openai/gpt-5.5",
                objects=[],
                error=error_str,
                duration_ms=duration_ms,
                metadata={},
            )
            return {"error": error_str, "objects": []}

    def _reanalyze_yolo_objects_with_qwen_vl_max(self, folder: Path, data: dict, image_path: Path) -> dict:
        """使用阿里云 DashScope qwen-vl-max 进行 Reanalyze。"""
        t0 = time.time()
        logger = get_logger()
        prompt = ""
        raw = ""
        used_model = "qwen-vl-max"
        user_intent = ""
        try:
            from llm_client import DashScopeVLClient

            prompt, width, height, vision_width, vision_height, scale_x, scale_y, click_x, click_y, scene_text = \
                self._build_reanalyze_prompt(image_path, data)

            debug_dir = folder / "qwen_vl_reanalyze"
            debug_dir.mkdir(parents=True, exist_ok=True)
            request_payload = {
                "model": "qwen-vl-max",
                "image_path": str(image_path),
                "original_image_size": [width, height],
                "vision_image_size": [vision_width, vision_height],
                "scale_to_original": [scale_x, scale_y],
                "click_point": [click_x, click_y],
                "scene_text": scene_text,
                "prompt": prompt,
            }
            (debug_dir / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            LogManager().append(
                "[Qwen-VL Reanalyze] request\n"
                f"  image={image_path}\n"
                f"  original_size={width}x{height}\n"
                f"  vision_size={vision_width}x{vision_height}\n"
                f"  scale_to_original=({scale_x:.6f},{scale_y:.6f})\n"
                f"  click=({click_x},{click_y})\n"
                f"  prompt_file={debug_dir / 'prompt.txt'}\n"
                f"{prompt}"
            )
            client = DashScopeVLClient()
            if not client.is_ready():
                return {"error": "DASHSCOPE_API_KEY not configured", "objects": []}
            raw = client.call_vision(image_path, prompt, max_tokens=4096, timeout=180)
            if raw.startswith("[dashscope_vl_error]"):
                (debug_dir / "response_error.txt").write_text(raw, encoding="utf-8")
                LogManager().append(f"[Qwen-VL Reanalyze] failed: {raw}")
                duration_ms = (time.time() - t0) * 1000
                logger.append(
                    image_path=str(image_path),
                    folder=str(folder),
                    prompt=prompt,
                    raw_response="",
                    model=used_model,
                    objects=[],
                    error=raw,
                    duration_ms=duration_ms,
                    metadata={"debug_dir": str(debug_dir)},
                )
                return {"error": raw, "objects": []}
            (debug_dir / "response_raw.txt").write_text(raw, encoding="utf-8")
            LogManager().append(
                "[Qwen-VL Reanalyze] raw response\n"
                f"  response_file={debug_dir / 'response_raw.txt'}\n"
                f"{raw}"
            )
            objects, user_intent = self._process_reanalyze_response(raw, width, height, scale_x, scale_y, click_x, click_y)
            for obj in objects:
                obj["source"] = "qwen-vl-max-reanalyze"
            parsed_payload = {
                "objects": objects,
                "object_count": len(objects),
            }
            (debug_dir / "parsed_objects.json").write_text(
                json.dumps(parsed_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            LogManager().append(
                "[Qwen-VL Reanalyze] parsed objects\n"
                f"  parsed_file={debug_dir / 'parsed_objects.json'}\n"
                f"{json.dumps(parsed_payload, ensure_ascii=False, indent=2)}"
            )
            duration_ms = (time.time() - t0) * 1000
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model,
                objects=objects,
                error="",
                duration_ms=duration_ms,
                metadata={
                    "debug_dir": str(debug_dir),
                    "original_size": [width, height],
                    "vision_size": [vision_width, vision_height],
                    "click_point": [click_x, click_y],
                    "user_intent": user_intent,
                },
            )
            return {"objects": objects, "raw": raw[:1200], "user_intent": user_intent}
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            error_str = str(e)
            LogManager().append(f"[Audit] Qwen-VL reanalyze failed: {e}")
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model,
                objects=[],
                error=error_str,
                duration_ms=duration_ms,
                metadata={},
            )
            return {"error": error_str, "objects": []}

    def _yolo_objects_from_event(self, data: dict) -> list[dict]:
        yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
        objects = []
        for obj in yolo.get("objects") or []:
            if obj.get("bbox_xyxy"):
                objects.append(dict(obj))
        if not objects and yolo.get("bbox_xyxy"):
            objects.append({
                "class_name": yolo.get("class_name") or "tap_target",
                "bbox_xyxy": yolo.get("bbox_xyxy"),
                "role": "clicked_target",
                "source": yolo.get("status") or "yolo",
            })
        return objects

    def _save_yolo_review(self, folder: Path, data: dict, image_path: Path, objects: list[dict], approved: bool = False) -> str:
        try:
            import shutil
            from PIL import Image
            from agent_data import GAME_DATA_DIR, AgentDataManager

            with Image.open(image_path) as img:
                width, height = img.size

            normalized = []
            review_objects = []
            label_lines = []
            for obj in objects:
                bbox = obj.get("bbox_xyxy") or []
                if len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                x1 = max(0, min(width - 1, x1))
                y1 = max(0, min(height - 1, y1))
                x2 = max(x1 + 1, min(width, x2))
                y2 = max(y1 + 1, min(height, y2))
                class_name = self._safe_yolo_class_name(obj.get("class_name") or "ui_element")
                class_id = self._ensure_yolo_class(class_name)
                clean = dict(obj)
                clean.update({
                    "class_id": class_id,
                    "class_name": class_name,
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "review_status": "approved" if clean.get("review_approved") else "candidate",
                })
                review_objects.append(clean)
                if clean.get("review_approved", False):
                    label_lines.append(
                        f"{class_id} {((x1 + x2) / 2) / width:.6f} {((y1 + y2) / 2) / height:.6f} "
                        f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}"
                    )
                    normalized.append(clean)

            event_key = folder.name
            label_text = "\n".join(label_lines) + ("\n" if label_lines else "")
            local_yolo_dir = folder / "yolo"
            local_images = local_yolo_dir / "images"
            local_labels = local_yolo_dir / "labels"
            local_images.mkdir(parents=True, exist_ok=True)
            local_labels.mkdir(parents=True, exist_ok=True)
            local_image = local_images / f"{event_key}.png"
            local_label = local_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(local_image))
            local_label.write_text(label_text, encoding="utf-8")
            (local_yolo_dir / "classes.txt").write_text(self._yolo_classes_text(), encoding="utf-8")

            dataset_images = GAME_DATA_DIR / "yolo_events" / "images" / "train"
            dataset_labels = GAME_DATA_DIR / "yolo_events" / "labels" / "train"
            dataset_images.mkdir(parents=True, exist_ok=True)
            dataset_labels.mkdir(parents=True, exist_ok=True)
            dataset_image = dataset_images / f"{event_key}.png"
            dataset_label = dataset_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(dataset_image))
            dataset_label.write_text(label_text, encoding="utf-8")
            (GAME_DATA_DIR / "yolo_events" / "classes.txt").write_text(self._yolo_classes_text(), encoding="utf-8")
            (GAME_DATA_DIR / "yolo_events" / "data.yaml").write_text(self._yolo_data_yaml(), encoding="utf-8")

            data["yolo"] = {
                "status": "review_approved" if approved else "review_edited",
                "image_width": width,
                "image_height": height,
                "objects": review_objects,
                "approved_objects": normalized,
                "bbox_xyxy": normalized[0]["bbox_xyxy"] if normalized else None,
                "class_name": normalized[0]["class_name"] if normalized else "ui_element",
                "label": label_text.strip(),
                "local_image": str(local_image),
                "local_label": str(local_label),
                "dataset_image": str(dataset_image),
                "dataset_label": str(dataset_label),
            }
            data["status"] = "review_approved" if approved else "review_pending"
            data["review"] = {
                "type": "yolo_event",
                "approved": bool(approved),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            index_path = folder / "index.json"
            index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            AgentDataManager().record_physical_event(
                event_key=folder.name,
                action_type=data.get("action_type", ""),
                timestamp_ms=int(time.time() * 1000),
                duration_ms=int(data.get("duration_ms") or 0),
                touch=data.get("touch", {}),
                folder_path=folder,
                images=data.get("images", {}),
                index_path=index_path,
                yolo=data.get("yolo"),
            )

            # 审核通过时，将场景注册到 SceneIndex hash 库，提升后续识别速度
            if approved:
                try:
                    scene_idx = SceneIndex()
                    scene_name = folder.name
                    scene_desc = ""
                    si = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
                    scene_desc = si.get("description") or si.get("scene_key") or ""
                    user_intent = data.get("gpt_user_intent", "")
                    description = " | ".join(filter(None, [scene_desc, user_intent])) or scene_name
                    reg_result = scene_idx.register_from_review(
                        image_path=image_path,
                        scene_name=scene_name,
                        description=description,
                        threshold=0.96,
                    )
                    if reg_result.get("registered"):
                        data["scene_index"] = {
                            "matched": True,
                            "confidence": reg_result.get("confidence", 1.0),
                            "scene_id": reg_result.get("scene_id"),
                            "scene_key": reg_result.get("scene_key") or scene_name,
                            "description": description,
                        }
                    if reg_result.get("registered"):
                        if reg_result.get("existed"):
                            LogManager().append(
                                f"[SceneIndex] Review-approved scene '{scene_name}' already in index "
                                f"(confidence={reg_result['confidence']:.3f}), hit +1"
                            )
                        else:
                            LogManager().append(
                                f"[SceneIndex] Review-approved scene '{scene_name}' registered as new entry "
                                f"(id={reg_result['scene_id']})"
                            )
                except Exception as reg_err:
                    LogManager().append(f"[SceneIndex] Failed to register review scene: {reg_err}")

                data["runtime_index"] = self._compile_runtime_index_from_review(
                    folder=folder,
                    data=data,
                    image_path=image_path,
                    approved_objects=normalized,
                    source="human_review",
                )
                index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                self._bridge.overlay_changed.emit({
                    "scene": data.get("scene_index", {}).get("scene_key", "") if isinstance(data.get("scene_index"), dict) else "",
                    "rule": "",
                    "status": f"索引 E{data['runtime_index'].get('elements', 0)} R{data['runtime_index'].get('rules', 0)}",
                })

            runtime = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
            runtime_text = ""
            if runtime:
                runtime_text = f", runtime=E{runtime.get('elements', 0)}/R{runtime.get('rules', 0)}"
            return f"YOLO audit saved: {len(normalized)} boxes, status={data['status']}{runtime_text}"
        except Exception as e:
            LogManager().append(f"[Audit] YOLO save failed: {e}")
            return f"YOLO audit save failed: {e}"

    def _train_yolo_incremental(self):
        def _run():
            try:
                import shutil
                import subprocess
                from agent_data import GAME_DATA_DIR

                data_yaml = (GAME_DATA_DIR / "yolo_events" / "data.yaml").resolve()
                if not data_yaml.exists():
                    self._bridge.status_changed.emit("YOLO train: data.yaml missing", "#f44747")
                    return
                yolo_cmd = shutil.which("yolo")
                if not yolo_cmd:
                    self._bridge.status_changed.emit("YOLO train: install ultralytics first", "#f44747")
                    return
                weights_dir = (GAME_DATA_DIR / "yolo_events" / "runs" / "detect" / "train" / "weights").resolve()
                last_model = weights_dir / "last.pt"
                model = str(last_model if last_model.exists() else "yolov8n.pt")
                project = (GAME_DATA_DIR / "yolo_events" / "runs").resolve()
                cmd = [
                    yolo_cmd,
                    "detect",
                    "train",
                    f"data={data_yaml}",
                    f"model={model}",
                    "epochs=20",
                    "imgsz=640",
                    f"project={project}",
                    "exist_ok=True",
                ]
                LogManager().append(f"[YOLO] train command: {' '.join(map(str, cmd))}")
                self._bridge.status_changed.emit("YOLO train: running...", "#9cdcfe")
                proc = subprocess.run(
                    cmd,
                    cwd=str((GAME_DATA_DIR / "yolo_events").resolve()),
                    capture_output=True,
                    text=True,
                )
                if proc.stdout:
                    LogManager().append(proc.stdout[-4000:])
                if proc.stderr:
                    LogManager().append(proc.stderr[-4000:])
                if proc.returncode == 0:
                    self._bridge.status_changed.emit("YOLO train: completed", "#4ec9b0")
                else:
                    self._bridge.status_changed.emit(f"YOLO train failed: {proc.returncode}", "#f44747")
            except Exception as e:
                LogManager().append(f"[YOLO] train failed: {e}")
                self._bridge.status_changed.emit(f"YOLO train failed: {e}", "#f44747")

        threading.Thread(target=_run, daemon=True).start()

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
        if item.data(0, 258) == "yolo_event":
            menu = QMenu(self)
            action_train = menu.addAction("Train YOLO")
            action = menu.exec(self.audit_list.viewport().mapToGlobal(position))
            if action == action_train:
                self._train_yolo_incremental()
            return
        menu = QMenu(self)
        action_ollama = menu.addAction("重新 Ollama 识别")
        action_qwen = menu.addAction("重新 qwen-vl-max 识别")
        action = menu.exec(self.audit_list.viewport().mapToGlobal(position))
        if action == action_ollama:
            self._reclassify_scene(item, "ollama")
        elif action == action_qwen:
            self._reclassify_scene(item, "qwen")

    def _audit_select_all(self):
        """审核列表全选/取消全选切换。"""
        if not getattr(self, "audit_list", None):
            return
        checked = 0
        for i in range(self.audit_list.topLevelItemCount()):
            if self.audit_list.topLevelItem(i).checkState(0) == Qt.CheckState.Checked:
                checked += 1
        new_state = Qt.CheckState.Unchecked if checked > 0 else Qt.CheckState.Checked
        for i in range(self.audit_list.topLevelItemCount()):
            self.audit_list.topLevelItem(i).setCheckState(0, new_state)

    def _get_checked_audit_folders(self) -> list[Path]:
        """获取审核列表中勾选的 YOLO 事件文件夹路径。"""
        folders = []
        for i in range(self.audit_list.topLevelItemCount()):
            item = self.audit_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked and item.data(1, 258) == "yolo_event":
                path = item.data(1, 257)
                if path:
                    folders.append(Path(path))
        return folders

    def _batch_approve_selected(self):
        """批量批准勾选的 YOLO 事件。"""
        folders = self._get_checked_audit_folders()
        if not folders:
            QMessageBox.information(self, "批量批准", "请先勾选要批准的事件")
            return
        reply = QMessageBox.question(
            self, "确认批量批准",
            f"确定要批量批准 {len(folders)} 个事件吗？\n"
            "没有 approved 框的事件会自动标记所有框为 approved。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        success = 0
        failed = 0
        for folder in folders:
            try:
                index_path = folder / "index.json"
                if not index_path.exists():
                    failed += 1
                    continue
                data = json.loads(index_path.read_text(encoding="utf-8"))
                yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
                objects = yolo.get("objects") or []
                if not objects and yolo.get("bbox_xyxy"):
                    objects = [dict(yolo)]
                # 如果没有 approved 框，自动标记所有框
                has_approved = any(obj.get("review_approved") or obj.get("review_status") == "approved" for obj in objects)
                if not has_approved:
                    for obj in objects:
                        obj["review_approved"] = True
                image_name = data.get("images", {}).get("before") or "before.png"
                image_path = folder / image_name
                if not image_path.exists():
                    failed += 1
                    continue
                self._save_yolo_review(folder, data, image_path, objects, approved=True)
                success += 1
            except Exception as e:
                LogManager().append(f"[BatchApprove] {folder.name} 失败: {e}")
                failed += 1
        QMessageBox.information(self, "批量批准完成", f"成功 {success} | 失败 {failed}")
        self._refresh_audit_list()

    def _batch_compile_selected(self):
        """批量编译勾选的已批准事件的 runtime_index。"""
        folders = self._get_checked_audit_folders()
        if not folders:
            QMessageBox.information(self, "批量编译", "请先勾选要编译的事件")
            return
        success = 0
        failed = 0
        skipped = 0
        for folder in folders:
            try:
                index_path = folder / "index.json"
                if not index_path.exists():
                    failed += 1
                    continue
                data = json.loads(index_path.read_text(encoding="utf-8"))
                if data.get("status") != "review_approved":
                    skipped += 1
                    continue
                yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
                approved_objects = [dict(obj) for obj in (yolo.get("approved_objects") or [])]
                if not approved_objects:
                    approved_objects = [dict(obj) for obj in (yolo.get("objects") or []) if obj.get("review_approved") or obj.get("review_status") == "approved"]
                if not approved_objects:
                    skipped += 1
                    continue
                image_name = data.get("images", {}).get("before") or "before.png"
                image_path = folder / image_name
                if not image_path.exists():
                    failed += 1
                    continue
                result = self._compile_runtime_index_from_review(
                    folder=folder,
                    data=data,
                    image_path=image_path,
                    approved_objects=approved_objects,
                    source="batch_compile",
                )
                data["runtime_index"] = result
                index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                success += 1
            except Exception as e:
                LogManager().append(f"[BatchCompile] {folder.name} 失败: {e}")
                failed += 1
        QMessageBox.information(self, "批量编译完成", f"成功 {success} | 失败 {failed} | 跳过 {skipped}")
        self._refresh_audit_list()

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
                    if not result:
                        # Ollama 未运行/不可用，自动 fallback 到 qwen-vl-max
                        result = classify_image_with_qwen(image_path)
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
    def _recording_offset_ms(self) -> int | None:
        ctx = self._active_recording_context()
        if not ctx:
            return None
        return ctx.get("video_offset_ms")

    def _active_recording_context(self) -> dict:
        if self._video_writer is not None and self._record_started_perf:
            return {
                "kind": "manual",
                "video_path": str(self._record_path) if self._record_path else "",
                "events_path": str(self._record_events_path) if self._record_events_path else "",
                "meta_path": str(self._record_meta_path) if self._record_meta_path else "",
                "video_offset_ms": max(0, int((time.perf_counter() - self._record_started_perf) * 1000)),
                "started_timestamp_ms": self._record_started_ms,
                "frame_count": self._record_frame_count,
                "fps": self._record_fps,
            }
        if hasattr(self, "execution_engine") and self.execution_engine:
            return self.execution_engine.get_recording_context()
        return {}

    def _write_recording_meta(self, finished: bool = False) -> None:
        if not self._record_meta_path:
            return
        try:
            meta = {
                "video_path": str(self._record_path) if self._record_path else "",
                "events_path": str(self._record_events_path) if self._record_events_path else "",
                "started_timestamp_ms": self._record_started_ms,
                "started_at": datetime.fromtimestamp(self._record_started_ms / 1000).isoformat() if self._record_started_ms else "",
                "fps": self._record_fps,
                "frame_count": self._record_frame_count,
                "duration_ms": self._recording_offset_ms() or 0,
                "finished": bool(finished),
            }
            if finished:
                meta["ended_timestamp_ms"] = int(time.time() * 1000)
                meta["ended_at"] = datetime.now().isoformat()
            self._record_meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            LogManager().append(f"[WARN] write recording meta failed: {e}")

    def _append_recording_event(self, op_dir: Path, data: dict) -> None:
        ctx = self._active_recording_context()
        events_path = Path(ctx.get("events_path", "")) if ctx.get("events_path") else None
        if not events_path:
            return
        try:
            event = {
                "recording_kind": ctx.get("kind", ""),
                "video_offset_ms": ctx.get("video_offset_ms"),
                "timestamp_ms": int(time.time() * 1000),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "event_key": op_dir.name if op_dir else "",
                "folder_path": str(op_dir) if op_dir else "",
                "video_path": ctx.get("video_path", ""),
                "session_id": ctx.get("session_id", ""),
                "action_type": data.get("action_type", ""),
                "duration_ms": data.get("duration_ms", 0),
                "touch": data.get("touch", {}),
                "change": data.get("change", {}),
                "scene_index": data.get("scene_index", {}),
                "after_scene_index": data.get("after_scene_index", {}),
                "click_target": data.get("click_target", {}),
                "images": data.get("images", {}),
            }
            events_path.parent.mkdir(parents=True, exist_ok=True)
            with events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            if ctx.get("kind") == "manual":
                self._write_recording_meta(finished=False)
            elif hasattr(self.execution_engine, "_write_recording_meta"):
                self.execution_engine._write_recording_meta(finished=False)
        except Exception as e:
            LogManager().append(f"[WARN] append recording event failed: {e}")

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
            self._record_events_path = record_dir / f"scrcpy_{ts}.events.jsonl"
            self._record_meta_path = record_dir / f"scrcpy_{ts}.meta.json"
            self._record_started_perf = time.perf_counter()
            self._record_started_ms = int(time.time() * 1000)
            self._record_frame_count = 0
            self._record_last_frame_perf = 0.0

            h, w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._video_writer = cv2.VideoWriter(
                str(self._record_path), fourcc, self._record_fps, (w, h)
            )
            self._write_recording_meta(finished=False)

            if self.btn_record:
                self.btn_record.setEnabled(False)
            if self.btn_stop_record:
                self.btn_stop_record.setEnabled(True)
            self._set_status(f"状态: 开始录制 -> {self._record_path.name}")
            self._update_video_feedback_overlay()
        except Exception as e:
            self._video_writer = None
            self._set_status(f"状态: 录制启动失败 - {e}")

    def do_stop_record(self):
        if self._video_writer is None:
            self._set_status("状态: 未在录制")
            return

        try:
            self._write_recording_meta(finished=True)
            self._video_writer.release()
            self._video_writer = None
            if self.btn_record:
                self.btn_record.setEnabled(True)
            if self.btn_stop_record:
                self.btn_stop_record.setEnabled(False)
            events_name = self._record_events_path.name if self._record_events_path else ""
            self._set_status(f"状态: 录制已保存 -> {self._record_path.name} | {events_name}")
            self._update_video_feedback_overlay()
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

    def _show_video_replay(self):
        """打开视频回放中心对话框。"""
        dialog = VideoReplayDialog(self)
        dialog.exec()

    def _show_scene_graph(self):
        """打开 Scene Graph 可视化对话框。"""
        dialog = SceneGraphDialog(self)
        dialog.exec()

    def _show_rule_stats(self):
        """打开规则命中率统计面板。"""
        dialog = RuleStatsDialog(self)
        dialog.exec()

    def _show_rule_debug(self):
        """从菜单打开规则调试：选择一张 before 图片进行分析。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 before 图片", "screenshots", "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        before_path = Path(path)
        op_dir = before_path.parent
        event_data = {
            "images": {"before": before_path.name},
            "touch": {"frame_start": {"x": 0, "y": 0}},
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

    def _show_data_quality(self):
        """打开数据质量监控面板。"""
        dialog = DataQualityDialog(self)
        dialog.exec()

    def _show_auto_replay(self):
        """打开自动回放对话框。"""
        dialog = AutoReplayDialog(self, self)
        dialog.exec()

    def _start_auto_replay(self, events: list, delay_ms: int):
        """开始自动回放事件序列。"""
        if not (self.client and self.client.alive):
            LogManager().append("[AutoReplay] 设备未连接，无法回放")
            return
        self._replay_events = events
        self._replay_index = 0
        self._replay_delay_ms = delay_ms
        self._replay_timer = QTimer(self)
        self._replay_timer.timeout.connect(self._replay_next_step)
        LogManager().append(f"[AutoReplay] 开始回放 {len(events)} 个事件，间隔 {delay_ms}ms")
        self._replay_next_step()

    def _stop_auto_replay(self):
        """停止自动回放。"""
        if hasattr(self, "_replay_timer") and self._replay_timer:
            self._replay_timer.stop()
        self._replay_index = 0
        LogManager().append("[AutoReplay] 回放已停止")

    def _replay_next_step(self):
        """执行下一个回放事件。"""
        if not hasattr(self, "_replay_events") or self._replay_index >= len(self._replay_events):
            self._stop_auto_replay()
            return
        event = self._replay_events[self._replay_index]
        x, y = event["x"], event["y"]
        frame_x, frame_y = self._map_device_to_frame(x, y)
        if frame_x is None:
            LogManager().append(f"[AutoReplay] 坐标映射失败: ({x},{y})")
            self._replay_index += 1
            if self._replay_index < len(self._replay_events):
                self._replay_timer.start(self._replay_delay_ms)
            return
        try:
            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_DOWN)

            def _do_up():
                time.sleep(0.05)
                self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_UP)

            threading.Thread(target=_do_up, daemon=True).start()
        except Exception as e:
            LogManager().append(f"[AutoReplay] 发送触摸失败: {e}")
        self._replay_index += 1
        if self._replay_index < len(self._replay_events):
            self._replay_timer.start(self._replay_delay_ms)
        else:
            LogManager().append("[AutoReplay] 回放完成")

    def _show_behavior_tree(self):
        """打开行为树生成对话框。"""
        dialog = BehaviorTreeDialog(self)
        dialog.exec()

    def _show_semantic_aggregation(self):
        """打开语义动作聚合面板。"""
        dialog = SemanticAggregationDialog(self)
        dialog.exec()

    def _show_kickoff_dashboard(self):
        """打开启动完成度仪表盘对话框。"""
        dialog = KickoffDashboardDialog(self, self)
        dialog.exec()

    def _show_reanalyze_history(self):
        """打开 Reanalyze 历史记录对话框。"""
        from reanalyze_logger import get_logger

        logger = get_logger()
        records = logger.read_all(limit=200)
        stats = logger.get_stats()

        dialog = QDialog(self)
        dialog.setWindowTitle("GPT-5.5 Reanalyze 历史记录")
        dialog.resize(960, 720)
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(12, 12, 12, 12)
        dialog_layout.setSpacing(8)

        # 统计信息
        stats_label = QLabel(
            f"总计调用: {stats['total_calls']} | 成功: {stats['success']} | 失败: {stats['failed']} | "
            f"总对象数: {stats['total_objects']} | 平均耗时: {stats['avg_duration_ms']:.0f}ms"
        )
        stats_label.setStyleSheet("color: #9cdcfe; font-size: 12px; padding: 4px;")
        dialog_layout.addWidget(stats_label)

        # 历史记录列表
        history_table = QTableWidget(dialog)
        history_table.setColumnCount(8)
        history_table.setHorizontalHeaderLabels(
            ["时间", "场景", "模型", "对象数", "修改数", "耗时(ms)", "状态", "图片路径"]
        )
        history_table.setColumnWidth(0, 150)
        history_table.setColumnWidth(1, 100)
        history_table.setColumnWidth(2, 120)
        history_table.setColumnWidth(3, 55)
        history_table.setColumnWidth(4, 55)
        history_table.setColumnWidth(5, 70)
        history_table.setColumnWidth(6, 55)
        history_table.setColumnWidth(7, 240)
        history_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; }"
            "QHeaderView::section { background-color: #3c3c3c; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        history_table.horizontalHeader().setStretchLastSection(True)
        history_table.setRowCount(len(records))

        for row, rec in enumerate(records):
            ts = rec.get("timestamp", "")
            folder = rec.get("folder", "")
            model = rec.get("model", "")
            obj_count = rec.get("object_count", 0)
            duration = rec.get("duration_ms", 0)
            success = rec.get("success", False)
            img_path = rec.get("image_path", "")

            mod_count = rec.get("modified_count", 0)
            history_table.setItem(row, 0, QTableWidgetItem(ts))
            history_table.setItem(row, 1, QTableWidgetItem(Path(folder).name))
            history_table.setItem(row, 2, QTableWidgetItem(model))
            history_table.setItem(row, 3, QTableWidgetItem(str(obj_count)))
            mod_item = QTableWidgetItem(str(mod_count))
            if mod_count > 0:
                mod_item.setForeground(QBrush(QColor("#ffcc00")))
            history_table.setItem(row, 4, mod_item)
            history_table.setItem(row, 5, QTableWidgetItem(f"{duration:.0f}"))
            status_item = QTableWidgetItem("成功" if success else "失败")
            status_item.setForeground(QBrush(QColor("#6a9955" if success else "#f44747")))
            history_table.setItem(row, 6, status_item)
            history_table.setItem(row, 7, QTableWidgetItem(img_path))

        dialog_layout.addWidget(history_table, 1)

        # 详情区域
        detail_label = QLabel("选中记录详情：")
        detail_label.setStyleSheet("color: #cccccc; font-weight: bold; padding-top: 8px;")
        dialog_layout.addWidget(detail_label)

        detail_text = QTextEdit(dialog)
        detail_text.setReadOnly(True)
        detail_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; padding: 6px; font-family: Consolas, monospace; font-size: 12px; }"
        )
        detail_text.setMaximumHeight(280)
        dialog_layout.addWidget(detail_text)

        def on_selection_changed():
            rows = history_table.selectionModel().selectedRows()
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(records):
                rec = records[row]
                lines = [
                    f"时间: {rec.get('timestamp', '')}",
                    f"图片: {rec.get('image_path', '')}",
                    f"场景: {rec.get('folder', '')}",
                    f"模型: {rec.get('model', '')}",
                    f"成功: {rec.get('success', False)}",
                    f"对象数: {rec.get('object_count', 0)}",
                    f"修改数: {rec.get('modified_count', 0)}",
                    f"耗时: {rec.get('duration_ms', 0):.2f}ms",
                    "",
                    "--- Objects ---",
                ]
                for oi, obj in enumerate(rec.get("objects", [])):
                    mod_flag = "[改]" if obj.get("modified") else "[原]"
                    lines.append(
                        f"{oi+1}. {mod_flag} {obj.get('class_name','')} | "
                        f"role={obj.get('role','')} | "
                        f"bbox={obj.get('bbox_xyxy','')} | "
                        f"src={obj.get('source','')}"
                    )
                lines.extend([
                    "",
                    "--- Prompt ---",
                    rec.get("prompt", "")[:2000],
                    "",
                    "--- Raw Response ---",
                    rec.get("raw_response", "")[:3000],
                ])
                if rec.get("error"):
                    lines.extend(["", "--- Error ---", rec["error"]])
                detail_text.setPlainText("\n".join(lines))

        history_table.itemSelectionChanged.connect(on_selection_changed)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_open_image = QPushButton("打开图片", dialog)
        btn_open_image.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )

        def _open_selected_image():
            rows = history_table.selectionModel().selectedRows()
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(records):
                img_path = records[row].get("image_path", "")
                if img_path and Path(img_path).exists():
                    import os
                    os.startfile(img_path)

        btn_open_image.clicked.connect(_open_selected_image)
        btn_row.addWidget(btn_open_image)

        btn_open_folder = QPushButton("打开文件夹", dialog)
        btn_open_folder.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )

        def _open_selected_folder():
            rows = history_table.selectionModel().selectedRows()
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(records):
                folder = records[row].get("folder", "")
                if folder and Path(folder).exists():
                    import os
                    os.startfile(folder)

        btn_open_folder.clicked.connect(_open_selected_folder)
        btn_row.addWidget(btn_open_folder)

        btn_refresh = QPushButton("刷新", dialog)
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )

        def _refresh_history():
            nonlocal records, stats
            records = logger.read_all(limit=200)
            stats = logger.get_stats()
            stats_label.setText(
                f"总计调用: {stats['total_calls']} | 成功: {stats['success']} | 失败: {stats['failed']} | "
                f"总对象数: {stats['total_objects']} | 平均耗时: {stats['avg_duration_ms']:.0f}ms"
            )
            history_table.setRowCount(len(records))
            for row, rec in enumerate(records):
                ts = rec.get("timestamp", "")
                folder = rec.get("folder", "")
                model = rec.get("model", "")
                obj_count = rec.get("object_count", 0)
                duration = rec.get("duration_ms", 0)
                success = rec.get("success", False)
                img_path = rec.get("image_path", "")
                mod_count = rec.get("modified_count", 0)

                history_table.setItem(row, 0, QTableWidgetItem(ts))
                history_table.setItem(row, 1, QTableWidgetItem(Path(folder).name))
                history_table.setItem(row, 2, QTableWidgetItem(model))
                history_table.setItem(row, 3, QTableWidgetItem(str(obj_count)))
                mod_item = QTableWidgetItem(str(mod_count))
                if mod_count > 0:
                    mod_item.setForeground(QBrush(QColor("#ffcc00")))
                history_table.setItem(row, 4, mod_item)
                history_table.setItem(row, 5, QTableWidgetItem(f"{duration:.0f}"))
                status_item = QTableWidgetItem("成功" if success else "失败")
                status_item.setForeground(QBrush(QColor("#6a9955" if success else "#f44747")))
                history_table.setItem(row, 6, status_item)
                history_table.setItem(row, 7, QTableWidgetItem(img_path))
            detail_text.clear()

        btn_refresh.clicked.connect(_refresh_history)
        btn_row.addWidget(btn_refresh)

        btn_close = QPushButton("关闭", dialog)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_close.clicked.connect(dialog.close)
        btn_row.addWidget(btn_close)
        btn_row.addStretch(1)

        dialog_layout.addLayout(btn_row)
        dialog.exec()

    # ------------------------------------------------------------------
    # TODO Dialogs
    # ------------------------------------------------------------------
    def _show_yolo_class_merge(self):
        show_yolo_class_merge(self)

    def _show_batch_scene_register(self):
        show_batch_scene_register(self)

    def _show_fast_feature(self):
        show_fast_feature(self)

    def _show_migration_tool(self):
        show_migration_tool(self)

    def _show_cloud_sync(self):
        show_cloud_sync(self)

    def _show_rl_stats(self):
        show_rl_stats(self)

    def _switch_game(self):
        switch_game(self, self.execution_engine, self._set_status)

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
                self._write_recording_meta(finished=True)
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
