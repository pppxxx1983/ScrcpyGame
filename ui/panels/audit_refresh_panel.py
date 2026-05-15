from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt

from log_manager import LogManager
from scene_index import SceneIndex

from analysis.scene_classifier import (
    SceneLevel, SceneState, SCENE_LEVEL_DISPLAY, SCENE_STATE_DISPLAY,
)

from PySide6.QtWidgets import QTreeWidgetItem


class AuditRefreshPanelMixin:
    def _refresh_audit_list(self):
        """从 scene_index.sqlite 读取场景列表并展示，支持按审核状态单选过滤。"""
        self.audit_list.clear()
        is_yolo = getattr(self, "rb_audit_yolo", None) and self.rb_audit_yolo.isChecked()
        if getattr(self, "batch_btn_row", None):
            for i in range(self.batch_btn_row.count()):
                w = self.batch_btn_row.itemAt(i).widget()
                if w:
                    w.setVisible(is_yolo)
        if is_yolo:
            self._refresh_yolo_audit_list()
            return
        self.audit_list.setHeaderLabels(["场景", "层级", "状态", "命中", "模型", "状态", "时间"])
        try:
            from scene_index import SceneIndex
            si = SceneIndex()
            status_filter = 1 if self.rb_approved.isChecked() else 0
            with si._connect() as conn:
                rows = conn.execute(
                    """SELECT id, scene_key, scene_level, scene_state, scene_context,
                              hits, model_name, review_status, created_at, image_path
                       FROM scenes WHERE review_status = ? ORDER BY hits DESC""",
                    (status_filter,),
                ).fetchall()
            for row in rows:
                row_id, scene_key, scene_level, scene_state, scene_context, hits, model_name, review_status, created_at, image_path = row
                item = QTreeWidgetItem()
                item.setText(0, str(scene_key))
                level_display = SCENE_LEVEL_DISPLAY.get(SceneLevel(scene_level), scene_level) if scene_level else "未分类"
                item.setText(1, level_display)
                state_display = SCENE_STATE_DISPLAY.get(SceneState(scene_state), scene_state) if scene_state else ""
                item.setText(2, state_display)
                item.setText(3, str(hits))
                item.setText(4, str(model_name))
                item.setText(5, "审核通过" if review_status else "未审核")
                item.setText(6, str(created_at))
                item.setData(0, 256, row_id)
                item.setData(0, 257, str(image_path))
                self.audit_list.addTopLevelItem(item)
        except Exception as e:
            LogManager().append(f"[Audit] 刷新场景列表失败: {e}")

    def _open_audit_item(self, item: QTreeWidgetItem):
        item_type = item.data(0, 258)
        if item_type == "yolo_event":
            folder = item.data(0, 257)
            if folder:
                self._open_yolo_audit_tab(Path(folder))
            return
        self._open_audit_scene_tab(item)

    def _refresh_yolo_audit_list(self):
        self.audit_list.setHeaderLabels(["", "Event", "Action", "Boxes", "Status", "Source", "Runtime", "Recording", "Time"])
        self.audit_list.setColumnWidth(0, 28)
        show_approved = self.rb_approved.isChecked()
        roots = [Path("screenshots") / "event_unknown", Path("screenshots") / "event_review", Path("screenshots")]
        folders = []
        for root in roots:
            if not root.exists():
                continue
            folders.extend(
                p for p in root.iterdir()
                if p.is_dir() and p.name.startswith("physical_") and (p / "index.json").exists()
            )
        seen = set()
        unique = []
        for folder in folders:
            key = str(folder.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique.append(folder)
        unique.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for folder in unique:
            try:
                data = json.loads((folder / "index.json").read_text(encoding="utf-8"))
            except Exception:
                data = {}
            status = data.get("status", "")
            if show_approved and status != "review_approved":
                continue
            if not show_approved and status not in ("review_pending", "needs_model_or_manual", "raw_captured", "processing"):
                continue
            yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
            objects = yolo.get("objects") or []
            if not objects and yolo.get("bbox_xyxy"):
                objects = [yolo]
            item = QTreeWidgetItem()
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setText(1, folder.name)
            item.setText(2, str(data.get("action_type", "")))
            item.setText(3, str(len(objects)))
            item.setText(4, str(status or "unknown"))
            item.setText(5, str(data.get("gpt_yolo_objects", {}).get("model") or yolo.get("status") or ""))
            runtime_index = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
            if runtime_index:
                runtime_text = f"E{runtime_index.get('elements', 0)} R{runtime_index.get('rules', 0)}"
            else:
                click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
                runtime_text = "rule hit" if click_target.get("status") == "runtime_rule_matched" else ""
            recording = data.get("recording", {}) if isinstance(data.get("recording"), dict) else {}
            recording_text = ""
            if recording.get("video_offset_ms") is not None:
                recording_text = f"{recording.get('kind', '')} @{self._format_seconds(recording.get('video_offset_ms'))}"
            item.setText(6, runtime_text)
            item.setText(7, recording_text)
            item.setText(8, str(data.get("time", "")))
            item.setData(0, 257, str(folder))
            item.setData(0, 258, "yolo_event")
            item.setData(1, 257, str(folder))
            item.setData(1, 258, "yolo_event")
            self.audit_list.addTopLevelItem(item)

