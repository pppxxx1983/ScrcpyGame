from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget





from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
class EventVideoPanelMixin:
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

