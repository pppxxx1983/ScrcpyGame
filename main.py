import re
import struct
import sys
import threading
import time
import json
from pathlib import Path

import scrcpy
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QButtonGroup, QToolButton,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
    QHBoxLayout, QTextEdit, QSizePolicy
)
from PySide6.QtCore import QTimer, QObject, Signal, Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont

from ui_main_window import Ui_MainWindow
from video_widget import VideoGLWidget
from log_manager import LogManager


class SignalBridge(QObject):
    status_changed = Signal(str, str)
    buttons_changed = Signal(bool)


class AnnotatedImageLabel(QLabel):
    def __init__(self, image_path: Path, title: str, touch: dict, parent=None):
        super().__init__(parent)
        self._annotated_pixmap = self._build_pixmap(image_path, title, touch)
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

    def _build_pixmap(self, image_path: Path, title: str, touch: dict) -> QPixmap:
        pixmap = QPixmap(str(image_path))
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

        painter.end()
        return annotated

    def _points_for_image(self, pixmap: QPixmap, touch: dict):
        width = pixmap.width()
        height = pixmap.height()
        if not touch:
            return None, None

        if width <= 1200 and "frame_start" in touch and "frame_end" in touch:
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
        self.setFixedSize(144, 92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(title)
        self.setStyleSheet(
            "QLabel { background-color: #111111; border: 1px solid #333333; "
            "color: #cccccc; padding: 2px; }"
        )
        pixmap = QPixmap(str(image_path))
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
            self.video_widget.on_touch = self._on_touch
            self.video_widget.on_scroll = self._on_scroll
            if layout and idx >= 0:
                layout.replaceWidget(old_widget, self.video_widget)
            old_widget.deleteLater()

        # 跨线程信号桥（必须在 setupUi 之后创建）
        self._bridge = SignalBridge(self)
        self._bridge.status_changed.connect(self._update_status_ui)
        self._bridge.buttons_changed.connect(self._update_connect_buttons_slot)

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
        self._setup_file_panel()

        def on_activity_clicked(btn):
            if not self.side_panel:
                return
            name = btn.objectName()
            self.side_panel.setVisible(name in ("btnAndroid", "btnSearch"))
            if self.ui.tabConnect:
                self.ui.tabConnect.setVisible(name == "btnAndroid")
            if self.file_panel:
                self.file_panel.setVisible(name == "btnSearch")
            if name == "btnSearch":
                self._refresh_screenshot_folders()

        for name in ["btnAndroid", "btnSearch", "btnGit", "btnRun", "btnExt"]:
            btn = self.findChild(QToolButton, name)
            if btn:
                btn.clicked.connect(lambda checked, b=btn: on_activity_clicked(b))

        if self.side_panel:
            self.side_panel.setVisible(True)
        if self.file_panel:
            self.file_panel.setVisible(False)

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

        title = QLabel("screenshots")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        refresh_btn = QPushButton("刷新文件夹")
        refresh_btn.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        refresh_btn.clicked.connect(self._refresh_screenshot_folders)
        panel_layout.addWidget(refresh_btn)

        self.list_screenshot_folders = QListWidget(self.file_panel)
        self.list_screenshot_folders.setObjectName("listScreenshotFolders")
        self.list_screenshot_folders.setStyleSheet(
            "QListWidget { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 4px; }"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background-color: #0e639c; color: white; }"
            "QListWidget::item:hover { background-color: #2a2d2e; }"
        )
        self.list_screenshot_folders.itemClicked.connect(self._open_screenshot_folder_tab)
        panel_layout.addWidget(self.list_screenshot_folders)

        layout.insertWidget(1, self.file_panel)
        self.file_panel.setVisible(False)
        self._refresh_screenshot_folders()

    def _refresh_screenshot_folders(self):
        if self.list_screenshot_folders is None:
            return
        self.list_screenshot_folders.clear()
        root = Path("screenshots")
        root.mkdir(exist_ok=True)
        folders = [p for p in root.iterdir() if p.is_dir()]
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
        folder = Path(folder_text)
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
                json_text = json.dumps(data, ensure_ascii=False, indent=2)
            except Exception as e:
                json_text = f"index.json read failed: {e}"

        touch = data.get("touch", {})
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

        def set_detail(label, name):
            old = current_detail["widget"]
            replacement = AnnotatedImageLabel(folder / name, label, touch, detail_holder)
            detail_layout.replaceWidget(old, replacement)
            old.deleteLater()
            current_detail["widget"] = replacement

        if not image_names:
            empty = QLabel("No PNG images")
            empty.setStyleSheet("color: #888888; padding: 12px;")
            left_layout.addWidget(empty)
        else:
            for label, name in image_names:
                thumb = ImageThumbnailLabel(
                    folder / name,
                    label,
                    lambda l=label, n=name: set_detail(l, n),
                    left_panel,
                )
                left_layout.addWidget(thumb)

        left_layout.addStretch(1)
        body.addWidget(left_panel, 0)
        body.addWidget(detail_holder, 1)

        if image_names:
            first_label, first_name = image_names[0]
            QTimer.singleShot(0, lambda: set_detail(first_label, first_name))
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
                    item = QListWidgetItem(f"{d.serial}  ({d.prop.model})")
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
            m = re.search(r'(\d+)x(\d+)', output)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                return (w, h)
            # fallback: dumpsys
            output = d.shell("dumpsys window displays | grep -E 'init|DisplayDeviceInfo'")
            m = re.search(r'(\d+)\s*x\s*(\d+)', output)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                return (w, h)
        except Exception:
            pass
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

        import time
        frame_count = [0]
        last_fps_time = [time.time()]

        def on_frame(frame):
            if frame is not None and self.video_widget is not None:
                frame_count[0] += 1
                import numpy as np
                rgb = np.ascontiguousarray(frame[..., ::-1])
                self.video_widget.set_frame(rgb)
                now = time.time()
                if now - last_fps_time[0] >= 1.0:
                    fps = frame_count[0]
                    frame_count[0] = 0
                    last_fps_time[0] = now
                    self._set_status(f"状态: 已连接 | FPS: {fps}", log=False)

        def on_init():
            # 优先使用 scrcpy 握手时的分辨率（和视频流方向 guaranteed 一致）
            cr = self.client.resolution
            if cr and len(cr) == 2 and all(isinstance(v, int) and 0 < v < 10000 for v in cr):
                self._device_resolution = cr
            elif self._device_resolution is None:
                self._device_resolution = self._get_device_resolution(device)
            else:
                pass
            self._update_connect_buttons(True)
            self._set_status("状态: 已连接")

        def on_disconnect():
            self._update_connect_buttons(False)
            self._set_status("状态: 已断开")

        def run():
            try:
                self.client = scrcpy.Client(
                    device=device,
                    max_width=1080,
                    bitrate=8000000,
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

    def _update_status_ui(self, text, color):
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
            return None, None
        fh, fw = frame.shape[:2]
        dw, dh = self._device_resolution  # wm size 返回的固定值，如 (900, 1600)

        # 视频帧宽高比反映设备当前方向
        if fw > fh:
            # 横屏：实际宽 = max(dw,dh)，高 = min(dw,dh)
            screen_w = max(dw, dh)
            screen_h = min(dw, dh)
        else:
            # 竖屏：实际宽 = min(dw,dh)，高 = max(dw,dh)
            screen_w = min(dw, dh)
            screen_h = max(dw, dh)

        x = int(frame_x * screen_w / fw)
        y = int(frame_y * screen_h / fh)
        x = max(0, min(x, screen_w - 1))
        y = max(0, min(y, screen_h - 1))
        return x, y

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
            before_pressed = (
                self._image_change_score(before_path, pressed_path, frame_start)
                if before_path.exists() and pressed_path.exists()
                else {}
            )
            before_after = (
                self._image_change_score(before_path, after_path, frame_start)
                if before_path.exists() and after_path.exists()
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
            if before_path.exists():
                try:
                    from scene_index import SceneIndex

                    data["scene_index"] = SceneIndex().ensure_scene(
                        before_path,
                        threshold=0.92,
                        describe_model="qwen3-vl:2b",
                    )
                except Exception as e:
                    data["scene_index"] = {"error": str(e)}
            with open(op_dir / "index.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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

    def _on_touch(self, frame_x: int, frame_y: int, action: int):
        device_x, device_y = self._map_frame_to_device(frame_x, frame_y)
        if device_x is None:
            return
        if action == 0:          # DOWN
            from datetime import datetime

            self._touch_start = (device_x, device_y)
            self._touch_last = (device_x, device_y)
            self._touch_frame_start = (frame_x, frame_y)
            self._touch_frame_last = (frame_x, frame_y)
            self._touch_time = time.time()

            # 主线程先把操作目录建好，避免 UP 时还没读到
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            op_dir = Path("screenshots") / f"op_{ts}"
            op_dir.mkdir(parents=True, exist_ok=True)
            self._op_dir_for_touch = op_dir
            self._save_video_frame_sync("before", op_dir)
            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_DOWN)

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
        device_x, device_y = self._map_frame_to_device(frame_x, frame_y)
        if device_x is None:
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

    def closeEvent(self, event):
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
