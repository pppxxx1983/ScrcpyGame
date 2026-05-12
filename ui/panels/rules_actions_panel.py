from __future__ import annotations

import sqlite3

from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt

from log_manager import LogManager
from ui.dialogs.rule_edit import RuleEditDialog




from PySide6.QtWidgets import QDialog, QMenu, QMessageBox, QTableWidgetItem
class RulesActionsPanelMixin:
    def _show_rule_context_menu(self, position):
        item = self.rule_table.itemAt(position)
        if not item:
            return
        rule_id = item.data(256)
        if not rule_id:
            return
        menu = QMenu(self)
        action_edit = menu.addAction("编辑")
        action_toggle = menu.addAction("启用/禁用")
        action_delete = menu.addAction("删除")
        action = menu.exec(self.rule_table.viewport().mapToGlobal(position))
        if action == action_edit:
            self._open_rule_edit_dialog_by_id(rule_id)
        elif action == action_toggle:
            self._toggle_rule_enabled(rule_id)
        elif action == action_delete:
            self._delete_rule(rule_id)

    def _toggle_rule_enabled(self, rule_id: int):
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            rule = dm.get_runtime_rule(rule_id)
            if rule is None:
                return
            dm.toggle_runtime_rule_enabled(rule_id, not rule.get("enabled", True))
            self._refresh_rule_list()
        except Exception as e:
            LogManager().append(f"[RulePanel] 切换启用状态失败: {e}")

    def _delete_rule(self, rule_id: int):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除规则 #{rule_id} 吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            if dm.delete_runtime_rule(rule_id):
                self._refresh_rule_list()
        except Exception as e:
            LogManager().append(f"[RulePanel] 删除规则失败: {e}")

    def _open_rule_edit_dialog(self, item: QTableWidgetItem):
        rule_id = item.data(256)
        if rule_id:
            self._open_rule_edit_dialog_by_id(rule_id)

    def _open_rule_edit_dialog_by_id(self, rule_id: int):
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            rule = dm.get_runtime_rule(rule_id)
            if rule is None:
                return
            dialog = RuleEditDialog(rule, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                data = dialog.get_data()
                dm.update_runtime_rule(
                    rule_id=rule_id,
                    element_name=data.get("element_name"),
                    action_type=data.get("action_type"),
                    action_effect=data.get("action_effect"),
                    user_intent=data.get("user_intent"),
                    bbox_xyxy=data.get("bbox_xyxy"),
                    next_scene_key=data.get("next_scene_key"),
                    confidence=data.get("confidence"),
                    enabled=data.get("enabled"),
                )
                self._refresh_rule_list()
        except Exception as e:
            LogManager().append(f"[RulePanel] 打开编辑对话框失败: {e}")

    def _open_rule_create_dialog(self):
        # 新建规则：使用空数据，rule_id=None
        dummy_rule = {
            "id": None,
            "rule_key": "",
            "scene_key": "",
            "element_name": "",
            "action_type": "tap",
            "action_effect": "",
            "user_intent": "",
            "bbox_xyxy": [0, 0, 100, 100],
            "next_scene_key": "",
            "confidence": 0.9,
            "enabled": True,
            "source": "manual",
        }
        dialog = RuleEditDialog(dummy_rule, self, is_create=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                from agent_data import AgentDataManager
                dm = AgentDataManager()
                # 生成 rule_key
                rule_key = data.get("rule_key") or "|".join([
                    data.get("scene_key", ""),
                    data.get("action_type", "tap"),
                    data.get("element_name", ""),
                    data.get("next_scene_key", ""),
                ])
                dm.upsert_runtime_rule(
                    rule_key=rule_key,
                    scene_id=None,
                    scene_key=data.get("scene_key", ""),
                    element_id=None,
                    element_name=data.get("element_name", ""),
                    action_type=data.get("action_type", "tap"),
                    action_effect=data.get("action_effect", ""),
                    user_intent=data.get("user_intent", ""),
                    bbox_xyxy=data.get("bbox_xyxy", [0, 0, 100, 100]),
                    next_scene_id=None,
                    next_scene_key=data.get("next_scene_key", ""),
                    source_event="manual_create",
                    source="manual",
                    confidence=data.get("confidence", 0.9),
                )
                # 更新 enabled 状态
                conn = sqlite3.connect(str(dm.db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE runtime_rule SET enabled = ? WHERE rule_key = ?",
                    (1 if data.get("enabled", True) else 0, rule_key),
                )
                conn.commit()
                conn.close()
                self._refresh_rule_list()
            except Exception as e:
                LogManager().append(f"[RulePanel] 创建规则失败: {e}")

