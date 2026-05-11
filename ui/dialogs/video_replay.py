from pathlib import Path
import json
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
)
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtCore import Signal, Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from log_manager import LogManager

class TimelineWidget(QWidget):
    """自定义时间轴控件：显示进度条 + 事件标记点。"""

    seek_requested = Signal(int)  # 毫秒

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration_ms = 0
        self._position_ms = 0
        self._events = []  # [{"offset_ms": int, "label": str, "color": str}]
        self._hover_idx = -1
        self._dragging = False
        self.setMinimumHeight(48)
        self.setMaximumHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_duration(self, ms: int):
        self._duration_ms = max(1, ms)
        self.update()

    def set_position(self, ms: int):
        self._position_ms = max(0, min(self._duration_ms, ms))
        self.update()

    def set_events(self, events: list):
        self._events = events
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        w = self.width()
        bar_h = 8
        bar_y = h - bar_h - 8

        # 背景条
        painter.fillRect(4, bar_y, w - 8, bar_h, QColor("#333333"))

        # 已播放进度
        if self._duration_ms > 0:
            ratio = self._position_ms / self._duration_ms
            filled_w = int((w - 8) * ratio)
            painter.fillRect(4, bar_y, filled_w, bar_h, QColor("#0e639c"))

        # 事件标记点
        for ev in self._events:
            offset = ev.get("media_offset_ms", ev.get("offset_ms", 0))
            if self._duration_ms > 0:
                x = 4 + int((w - 8) * (offset / self._duration_ms))
                color = QColor(ev.get("color", "#ffcc00"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(x - 4, bar_y - 3, 8, 8)
                # 竖线
                painter.setPen(QPen(color, 1))
                painter.drawLine(x, 4, x, bar_y - 4)

        # 当前位置指示器
        if self._duration_ms > 0:
            ratio = self._position_ms / self._duration_ms
            cx = 4 + int((w - 8) * ratio)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(cx - 5, bar_y - 1, 10, 10)

        painter.end()

    def mousePressEvent(self, event):
        if self._duration_ms <= 0 or event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self._seek_from_x(event.position().x(), emit=False)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._seek_from_x(event.position().x(), emit=False)
            event.accept()
            return
        self._update_hover(event)

    def mouseReleaseEvent(self, event):
        if self._duration_ms <= 0 or event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = False
        self._seek_from_x(event.position().x(), emit=True)
        event.accept()

    def _seek_from_x(self, x_pos: float, emit: bool):
        w = self.width()
        x = max(4, min(w - 4, x_pos))
        ratio = (x - 4) / max(1, w - 8)
        ms = int(ratio * self._duration_ms)
        self.set_position(ms)
        if emit:
            self.seek_requested.emit(ms)

    def _update_hover(self, event):
        if self._duration_ms <= 0 or not self._events:
            self._hover_idx = -1
            return
        w = self.width()
        x = event.position().x()
        best = -1
        best_dist = 9999
        for i, ev in enumerate(self._events):
            ex = 4 + int((w - 8) * (ev.get("media_offset_ms", ev.get("offset_ms", 0)) / self._duration_ms))
            dist = abs(x - ex)
            if dist < best_dist and dist < 12:
                best_dist = dist
                best = i
        if best != self._hover_idx:
            self._hover_idx = best
            if best >= 0:
                ev = self._events[best]
                QToolTip.showText(self.mapToGlobal(event.position().toPoint()), ev.get("label", ""))
            else:
                QToolTip.hideText()
        self.update()


class VideoReplayDialog(QDialog):
    """视频回放中心：文件列表 + 播放器 + 时间轴事件标记 + 事件列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("视频回放中心")
        self.resize(1280, 760)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.3)
        self._player.setAudioOutput(self._audio)
        self._current_events = []
        self._current_video_path = ""
        self._current_meta = {}

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 左侧：录像文件列表
        left = QWidget()
        left.setFixedWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        lbl_videos = QLabel("录像文件")
        lbl_videos.setStyleSheet("font-weight: bold; color: #cccccc;")
        left_layout.addWidget(lbl_videos)

        self.video_list = QListWidget(left)
        self.video_list.setStyleSheet(
            "QListWidget { background-color: #252526; color: #cccccc; border: 1px solid #3c3c3c; padding: 4px; }"
            "QListWidget::item { padding: 6px; border-bottom: 1px solid #333333; }"
            "QListWidget::item:selected { background-color: #0e639c; }"
            "QListWidget::item:hover { background-color: #2a2d2e; }"
        )
        self.video_list.itemClicked.connect(self._on_video_selected)
        left_layout.addWidget(self.video_list, 1)

        btn_refresh = QPushButton("刷新列表")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_refresh.clicked.connect(self._scan_videos)
        left_layout.addWidget(btn_refresh)
        main_layout.addWidget(left)

        # 中间：视频播放器 + 时间轴 + 控制按钮
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        self.video_widget = QVideoWidget(center)
        self.video_widget.setMinimumHeight(400)
        self.video_widget.setStyleSheet("background-color: #000000; border: 1px solid #333333;")
        self._player.setVideoOutput(self.video_widget)
        center_layout.addWidget(self.video_widget, 1)

        # 时间轴
        self.timeline = TimelineWidget(center)
        self.timeline.seek_requested.connect(self._seek_to)
        center_layout.addWidget(self.timeline)

        # 控制栏
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedWidth(40)
        self.btn_play.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
        )
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.btn_play)

        self.lbl_time = QLabel("0:00 / 0:00")
        self.lbl_time.setStyleSheet("color: #cccccc; font-family: Consolas;")
        self.lbl_time.setFixedWidth(120)
        ctrl.addWidget(self.lbl_time)

        ctrl.addStretch(1)

        center_layout.addLayout(ctrl)
        main_layout.addWidget(center, 1)

        # 右侧：事件列表
        right = QWidget()
        right.setFixedWidth(260)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        lbl_events = QLabel("事件列表")
        lbl_events.setStyleSheet("font-weight: bold; color: #cccccc;")
        right_layout.addWidget(lbl_events)

        self.event_table = QTableWidget(right)
        self.event_table.setColumnCount(3)
        self.event_table.setHorizontalHeaderLabels(["时间", "操作", "坐标"])
        self.event_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.event_table.setColumnWidth(0, 60)
        self.event_table.setColumnWidth(1, 100)
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.event_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.event_table.itemDoubleClicked.connect(self._on_event_double_clicked)
        right_layout.addWidget(self.event_table, 1)

        self.event_info = QLabel("")
        self.event_info.setWordWrap(True)
        self.event_info.setStyleSheet("color: #888888; font-size: 11px; padding: 4px;")
        right_layout.addWidget(self.event_info)

        main_layout.addWidget(right)

        # 播放器信号
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self._scan_videos()

    def _scan_videos(self):
        self.video_list.clear()
        self._video_items = []
        roots = [
            (Path("recordings"), "手动录制"),
            (Path("game_agent_data") / "games" / "my_game" / "raw_videos", "Session"),
        ]
        for root, kind in roots:
            if not root.exists():
                continue
            for mp4 in sorted(root.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
                meta = self._read_video_meta(mp4, kind)
                text = f"[{kind}] {mp4.name[:20]}..." if len(mp4.name) > 20 else f"[{kind}] {mp4.name}"
                item = QListWidgetItem(text)
                item.setData(256, str(mp4))
                item.setData(257, meta)
                item.setToolTip(str(mp4))
                self.video_list.addItem(item)
        if self.video_list.count() == 0:
            self.video_list.addItem("暂无录像文件")

    def _read_video_meta(self, mp4: Path, kind: str) -> dict:
        meta = {"kind": kind, "duration_ms": 0, "fps": 20, "frame_count": 0}
        # 手动录制：找 .meta.json
        if kind == "手动录制":
            meta_path = mp4.parent / f"{mp4.stem}.meta.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["duration_ms"] = data.get("duration_ms") or data.get("video_offset_ms", 0)
                    meta["fps"] = data.get("fps", 20)
                    meta["frame_count"] = data.get("frame_count", 0)
                except Exception:
                    pass
        # Session：找 recording_meta.json
        else:
            session_dir = mp4.parent.parent / "sessions" / mp4.stem
            meta_path = session_dir / "recording_meta.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["duration_ms"] = data.get("duration_ms") or data.get("video_offset_ms", 0)
                    meta["fps"] = data.get("fps", 20)
                    meta["frame_count"] = data.get("frame_count", 0)
                except Exception:
                    pass
        return meta

    def _on_video_selected(self, item: QListWidgetItem):
        path = item.data(256)
        if not path or not Path(path).exists():
            return
        self._current_video_path = path
        self._current_meta = item.data(257) or {}
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self._load_events(path)
        self.btn_play.setText("▶")
        self.lbl_time.setText("0:00 / 0:00")

    def _load_events(self, video_path: str):
        self._current_events = []
        video_path = Path(video_path)
        events_path = None

        # 手动录制：找 .events.jsonl
        if video_path.parent.name == "recordings":
            events_path = video_path.parent / f"{video_path.stem}.events.jsonl"
        # Session：找 operations.jsonl
        else:
            session_dir = video_path.parent.parent / "sessions" / video_path.stem
            ops_path = session_dir / "operations.jsonl"
            if ops_path.exists():
                events_path = ops_path

        if events_path and events_path.exists():
            try:
                for line in events_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    offset = data.get("video_offset_ms")
                    if offset is None:
                        continue
                    action = data.get("action_type", "")
                    touch = data.get("touch", {})
                    start = touch.get("start", {}) if isinstance(touch, dict) else {}
                    x = start.get("x", "-")
                    y = start.get("y", "-")
                    logical_offset_ms = int(offset)
                    self._current_events.append({
                        "offset_ms": logical_offset_ms,
                        "media_offset_ms": logical_offset_ms,
                        "action": action,
                        "x": x,
                        "y": y,
                        "raw": data,
                        "label": f"{action} ({x},{y})",
                        "color": "#ffcc00",
                    })
                self._current_events.sort(key=lambda e: e["offset_ms"])
            except Exception as e:
                LogManager().append(f"[VideoReplay] 加载事件失败: {e}")

        # 更新时间轴事件标记
        duration = self._player.duration()
        self._apply_event_media_offsets(duration)
        self.timeline.set_events(self._current_events)
        self.timeline.set_duration(duration)
        self._update_event_table()

    def _logical_duration_ms(self) -> int:
        meta_duration = int((self._current_meta or {}).get("duration_ms") or 0)
        if meta_duration > 0:
            return meta_duration
        return max((int(ev.get("offset_ms") or 0) for ev in self._current_events), default=0)

    def _apply_event_media_offsets(self, media_duration_ms: int):
        logical_duration = self._logical_duration_ms()
        if media_duration_ms <= 0 or logical_duration <= 0:
            for ev in self._current_events:
                ev["media_offset_ms"] = int(ev.get("offset_ms") or 0)
            return

        ratio = media_duration_ms / logical_duration
        if ratio < 0.8 or ratio > 1.2:
            LogManager().append(
                f"[VideoReplay] event time scale adjusted: media={media_duration_ms}ms, "
                f"logical={logical_duration}ms, ratio={ratio:.3f}"
            )
        for ev in self._current_events:
            logical_offset = int(ev.get("offset_ms") or 0)
            ev["media_offset_ms"] = max(0, min(media_duration_ms, int(logical_offset * ratio)))

    def _update_event_table(self):
        self.event_table.setRowCount(len(self._current_events))
        for row, ev in enumerate(self._current_events):
            sec = ev.get("media_offset_ms", ev["offset_ms"]) / 1000
            time_str = f"{int(sec // 60)}:{int(sec % 60):02d}"
            self.event_table.setItem(row, 0, QTableWidgetItem(time_str))
            self.event_table.setItem(row, 1, QTableWidgetItem(ev["action"]))
            self.event_table.setItem(row, 2, QTableWidgetItem(f"({ev['x']},{ev['y']})"))
            self.event_table.item(row, 0).setData(256, ev.get("media_offset_ms", ev["offset_ms"]))

    def _on_event_double_clicked(self, item: QTableWidgetItem):
        offset = item.data(256)
        if offset is not None:
            self._seek_to(offset)
            self._player.play()

    def _seek_to(self, ms: int):
        dur = self._player.duration()
        target = max(0, min(int(ms), dur if dur > 0 else int(ms)))
        if hasattr(self._player, "isSeekable") and not self._player.isSeekable():
            LogManager().append("[VideoReplay] player reports media is not seekable")
        was_paused = self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        self._player.setPosition(target)
        self.timeline.set_position(target)
        self.lbl_time.setText(f"{self._fmt(target)} / {self._fmt(dur)}")
        if was_paused:
            self._player.play()
            QTimer.singleShot(80, self._player.pause)

    def _toggle_play(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸")
        else:
            self.btn_play.setText("▶")

    def _on_position_changed(self, pos: int):
        self.timeline.set_position(pos)
        dur = self._player.duration()
        self.lbl_time.setText(f"{self._fmt(pos)} / {self._fmt(dur)}")

    def _on_duration_changed(self, dur: int):
        self._apply_event_media_offsets(dur)
        self.timeline.set_events(self._current_events)
        self._update_event_table()
        self.timeline.set_duration(dur)
        self.lbl_time.setText(f"{self._fmt(self._player.position())} / {self._fmt(dur)}")

    @staticmethod
    def _fmt(ms: int) -> str:
        s = max(0, ms) // 1000
        return f"{s // 60}:{s % 60:02d}"
