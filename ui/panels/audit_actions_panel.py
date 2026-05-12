from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt

from log_manager import LogManager
from scene_index import SceneIndex






from PySide6.QtWidgets import QMenu, QMessageBox
class AuditActionsPanelMixin:
    def _show_audit_context_menu(self, position):
        """右键菜单：重新识别。"""
        item = self.audit_list.itemAt(position)
        if not item:
            return
        if item.data(0, 258) == "yolo_event":
            menu = QMenu(self)
            action_train = menu.addAction("Train YOLO")
            action = menu.exec(self.audit_list.viewport().mapToGlobal(position))
            if action == action_train:
                self._train_yolo_incremental()
            return
        menu = QMenu(self)
        action_ollama = menu.addAction("重新 Ollama 识别")
        action_qwen = menu.addAction("重新 qwen-vl-max 识别")
        action = menu.exec(self.audit_list.viewport().mapToGlobal(position))
        if action == action_ollama:
            self._reclassify_scene(item, "ollama")
        elif action == action_qwen:
            self._reclassify_scene(item, "qwen")

    def _audit_select_all(self):
        """审核列表全选/取消全选切换。"""
        if not getattr(self, "audit_list", None):
            return
        checked = 0
        for i in range(self.audit_list.topLevelItemCount()):
            if self.audit_list.topLevelItem(i).checkState(0) == Qt.CheckState.Checked:
                checked += 1
        new_state = Qt.CheckState.Unchecked if checked > 0 else Qt.CheckState.Checked
        for i in range(self.audit_list.topLevelItemCount()):
            self.audit_list.topLevelItem(i).setCheckState(0, new_state)

    def _get_checked_audit_folders(self) -> list[Path]:
        """获取审核列表中勾选的 YOLO 事件文件夹路径。"""
        folders = []
        for i in range(self.audit_list.topLevelItemCount()):
            item = self.audit_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked and item.data(1, 258) == "yolo_event":
                path = item.data(1, 257)
                if path:
                    folders.append(Path(path))
        return folders

    def _batch_approve_selected(self):
        """批量批准勾选的 YOLO 事件。"""
        folders = self._get_checked_audit_folders()
        if not folders:
            QMessageBox.information(self, "批量批准", "请先勾选要批准的事件")
            return
        reply = QMessageBox.question(
            self, "确认批量批准",
            f"确定要批量批准 {len(folders)} 个事件吗？\n"
            "没有 approved 框的事件会自动标记所有框为 approved。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        success = 0
        failed = 0
        for folder in folders:
            try:
                index_path = folder / "index.json"
                if not index_path.exists():
                    failed += 1
                    continue
                data = json.loads(index_path.read_text(encoding="utf-8"))
                yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
                objects = yolo.get("objects") or []
                if not objects and yolo.get("bbox_xyxy"):
                    objects = [dict(yolo)]
                # 如果没有 approved 框，自动标记所有框
                has_approved = any(obj.get("review_approved") or obj.get("review_status") == "approved" for obj in objects)
                if not has_approved:
                    for obj in objects:
                        obj["review_approved"] = True
                image_name = data.get("images", {}).get("before") or "before.png"
                image_path = folder / image_name
                if not image_path.exists():
                    failed += 1
                    continue
                self._save_yolo_review(folder, data, image_path, objects, approved=True)
                success += 1
            except Exception as e:
                LogManager().append(f"[BatchApprove] {folder.name} 失败: {e}")
                failed += 1
        QMessageBox.information(self, "批量批准完成", f"成功 {success} | 失败 {failed}")
        self._refresh_audit_list()

    def _batch_compile_selected(self):
        """批量编译勾选的已批准事件的 runtime_index。"""
        folders = self._get_checked_audit_folders()
        if not folders:
            QMessageBox.information(self, "批量编译", "请先勾选要编译的事件")
            return
        success = 0
        failed = 0
        skipped = 0
        for folder in folders:
            try:
                index_path = folder / "index.json"
                if not index_path.exists():
                    failed += 1
                    continue
                data = json.loads(index_path.read_text(encoding="utf-8"))
                if data.get("status") != "review_approved":
                    skipped += 1
                    continue
                yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
                approved_objects = [dict(obj) for obj in (yolo.get("approved_objects") or [])]
                if not approved_objects:
                    approved_objects = [dict(obj) for obj in (yolo.get("objects") or []) if obj.get("review_approved") or obj.get("review_status") == "approved"]
                if not approved_objects:
                    skipped += 1
                    continue
                image_name = data.get("images", {}).get("before") or "before.png"
                image_path = folder / image_name
                if not image_path.exists():
                    failed += 1
                    continue
                result = self._compile_runtime_index_from_review(
                    folder=folder,
                    data=data,
                    image_path=image_path,
                    approved_objects=approved_objects,
                    source="batch_compile",
                )
                data["runtime_index"] = result
                index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                success += 1
            except Exception as e:
                LogManager().append(f"[BatchCompile] {folder.name} 失败: {e}")
                failed += 1
        QMessageBox.information(self, "批量编译完成", f"成功 {success} | 失败 {failed} | 跳过 {skipped}")
        self._refresh_audit_list()

