"""YOLO Class Merge & Management Dialog."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QLineEdit, QTextEdit, QSplitter, QWidget, QGroupBox,
)
from PySide6.QtCore import Qt

from yolo_class_manager import YoloClassManager, normalize_class_name
from log_manager import LogManager


class YoloClassMergeDialog(QDialog):
    def __init__(self, classes_txt: Path, labels_dir: Path | None, parent=None):
        super().__init__(parent)
        self.classes_txt = classes_txt
        self.labels_dir = labels_dir
        self.mgr = YoloClassManager(classes_txt)
        self.setWindowTitle("YOLO Class Merge & Manager")
        self.resize(900, 700)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top info
        info = QLabel(
            f"Total classes: {len(self.mgr.names)}  |  "
            f"Labels dir: {self.labels_dir or 'N/A'}"
        )
        layout.addWidget(info)
        self._info_label = info

        # Class table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["ID", "Name", "Aliases", "Action"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self._table)

        # Suggestions group
        sug_group = QGroupBox("Merge Suggestions")
        sug_layout = QVBoxLayout(sug_group)
        self._sug_table = QTableWidget()
        self._sug_table.setColumnCount(4)
        self._sug_table.setHorizontalHeaderLabels(["Keep", "Merge", "Similarity", "Action"])
        self._sug_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._sug_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        sug_layout.addWidget(self._sug_table)
        btn_refresh_sug = QPushButton("Refresh Suggestions")
        btn_refresh_sug.clicked.connect(self._refresh_suggestions)
        sug_layout.addWidget(btn_refresh_sug)
        layout.addWidget(sug_group)

        # Normalization test
        test_group = QGroupBox("Normalization Test")
        test_layout = QHBoxLayout(test_group)
        self._test_input = QLineEdit()
        self._test_input.setPlaceholderText("Enter raw class name...")
        test_layout.addWidget(self._test_input)
        btn_test = QPushButton("Test")
        btn_test.clicked.connect(self._on_test)
        test_layout.addWidget(btn_test)
        self._test_output = QLabel("-")
        test_layout.addWidget(self._test_output)
        layout.addWidget(test_group)

        # Batch merge
        batch_group = QGroupBox("Batch Operations")
        batch_layout = QHBoxLayout(batch_group)
        btn_normalize_all = QPushButton("Normalize All Classes")
        btn_normalize_all.clicked.connect(self._normalize_all)
        batch_layout.addWidget(btn_normalize_all)
        btn_rebuild = QPushButton("Rebuild from Labels")
        btn_rebuild.clicked.connect(self._rebuild_from_labels)
        batch_layout.addWidget(btn_rebuild)
        layout.addWidget(batch_group)

        # Bottom buttons
        btns = QHBoxLayout()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _refresh(self):
        names = self.mgr.names
        self._table.setRowCount(len(names))
        for i, name in enumerate(names):
            self._table.setItem(i, 0, QTableWidgetItem(str(i)))
            self._table.setItem(i, 1, QTableWidgetItem(name))
            # Find aliases
            alias_list = [raw for raw, can in self.mgr.aliases.items() if can == name]
            alias_text = ", ".join(alias_list[:10])
            if len(alias_list) > 10:
                alias_text += f" ... ({len(alias_list)} total)"
            self._table.setItem(i, 2, QTableWidgetItem(alias_text))
            btn = QPushButton("Delete")
            btn.clicked.connect(lambda checked=False, n=name: self._delete_class(n))
            self._table.setCellWidget(i, 3, btn)
        self._info_label.setText(
            f"Total classes: {len(names)}  |  "
            f"Labels dir: {self.labels_dir or 'N/A'}"
        )
        self._refresh_suggestions()

    def _refresh_suggestions(self):
        suggestions = self.mgr.suggest_merges(threshold=0.70)
        self._sug_table.setRowCount(len(suggestions))
        for i, sug in enumerate(suggestions):
            self._sug_table.setItem(i, 0, QTableWidgetItem(sug.keep))
            self._sug_table.setItem(i, 1, QTableWidgetItem(sug.merge))
            item = QTableWidgetItem(f"{sug.similarity:.2f}")
            item.setToolTip(sug.reason)
            self._sug_table.setItem(i, 2, item)
            btn = QPushButton("Merge")
            btn.clicked.connect(lambda checked=False, s=sug: self._merge_class(s.merge, s.keep))
            self._sug_table.setCellWidget(i, 3, btn)

    def _delete_class(self, name: str):
        if name not in self.mgr.names:
            return
        if len(self.mgr.names) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "At least one class must remain.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete class '{name}'?\nThis does NOT update label files yet.",
        )
        if reply != QMessageBox.Yes:
            return
        self.mgr.names.remove(name)
        self.mgr.save()
        self._refresh()
        LogManager().append(f"[YOLO] deleted class '{name}'")

    def _merge_class(self, merge_name: str, into_name: str):
        reply = QMessageBox.question(
            self, "Confirm Merge",
            f"Merge class '{merge_name}' -> '{into_name}'?\n"
            f"Label files will be rewritten.",
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.mgr.merge(merge_name, into_name, self.labels_dir)
            self._refresh()
            LogManager().append(f"[YOLO] merged '{merge_name}' -> '{into_name}'")
        except Exception as e:
            QMessageBox.critical(self, "Merge Failed", str(e))

    def _on_test(self):
        raw = self._test_input.text().strip()
        result = normalize_class_name(raw)
        self._test_output.setText(f"{result}")

    def _normalize_all(self):
        """Rewrite classes.txt with normalized names, update aliases."""
        old_names = list(self.mgr.names)
        new_names = []
        name_map: dict[str, str] = {}
        for old in old_names:
            new = normalize_class_name(old)
            name_map[old] = new
            if new not in new_names:
                new_names.append(new)

        # Build alias mapping
        for old, new in name_map.items():
            if old != new:
                self.mgr.aliases[old] = new

        self.mgr.names = new_names
        self.mgr.save()

        # Rewrite label files
        if self.labels_dir and self.labels_dir.exists():
            for txt_file in self.labels_dir.rglob("*.txt"):
                lines = txt_file.read_text(encoding="utf-8").splitlines()
                new_lines = []
                changed = False
                for line in lines:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    try:
                        cid = int(parts[0])
                    except ValueError:
                        new_lines.append(line)
                        continue
                    if cid < len(old_names):
                        old_name = old_names[cid]
                        new_name = name_map.get(old_name, old_name)
                        new_cid = new_names.index(new_name)
                        if new_cid != cid:
                            parts[0] = str(new_cid)
                            new_lines.append(" ".join(parts))
                            changed = True
                            continue
                    new_lines.append(line)
                if changed:
                    txt_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        self._refresh()
        QMessageBox.information(
            self, "Normalize Done",
            f"Normalized {len(old_names)} classes -> {len(new_names)} classes."
        )
        LogManager().append(f"[YOLO] normalized classes {len(old_names)} -> {len(new_names)}")

    def _rebuild_from_labels(self):
        if not self.labels_dir or not self.labels_dir.exists():
            QMessageBox.warning(self, "No Labels Dir", "Label directory not available.")
            return
        mapping = self.mgr.rebuild_from_labels(self.labels_dir)
        self._refresh()
        QMessageBox.information(
            self, "Rebuild Done",
            f"Rebuilt class list from labels. Now {len(mapping)} classes."
        )
