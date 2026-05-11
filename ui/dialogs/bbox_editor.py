from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSpinBox,
    QDialog,
)
from PySide6.QtCore import Signal
from ui.widgets.bbox_canvas import BBoxCanvas

class BBoxEditorDialog(QDialog):
    def __init__(self, image_path: Path, objects: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("BBox Editor")
        self.resize(1180, 760)
        self.objects = [dict(obj) for obj in objects]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.canvas = BBoxCanvas(image_path, self.objects, self)
        layout.addWidget(self.canvas, 1)

        side = QWidget(self)
        side.setFixedWidth(340)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget(side)
        self.list_widget.setStyleSheet("QListWidget { background-color: #252526; color: #cccccc; }")
        side_layout.addWidget(self.list_widget, 1)

        self.label_edit = QLineEdit(side)
        self.label_edit.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        side_layout.addWidget(QLabel("Label"))
        side_layout.addWidget(self.label_edit)
        self.spins = {}
        for name in ["x1", "y1", "x2", "y2"]:
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            spin = QSpinBox(side)
            spin.setRange(0, 10000)
            spin.setStyleSheet("QSpinBox { background-color: #3c3c3c; color: #cccccc; }")
            row.addWidget(spin, 1)
            side_layout.addLayout(row)
            self.spins[name] = spin

        row = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_delete = QPushButton("Delete")
        row.addWidget(btn_add)
        row.addWidget(btn_delete)
        side_layout.addLayout(row)

        row2 = QHBoxLayout()
        btn_ok = QPushButton("Apply")
        btn_cancel = QPushButton("Cancel")
        row2.addWidget(btn_ok)
        row2.addWidget(btn_cancel)
        side_layout.addLayout(row2)
        layout.addWidget(side)

        self._updating = False
        self.list_widget.currentRowChanged.connect(self._select)
        self.canvas.selection_changed.connect(self.list_widget.setCurrentRow)
        self.canvas.objects_changed.connect(self._refresh_fields)
        self.label_edit.textEdited.connect(self._label_changed)
        for spin in self.spins.values():
            spin.valueChanged.connect(self._spin_changed)
        btn_add.clicked.connect(self._add_box)
        btn_delete.clicked.connect(self._delete_box)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        self._refresh_list()
        if self.objects:
            self.list_widget.setCurrentRow(0)

    def _refresh_list(self):
        current = self.list_widget.currentRow()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for idx, obj in enumerate(self.objects):
            self.list_widget.addItem(f"{idx + 1}. {obj.get('class_name') or 'ui_element'} {obj.get('bbox_xyxy')}")
        if self.objects:
            self.list_widget.setCurrentRow(max(0, min(current, len(self.objects) - 1)))
        self.list_widget.blockSignals(False)

    def _select(self, index: int):
        if index < 0 or index >= len(self.objects):
            return
        self.canvas.set_selected_index(index)
        self._refresh_fields()

    def _refresh_fields(self):
        idx = self.list_widget.currentRow()
        if idx < 0 or idx >= len(self.objects):
            return
        self._updating = True
        obj = self.objects[idx]
        self.label_edit.setText(str(obj.get("class_name") or "ui_element"))
        bbox = obj.get("bbox_xyxy") or [0, 0, 1, 1]
        for key, value in zip(["x1", "y1", "x2", "y2"], bbox):
            self.spins[key].setValue(int(value))
        self._updating = False
        self._refresh_list()

    def _label_changed(self, text: str):
        if self._updating:
            return
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.objects):
            self.objects[idx]["class_name"] = text.strip() or "ui_element"
            self.objects[idx]["modified"] = True
            self.canvas.update()
            self._refresh_list()

    def _spin_changed(self):
        if self._updating:
            return
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.objects):
            x1 = self.spins["x1"].value()
            y1 = self.spins["y1"].value()
            x2 = max(x1 + 1, self.spins["x2"].value())
            y2 = max(y1 + 1, self.spins["y2"].value())
            self.objects[idx]["bbox_xyxy"] = [x1, y1, x2, y2]
            self.objects[idx]["modified"] = True
            self.canvas.update()
            self._refresh_list()

    def _add_box(self):
        self.objects.append({"class_name": "ui_element", "bbox_xyxy": [20, 20, 140, 100], "role": "ui_element", "source": "manual_editor", "modified": True})
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self.objects) - 1)
        self.canvas.update()

    def _delete_box(self):
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.objects):
            self.objects.pop(idx)
            self._refresh_list()
            self.canvas.update()

    def edited_objects(self) -> list[dict]:
        return [dict(obj) for obj in self.objects]

