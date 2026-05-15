import sys
import threading
import time
import os
from pathlib import Path

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

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QToolButton,
    QWidget,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import QTimer

from ui_main_window import Ui_MainWindow
from video_widget import VideoGLWidget
from log_manager import LogManager
from execution_engine import ExecutionEngine
from scene_index import UnknownFolderProcessor
from ui.widgets.signal_bridge import SignalBridge
from analysis.mixins import AnalysisMixin
from services.mixins import ServicesMixin
from ui.panels.mixins import PanelsMixin


class MainWindow(
    PanelsMixin,
    ServicesMixin,
    AnalysisMixin,
    QMainWindow,
):
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

        # 执行引擎（不阻塞主界面）
        self.execution_engine = ExecutionEngine()
        self.execution_engine.status_changed.connect(self._update_status_ui)
        self.execution_engine.task_added.connect(self._on_task_added)
        self.execution_engine.task_subtask_added.connect(self._on_task_subtask_added)
        self.execution_engine.task_cleared.connect(self._on_task_cleared)
        self.execution_engine.task_done.connect(self._on_task_done)
        self.execution_engine.scene_image_ready.connect(self._show_scene_image)
        self.execution_engine.motion_heatmap_ready.connect(self._on_motion_heatmap)

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

        # 文件菜单：只保留退出
        self.ui.menuFile.clear()
        self.ui.menuFile.addAction(self.ui.actionExit)

        # 工具菜单 - 只保留视频回放
        self.ui.menuTools = QMenu("工具(&T)", self)
        self.ui.actionVideoReplay = QAction("视频回放", self)
        self.ui.actionVideoReplay.triggered.connect(self._show_video_replay)
        self.ui.menuTools.addAction(self.ui.actionVideoReplay)
        self.ui.menubar.addAction(self.ui.menuTools.menuAction())

        # 退出
        self.ui.actionExit.triggered.connect(self.close)

    # ------------------------------------------------------------------
    # TODO: 执行引擎信号槽和自动化决策方法已移至 PanelsMixin
    # 如需在此处实现特定逻辑，请在对应的 Panel Mixin 中添加
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # TODO Dialogs
    # ------------------------------------------------------------------

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
