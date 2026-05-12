from __future__ import annotations

import sqlite3

from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt

from log_manager import LogManager
from ui.dialogs.rule_edit import RuleEditDialog




from PySide6.QtWidgets import QTableWidgetItem
class RulesRefreshPanelMixin:
    def _refresh_rule_list(self):
        if not getattr(self, "rule_table", None):
            return
        self.rule_table.setRowCount(0)
        try:
            from agent_data import AgentDataManager
            dm = AgentDataManager()
            search = self.rule_search_edit.text().strip() if getattr(self, "rule_search_edit", None) else ""
            if self.rb_rule_enabled.isChecked():
                filter_enabled = True
            elif self.rb_rule_disabled.isChecked():
                filter_enabled = False
            else:
                filter_enabled = None
            rules = dm.list_all_runtime_rules(search=search, filter_enabled=filter_enabled)
            stats = dm.get_runtime_rule_stats()
            self.rule_stats_label.setText(
                f"总计 {stats['total']} | 已启用 {stats['enabled']} | "
                f"已禁用 {stats['disabled']} | 总命中 {stats['total_hits']}"
            )
            self.rule_table.setRowCount(len(rules))
            for row, rule in enumerate(rules):
                self.rule_table.setItem(row, 0, QTableWidgetItem(str(rule["id"])))
                self.rule_table.setItem(row, 1, QTableWidgetItem(rule["scene_key"] or ""))
                self.rule_table.setItem(row, 2, QTableWidgetItem(rule["element_name"] or ""))
                self.rule_table.setItem(row, 3, QTableWidgetItem(rule["action_type"] or ""))
                self.rule_table.setItem(row, 4, QTableWidgetItem(rule["action_effect"] or ""))
                conf_item = QTableWidgetItem(f"{rule['confidence']:.2f}" if rule.get('confidence') else "-")
                self.rule_table.setItem(row, 5, conf_item)
                self.rule_table.setItem(row, 6, QTableWidgetItem(str(rule.get("hits", 0))))
                enabled_item = QTableWidgetItem("是" if rule.get("enabled") else "否")
                if not rule.get("enabled"):
                    enabled_item.setForeground(QBrush(QColor("#f44747")))
                self.rule_table.setItem(row, 7, enabled_item)
                self.rule_table.setItem(row, 8, QTableWidgetItem(rule["source"] or ""))
                # 存储 rule_id
                for col in range(9):
                    item = self.rule_table.item(row, col)
                    if item:
                        item.setData(256, rule["id"])
                # 禁用行整体变灰
                if not rule.get("enabled"):
                    for col in range(9):
                        item = self.rule_table.item(row, col)
                        if item:
                            item.setForeground(QBrush(QColor("#888888")))
        except Exception as e:
            LogManager().append(f"[RulePanel] 刷新规则列表失败: {e}")
            self.rule_stats_label.setText(f"加载失败: {e}")

