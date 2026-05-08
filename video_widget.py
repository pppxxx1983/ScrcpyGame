import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt


class VideoGLWidget(QWidget):
    """视频渲染控件，用 QPainter + QImage 绘制，兼容所有平台"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._image = None
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: #000000;")
        self._frame_count = 0
        self.on_touch = None          # callback(frame_x, frame_y, action)
        self.on_scroll = None         # callback(frame_x, frame_y, h, v)

    def set_frame(self, frame: np.ndarray):
        """可从任意线程调用，scrcpy 帧回调里直接塞"""
        if frame is None or frame.size == 0:
            return
        h, w = frame.shape[:2]
        self._frame = frame.copy()
        self._image = QImage(
            self._frame.data, w, h, w * 3, QImage.Format_RGB888
        ).copy()
        self.update()

    def _map_to_frame(self, wx: int, wy: int):
        """把控件坐标映射到视频帧坐标，返回 (fx, fy)，不在画面内返回 (None, None)"""
        if self._frame is None:
            return None, None
        img_h, img_w = self._frame.shape[:2]
        widget_w, widget_h = self.width(), self.height()
        scale = min(widget_w / img_w, widget_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        offset_x = (widget_w - new_w) // 2
        offset_y = (widget_h - new_h) // 2

        if wx < offset_x or wx > offset_x + new_w or wy < offset_y or wy > offset_y + new_h:
            return None, None

        fx = int((wx - offset_x) / scale)
        fy = int((wy - offset_y) / scale)
        fx = max(0, min(fx, img_w - 1))
        fy = max(0, min(fy, img_h - 1))
        return fx, fy

    def mousePressEvent(self, event):
        if self.on_touch and event.button() == Qt.LeftButton:
            fx, fy = self._map_to_frame(event.pos().x(), event.pos().y())
            if fx is not None:
                self.on_touch(fx, fy, 0)   # ACTION_DOWN

    def mouseMoveEvent(self, event):
        if self.on_touch and event.buttons() & Qt.LeftButton:
            fx, fy = self._map_to_frame(event.pos().x(), event.pos().y())
            if fx is not None:
                self.on_touch(fx, fy, 2)   # ACTION_MOVE

    def mouseReleaseEvent(self, event):
        if self.on_touch and event.button() == Qt.LeftButton:
            fx, fy = self._map_to_frame(event.pos().x(), event.pos().y())
            if fx is not None:
                self.on_touch(fx, fy, 1)   # ACTION_UP

    def wheelEvent(self, event):
        if self.on_scroll:
            pos = event.position().toPoint()
            fx, fy = self._map_to_frame(pos.x(), pos.y())
            if fx is not None:
                # angleDelta 一次通常是 120 的倍数，缩小一点给 Android
                h = event.angleDelta().x() // 10
                v = event.angleDelta().y() // 10
                if h != 0 or v != 0:
                    self.on_scroll(fx, fy, h, v)

    def paintEvent(self, event):
        if self._image is None:
            return
        painter = QPainter(self)
        img_w, img_h = self._image.width(), self._image.height()
        widget_w, widget_h = self.width(), self.height()
        scale = min(widget_w / img_w, widget_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        x = (widget_w - new_w) // 2
        y = (widget_h - new_h) // 2
        painter.drawImage(x, y, self._image.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        painter.end()
