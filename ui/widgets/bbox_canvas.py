from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtCore import Signal, Qt

class BBoxCanvas(QWidget):
    objects_changed = Signal()
    selection_changed = Signal(int)

    def __init__(self, image_path: Path, objects: list[dict], parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.objects = objects
        self.selected_index = 0
        self._pixmap = QPixmap(str(image_path.resolve()))
        self._drag = None
        self.setMinimumSize(720, 420)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #111111;")

    def set_selected_index(self, index: int):
        self.selected_index = max(0, min(index, len(self.objects) - 1)) if self.objects else 0
        self.update()

    def _image_rect(self):
        if self._pixmap.isNull():
            return None
        area = self.rect()
        scaled = self._pixmap.size()
        scaled.scale(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = area.x() + (area.width() - scaled.width()) // 2
        y = area.y() + (area.height() - scaled.height()) // 2
        return x, y, scaled.width(), scaled.height()

    def _to_widget(self, x: int, y: int):
        rect = self._image_rect()
        if not rect or self._pixmap.isNull():
            return x, y
        rx, ry, rw, rh = rect
        return rx + x * rw / self._pixmap.width(), ry + y * rh / self._pixmap.height()

    def _to_image(self, x: int, y: int):
        rect = self._image_rect()
        if not rect or self._pixmap.isNull():
            return x, y
        rx, ry, rw, rh = rect
        ix = int((x - rx) * self._pixmap.width() / max(1, rw))
        iy = int((y - ry) * self._pixmap.height() / max(1, rh))
        return (
            max(0, min(self._pixmap.width() - 1, ix)),
            max(0, min(self._pixmap.height() - 1, iy)),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111111"))
        rect = self._image_rect()
        if not rect or self._pixmap.isNull():
            painter.setPen(QColor("#f44747"))
            painter.drawText(20, 40, "image load failed")
            painter.end()
            return
        rx, ry, rw, rh = rect
        painter.drawPixmap(rx, ry, rw, rh, self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for idx, obj in enumerate(self.objects):
            bbox = obj.get("bbox_xyxy") or []
            if len(bbox) != 4:
                continue
            x1, y1 = self._to_widget(int(bbox[0]), int(bbox[1]))
            x2, y2 = self._to_widget(int(bbox[2]), int(bbox[3]))
            selected = idx == self.selected_index
            color = QColor("#ff4040") if selected else QColor("#4ec9b0")
            painter.setPen(QPen(color, 3 if selected else 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            label = str(obj.get("class_name") or "ui_element")
            painter.fillRect(int(x1), max(0, int(y1) - 22), min(220, len(label) * 9 + 16), 22, QColor(163, 21, 21, 128) if selected else QColor(16, 124, 93, 64))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(x1) + 6, max(16, int(y1) - 6), label)
            if selected:
                painter.setBrush(QColor("#ff4040"))
                painter.setPen(QPen(QColor("#111111"), 1))
                for hx, hy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
                    painter.drawRect(int(hx) - 5, int(hy) - 5, 10, 10)
        painter.end()

    def _hit_test(self, pos):
        px, py = pos.x(), pos.y()
        best = None
        for idx, obj in enumerate(self.objects):
            bbox = obj.get("bbox_xyxy") or []
            if len(bbox) != 4:
                continue
            points = {
                "tl": self._to_widget(int(bbox[0]), int(bbox[1])),
                "tr": self._to_widget(int(bbox[2]), int(bbox[1])),
                "bl": self._to_widget(int(bbox[0]), int(bbox[3])),
                "br": self._to_widget(int(bbox[2]), int(bbox[3])),
            }
            for handle, (hx, hy) in points.items():
                if abs(px - hx) <= 10 and abs(py - hy) <= 10:
                    return idx, handle
            x1, y1 = points["tl"]
            x2, y2 = points["br"]
            if x1 <= px <= x2 and y1 <= py <= y2:
                best = (idx, "move")
        return best

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit_test(event.position().toPoint())
        if not hit:
            return
        idx, handle = hit
        self.selected_index = idx
        self.selection_changed.emit(idx)
        ix, iy = self._to_image(int(event.position().x()), int(event.position().y()))
        bbox = list(self.objects[idx].get("bbox_xyxy") or [0, 0, 1, 1])
        self._drag = {"index": idx, "handle": handle, "start": (ix, iy), "bbox": bbox}
        self.update()

    def mouseMoveEvent(self, event):
        if not self._drag:
            return
        idx = self._drag["index"]
        if idx >= len(self.objects):
            return
        ix, iy = self._to_image(int(event.position().x()), int(event.position().y()))
        x1, y1, x2, y2 = list(self._drag["bbox"])
        handle = self._drag["handle"]
        if handle == "move":
            sx, sy = self._drag["start"]
            dx, dy = ix - sx, iy - sy
            w, h = x2 - x1, y2 - y1
            x1 = max(0, min(self._pixmap.width() - w, x1 + dx))
            y1 = max(0, min(self._pixmap.height() - h, y1 + dy))
            x2, y2 = x1 + w, y1 + h
        else:
            if "l" in handle:
                x1 = ix
            if "r" in handle:
                x2 = ix
            if "t" in handle:
                y1 = iy
            if "b" in handle:
                y2 = iy
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            x2 = max(x1 + 1, x2)
            y2 = max(y1 + 1, y2)
        self.objects[idx]["bbox_xyxy"] = [int(x1), int(y1), int(x2), int(y2)]
        self.objects_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag:
            idx = self._drag["index"]
            if 0 <= idx < len(self.objects):
                self.objects[idx]["modified"] = True
        self._drag = None

