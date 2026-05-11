"""Batch scene registration dialog for unknown screenshots."""
from __future__ import annotations

import time
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QProgressBar, QLineEdit, QComboBox, QCheckBox, QFileDialog,
    QTextEdit, QGroupBox, QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal

from log_manager import LogManager


class BatchRegisterWorker(QThread):
    progress = Signal(int, int, str)  # current, total, message
    item_done = Signal(int, dict)  # row, result_dict
    finished_all = Signal()

    def __init__(self, items: list[tuple[int, Path]], method: str, model: str, parent=None):
        super().__init__(parent)
        self.items = items
        self.method = method
        self.model = model
        self._stop = False

    def run(self):
        total = len(self.items)
        for idx, (row, img_path) in enumerate(self.items):
            if self._stop:
                break
            self.progress.emit(idx + 1, total, f"Processing {img_path.name} ...")
            result = self._process_one(img_path)
            self.item_done.emit(row, result)
        self.finished_all.emit()

    def _process_one(self, img_path: Path) -> dict:
        try:
            from PIL import Image
            from scene_index import image_fingerprint, SceneIndex

            fp = image_fingerprint(img_path)
            if self.method == "hash":
                # Try to find similar existing scene
                si = SceneIndex()
                match = si.find_best(img_path, threshold=0.88)
                if match and match.get("confidence", 0) >= 0.88:
                    return {
                        "status": "hash_matched",
                        "scene_key": match.get("scene_key", "unknown"),
                        "confidence": match.get("confidence", 0),
                        "dhash": fp["dhash"],
                    }
                return {"status": "hash_no_match", "dhash": fp["dhash"]}

            elif self.method in ("ollama", "qwen"):
                # Use LLM vision to classify
                from llm_client import QwenVLClient
                client = QwenVLClient()
                prompt = (
                    "Analyze this game screenshot. Give a very short scene name (1-3 words, English snake_case). "
                    "Output ONLY the scene name, nothing else."
                )
                model_name = self.model or ("qwen-vl-max" if self.method == "qwen" else "qwen3-vl:8b")
                resp = client.describe_image(str(img_path), prompt, model=model_name)
                text = resp if isinstance(resp, str) else str(resp)
                # Clean up
                name = text.strip().lower().replace(" ", "_").replace("-", "_")[:32]
                name = "".join(c for c in name if c.isalnum() or c == "_") or "unknown_scene"
                return {"status": "llm_classified", "scene_key": name, "raw": text}
            else:
                return {"status": "error", "error": f"unknown method {self.method}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def stop(self):
        self._stop = True


class SceneBatchRegisterDialog(QDialog):
    def __init__(self, unknown_dir: Path, parent=None):
        super().__init__(parent)
        self.unknown_dir = unknown_dir
        self.setWindowTitle("Batch Scene Registration")
        self.resize(1100, 750)
        self._worker: BatchRegisterWorker | None = None
        self._build_ui()
        self._scan_folder()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Unknown folder:"))
        self._path_edit = QLineEdit(str(self.unknown_dir))
        ctrl.addWidget(self._path_edit, 1)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._browse)
        ctrl.addWidget(btn_browse)
        btn_scan = QPushButton("Rescan")
        btn_scan.clicked.connect(self._scan_folder)
        ctrl.addWidget(btn_scan)
        layout.addLayout(ctrl)

        # Method selection
        method_box = QGroupBox("Registration Method")
        method_layout = QHBoxLayout(method_box)
        self._method_combo = QComboBox()
        self._method_combo.addItems(["hash (match existing)", "ollama (local LLM)", "qwen (cloud LLM)"])
        method_layout.addWidget(QLabel("Method:"))
        method_layout.addWidget(self._method_combo)
        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("Optional model override (e.g. qwen3-vl:8b)")
        method_layout.addWidget(QLabel("Model:"))
        method_layout.addWidget(self._model_edit, 1)
        self._auto_move = QCheckBox("Auto-move to classified folder")
        self._auto_move.setChecked(True)
        method_layout.addWidget(self._auto_move)
        layout.addWidget(method_box)

        # Progress
        prog = QHBoxLayout()
        self._prog_bar = QProgressBar()
        prog.addWidget(self._prog_bar)
        self._prog_label = QLabel("Idle")
        prog.addWidget(self._prog_label)
        layout.addLayout(prog)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["File", "dhash", "Status", "Scene Key", "Confidence", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self._table)

        # Batch actions
        btns = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(self._select_all)
        btns.addWidget(btn_select_all)
        btn_run = QPushButton("Run Batch Registration")
        btn_run.setStyleSheet("QPushButton { background-color: #0e639c; color: white; padding: 8px; }")
        btn_run.clicked.connect(self._run_batch)
        btns.addWidget(btn_run)
        btn_register_selected = QPushButton("Register Selected")
        btn_register_selected.clicked.connect(self._register_selected)
        btns.addWidget(btn_register_selected)
        btn_stop = QPushButton("Stop")
        btn_stop.clicked.connect(self._stop_worker)
        btns.addWidget(btn_stop)
        btns.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

        # Log
        self._log = QTextEdit()
        self._log.setMaximumHeight(120)
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Unknown Folder", str(self.unknown_dir))
        if path:
            self.unknown_dir = Path(path)
            self._path_edit.setText(str(self.unknown_dir))
            self._scan_folder()

    def _scan_folder(self):
        self.unknown_dir = Path(self._path_edit.text().strip())
        files = sorted(
            [f for f in self.unknown_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")],
            key=lambda x: x.name,
        )
        self._table.setRowCount(len(files))
        self._files = files
        for i, f in enumerate(files):
            self._table.setItem(i, 0, QTableWidgetItem(f.name))
            self._table.setItem(i, 1, QTableWidgetItem(""))
            self._table.setItem(i, 2, QTableWidgetItem("pending"))
            self._table.setItem(i, 3, QTableWidgetItem(""))
            self._table.setItem(i, 4, QTableWidgetItem(""))
            # Action buttons per row
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(2, 2, 2, 2)
            btn_reg = QPushButton("Reg")
            btn_reg.clicked.connect(lambda checked=False, r=i: self._register_one(r))
            hl.addWidget(btn_reg)
            btn_del = QPushButton("Del")
            btn_del.clicked.connect(lambda checked=False, r=i: self._delete_one(r))
            hl.addWidget(btn_del)
            self._table.setCellWidget(i, 5, w)
        self._prog_label.setText(f"Found {len(files)} images")

    def _select_all(self):
        self._table.selectAll()

    def _run_batch(self):
        method_map = {"hash (match existing)": "hash", "ollama (local LLM)": "ollama", "qwen (cloud LLM)": "qwen"}
        method = method_map[self._method_combo.currentText()]
        model = self._model_edit.text().strip()
        items = [(i, f) for i, f in enumerate(self._files)]
        if not items:
            return
        self._prog_bar.setMaximum(len(items))
        self._prog_bar.setValue(0)
        self._worker = BatchRegisterWorker(items, method, model, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current: int, total: int, msg: str):
        self._prog_bar.setValue(current)
        self._prog_label.setText(f"{current}/{total}: {msg}")

    def _on_item_done(self, row: int, result: dict):
        status = result.get("status", "unknown")
        self._table.setItem(row, 2, QTableWidgetItem(status))
        self._table.setItem(row, 3, QTableWidgetItem(result.get("scene_key", "")))
        conf = result.get("confidence", "")
        self._table.setItem(row, 4, QTableWidgetItem(f"{conf:.3f}" if isinstance(conf, float) else str(conf)))
        if "dhash" in result:
            self._table.setItem(row, 1, QTableWidgetItem(result["dhash"]))
        self._log.append(f"[{row}] {status}: {result.get('scene_key', '')} {result.get('error', '')}")

    def _on_finished(self):
        self._prog_label.setText("Batch done")
        self._worker = None

    def _stop_worker(self):
        if self._worker:
            self._worker.stop()

    def _register_one(self, row: int):
        if row < 0 or row >= len(self._files):
            return
        img_path = self._files[row]
        scene_key = self._table.item(row, 3)
        key = scene_key.text().strip() if scene_key else ""
        if not key:
            # Prompt user
            from PySide6.QtWidgets import QInputDialog
            key, ok = QInputDialog.getText(self, "Scene Name", f"Name for {img_path.name}:")
            if not ok or not key:
                return
            key = key.strip().lower().replace(" ", "_")[:32]
        self._do_register(img_path, key)
        self._table.setItem(row, 2, QTableWidgetItem("registered"))

    def _register_selected(self):
        selected = self._table.selectionModel().selectedRows()
        for idx in selected:
            row = idx.row()
            self._register_one(row)

    def _do_register(self, img_path: Path, scene_key: str):
        try:
            from scene_index import image_fingerprint, SceneIndex
            from agent_data import GAME_DATA_DIR

            target_dir = Path("screenshots") / scene_key
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / img_path.name
            shutil.copy2(str(img_path), str(target_path))

            fp = image_fingerprint(target_path)
            si = SceneIndex()
            si.add_scene(
                scene_key=scene_key,
                dhash=fp["dhash"],
                ahash=fp["ahash"],
                description="",
                image_path=str(target_path),
                width=fp["width"],
                height=fp["height"],
                model_name="batch_register",
                recognize_cost=0,
            )
            if self._auto_move.isChecked() and img_path.parent == self.unknown_dir:
                img_path.unlink(missing_ok=True)
            LogManager().append(f"[BatchReg] registered {img_path.name} -> {scene_key}")
        except Exception as e:
            LogManager().append(f"[BatchReg] register failed: {e}")

    def _delete_one(self, row: int):
        if row < 0 or row >= len(self._files):
            return
        img_path = self._files[row]
        reply = QMessageBox.question(self, "Delete", f"Delete {img_path.name}?")
        if reply == QMessageBox.Yes:
            img_path.unlink(missing_ok=True)
            self._scan_folder()
