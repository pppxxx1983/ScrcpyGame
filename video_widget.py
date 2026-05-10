import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QImage, QPainter, QFont, QColor, QPen
from PySide6.QtCore import Qt, QRect, QTimer


class VideoGLWidget(QWidget):
    """视频渲染控件，用 QPainter + QImage 绘制，兼容所有平台"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._image = None
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: #000000;")
        self._touch_points = []
        self._touch_feedback_timer = QTimer(self)
        self._touch_feedback_timer.setSingleShot(True)
        self._touch_feedback_timer.timeout.connect(self.clear_touch_feedback)
        self._frame_count = 0
        self.on_touch = None          # callback(frame_x, frame_y, action)
        self.on_scroll = None         # callback(frame_x, frame_y, h, v)
        self._overlay_text = ""       # 场景识别名字叠加文字

    def show_touch_feedback(self, points, hold_ms: int = 450):
        self._touch_points = [(int(x), int(y)) for x, y in points if x is not None and y is not None]
        if hold_ms > 0:
            self._touch_feedback_timer.start(hold_ms)
        self.update()
        self.repaint()

    def clear_touch_feedback(self):
        self._touch_points = []
        self.update()

    def _frame_to_widget(self, fx: int, fy: int, x: int, y: int, new_w: int, new_h: int):
        if self._image is None:
            return None
        img_w, img_h = self._image.width(), self._image.height()
        return (
            x + int(fx * new_w / max(1, img_w)),
            y + int(fy * new_h / max(1, img_h)),
        )

    def set_frame(self, frame: np.ndarray):
        """可从任意线程调用，只做引用保存和触发重绘，不拷贝。"""
        if frame is None or frame.size == 0:
            return
        try:
            _ = self.width()
        except RuntimeError:
            return
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
        self._frame = frame
        h, w = frame.shape[:2]
        self._image = QImage(
            frame.data,
            w,
            h,
            frame.strides[0],
            QImage.Format.Format_RGB888,
        )
        try:
            self.update()
        except RuntimeError:
            pass

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

    def set_overlay_text(self, text: str):
        """设置左上角叠加文字（如场景识别名字），空字符串表示不显示。"""
        self._overlay_text = text
        self.update()

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
        # FastTransformation 避免 CPU 高质量缩放造成延迟
        painter.drawImage(QRect(x, y, new_w, new_h), self._image)

        # 绘制场景识别名字（左上角，半透明黑底白字）
        if self._overlay_text:
            font = QFont("Microsoft YaHei", 18, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text = self._overlay_text
            text_w = fm.horizontalAdvance(text) + 20
            text_h = fm.height() + 14
            pad_x = x + 12
            pad_y = y + 12
            painter.fillRect(pad_x, pad_y, text_w, text_h, QColor(0, 0, 0, 180))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(pad_x + 10, pad_y + fm.ascent() + 7, text)

        touch_points = getattr(self, "_touch_points", [])
        if touch_points:
            points = [
                self._frame_to_widget(px, py, x, y, new_w, new_h)
                for px, py in touch_points
            ]
            points = [p for p in points if p is not None]
            if points:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(QColor(255, 204, 0, 230), 5))
                for first, second in zip(points, points[1:]):
                    painter.drawLine(first[0], first[1], second[0], second[1])

                sx, sy = points[0]
                ex, ey = points[-1]
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(0, 0, 0, 210), 7))
                painter.drawEllipse(sx - 24, sy - 24, 48, 48)
                painter.setPen(QPen(QColor(255, 64, 64, 245), 4))
                painter.drawEllipse(sx - 24, sy - 24, 48, 48)
                painter.drawLine(sx - 32, sy, sx + 32, sy)
                painter.drawLine(sx, sy - 32, sx, sy + 32)

                if len(points) > 1:
                    painter.setPen(QPen(QColor(0, 0, 0, 210), 7))
                    painter.drawEllipse(ex - 20, ey - 20, 40, 40)
                    painter.setPen(QPen(QColor(64, 216, 255, 245), 4))
                    painter.drawEllipse(ex - 20, ey - 20, 40, 40)

        painter.end()
