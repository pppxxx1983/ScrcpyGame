from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt

from log_manager import LogManager
from ui.widgets.image_labels import YoloReviewImageLabel
from ui.dialogs.bbox_editor import BBoxEditorDialog




from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class YoloAuditPanelMixin:
    def _load_yolo_audit_state(self, folder: Path):
        index_path = folder / "index.json"
        if not index_path.exists():
            self._set_status(f"YOLO audit: missing index.json in {folder.name}")
            return None
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._set_status(f"YOLO audit: index read failed - {e}")
            return None

        image_name = data.get("images", {}).get("before") or "before.png"
        image_path = folder / image_name
        if not image_path.exists():
            self._set_status(f"YOLO audit: image missing - {image_path}")
            return None

        objects = self._yolo_objects_from_event(data)
        if not objects:
            objects = [{
                "class_name": data.get("click_target", {}).get("element_name") or "tap_target",
                "bbox_xyxy": data.get("click_target", {}).get("bbox_xyxy") or [0, 0, 80, 80],
                "role": "clicked_target",
                "source": "manual",
            }]
        return data, image_path, objects

    def _get_or_reset_yolo_audit_tab(self):
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
        return audit_tab, layout

    def _open_yolo_audit_tab(self, folder: Path):
        state = self._load_yolo_audit_state(folder)
        if state is None:
            return
        data, image_path, objects = state
        selected = {"index": 0}
        audit_tab, layout = self._get_or_reset_yolo_audit_tab()

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

