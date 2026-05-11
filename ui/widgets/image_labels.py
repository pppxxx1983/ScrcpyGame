from pathlib import Path
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal

class AnnotatedImageLabel(QLabel):
    def __init__(self, image_path: Path, title: str, touch: dict, yolo: dict | None = None, event_data: dict | None = None, parent=None):
        super().__init__(parent)
        self._annotated_pixmap = self._build_pixmap(image_path, title, touch, yolo or {}, event_data or {})
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

    def _build_pixmap(self, image_path: Path, title: str, touch: dict, yolo: dict, event_data: dict) -> QPixmap:
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

        draw_items = []
        click_target = event_data.get("click_target", {}) if isinstance(event_data.get("click_target"), dict) else {}
        if click_target.get("bbox_xyxy"):
            draw_items.append({
                "bbox_xyxy": click_target.get("bbox_xyxy"),
                "label": click_target.get("element_name") or click_target.get("status") or "click_target",
                "kind": "runtime_rule" if click_target.get("status") == "runtime_rule_matched" else "click_target",
            })

        for obj in event_data.get("gpt_yolo_objects", {}).get("objects", []) if isinstance(event_data.get("gpt_yolo_objects"), dict) else []:
            if obj.get("bbox_xyxy"):
                draw_items.append({
                    "bbox_xyxy": obj.get("bbox_xyxy"),
                    "label": obj.get("class_name") or obj.get("name") or "gpt",
                    "kind": "gpt",
                })

        yolo_objects = yolo.get("objects") or []
        if not yolo_objects and yolo.get("bbox_xyxy"):
            yolo_objects = [yolo]
        for yolo_obj in yolo_objects:
            if yolo_obj.get("bbox_xyxy"):
                draw_items.append({
                    "bbox_xyxy": yolo_obj.get("bbox_xyxy"),
                    "label": yolo_obj.get("class_name") or "yolo",
                    "kind": "approved" if yolo_obj.get("review_status") == "approved" else yolo_obj.get("source") or "yolo",
                })

        seen = set()
        deduped = []
        for item in draw_items:
            bbox = item.get("bbox_xyxy") or []
            key = (item.get("kind"), tuple(int(v) for v in bbox)) if len(bbox) == 4 else None
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        for yolo_obj in deduped:
            bbox = yolo_obj.get("bbox_xyxy")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            x1 = max(0, min(annotated.width() - 1, x1))
            y1 = max(0, min(annotated.height() - 1, y1))
            x2 = max(x1 + 1, min(annotated.width(), x2))
            y2 = max(y1 + 1, min(annotated.height(), y2))

            kind = yolo_obj.get("kind", "yolo")
            if kind == "runtime_rule":
                box_color = QColor("#4ec9b0")
                fill_color = QColor("#107c5d")
                prefix = "RULE"
            elif kind == "gpt":
                box_color = QColor("#d670d6")
                fill_color = QColor("#7f3f98")
                prefix = "GPT"
            elif kind == "click_target":
                box_color = QColor("#ffcc00")
                fill_color = QColor("#8a6d00")
                prefix = "TARGET"
            elif kind == "approved":
                box_color = QColor("#40d8ff")
                fill_color = QColor("#0e639c")
                prefix = "APPROVED"
            else:
                box_color = QColor("#9cdcfe")
                fill_color = QColor("#264f78")
                prefix = "YOLO"

            box_pen = QPen(box_color, 4)
            painter.setPen(box_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

            label = f"{prefix} {yolo_obj.get('label') or 'ui'}"
            painter.setFont(QFont("Microsoft YaHei", 14))
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(label) + 12
            text_h = fm.height() + 6
            label_y = max(0, y1 - text_h)
            painter.fillRect(x1, label_y, text_w, text_h, fill_color)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(x1 + 6, label_y + text_h - 7, label)

        if deduped:
            legend = "GREEN=rule  YELLOW=target  BLUE=approved  PURPLE=GPT"
            painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            lw = fm.horizontalAdvance(legend) + 16
            lh = fm.height() + 8
            painter.fillRect(12, annotated.height() - lh - 12, lw, lh, QColor(0, 0, 0, 170))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(20, annotated.height() - 20, legend)

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


class YoloReviewImageLabel(QLabel):
    def __init__(self, image_path: Path, objects: list[dict], selected_index: int = 0, parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self._objects = objects
        self._selected_index = selected_index
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(420, 320)
        self.setStyleSheet("background-color: #111111; border: 1px solid #333333;")
        self._orig = QPixmap(str(image_path.resolve()))
        self._annotated = QPixmap()
        self._rebuild()

    def set_objects(self, objects: list[dict], selected_index: int = 0):
        self._objects = objects
        self._selected_index = selected_index
        self._rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled()

    def _rebuild(self):
        if self._orig.isNull():
            fallback = QPixmap(520, 160)
            fallback.fill(QColor("#1e1e1e"))
            painter = QPainter(fallback)
            painter.setPen(QColor("#f44747"))
            painter.drawText(12, 36, "image load failed")
            painter.end()
            self._annotated = fallback
            self._update_scaled()
            return

        canvas = QPixmap(self._orig)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for idx, obj in enumerate(self._objects):
            bbox = obj.get("bbox_xyxy") or []
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            approved = bool(obj.get("review_approved") or obj.get("review_status") == "approved")
            if idx == self._selected_index:
                color = QColor("#ff4040")
                fill = QColor(163, 21, 21, 150)
            elif approved:
                color = QColor("#40d8ff")
                fill = QColor(14, 99, 156, 120)
            else:
                color = QColor("#9cdcfe")
                fill = QColor(38, 79, 120, 90)
            painter.setPen(QPen(color, 5 if idx == self._selected_index else 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

            state = "OK" if approved else "CAND"
            source = str(obj.get("source") or "")[:10]
            label = f"{state} {obj.get('class_name') or 'ui_element'}"
            if source:
                label += f" · {source}"
            painter.setFont(QFont("Microsoft YaHei", 13))
            fm = painter.fontMetrics()
            text_w = min(canvas.width() - x1, fm.horizontalAdvance(label) + 12)
            text_h = fm.height() + 6
            label_y = max(0, y1 - text_h)
            painter.fillRect(x1, label_y, text_w, text_h, fill)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(x1 + 6, label_y + text_h - 7, label)
        legend = "RED=selected  BLUE=approved  LIGHT=候选"
        painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        lw = fm.horizontalAdvance(legend) + 16
        lh = fm.height() + 8
        painter.fillRect(12, canvas.height() - lh - 12, lw, lh, QColor(0, 0, 0, 170))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(20, canvas.height() - 20, legend)
        painter.end()
        self._annotated = canvas
        self._update_scaled()

    def _update_scaled(self):
        if self._annotated.isNull():
            return
        available = self.contentsRect().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        self.setPixmap(
            self._annotated.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

