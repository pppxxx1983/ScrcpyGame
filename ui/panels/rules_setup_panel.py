from __future__ import annotations

import sqlite3

from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt

from log_manager import LogManager
from ui.dialogs.rule_edit import RuleEditDialog




from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QTableWidget, QVBoxLayout, QWidget
class RulesSetupPanelMixin:
    def _setup_rule_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.rule_panel = QWidget(self.side_panel)
        self.rule_panel.setObjectName("rulePanel")
        panel_layout = QVBoxLayout(self.rule_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("规则管理")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        # 统计栏
        self.rule_stats_label = QLabel("规则统计: loading")
        self.rule_stats_label.setWordWrap(True)
        self.rule_stats_label.setStyleSheet(
            "background-color: #111111; color: #9cdcfe; border: 1px solid #333333; padding: 6px; font-weight: bold;"
        )
        panel_layout.addWidget(self.rule_stats_label)

        # 搜索框
        search_row = QHBoxLayout()
        self.rule_search_edit = QLineEdit()
        self.rule_search_edit.setPlaceholderText("搜索规则...")
        self.rule_search_edit.setStyleSheet(
            "QLineEdit { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
        )
        self.rule_search_edit.returnPressed.connect(self._refresh_rule_list)
        search_row.addWidget(self.rule_search_edit)

        btn_search = QPushButton("搜索")
        btn_search.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_search.clicked.connect(self._refresh_rule_list)
        search_row.addWidget(btn_search)
        panel_layout.addLayout(search_row)

        # 过滤 radio
        filter_row = QHBoxLayout()
        self.rb_rule_all = QRadioButton("全部")
        self.rb_rule_all.setChecked(True)
        self.rb_rule_all.setStyleSheet("color: #cccccc;")
        self.rb_rule_enabled = QRadioButton("已启用")
        self.rb_rule_enabled.setStyleSheet("color: #cccccc;")
        self.rb_rule_disabled = QRadioButton("已禁用")
        self.rb_rule_disabled.setStyleSheet("color: #cccccc;")
        self.rb_rule_group = QButtonGroup(self)
        self.rb_rule_group.setExclusive(True)
        self.rb_rule_group.addButton(self.rb_rule_all)
        self.rb_rule_group.addButton(self.rb_rule_enabled)
        self.rb_rule_group.addButton(self.rb_rule_disabled)
        for rb in [self.rb_rule_all, self.rb_rule_enabled, self.rb_rule_disabled]:
            rb.toggled.connect(self._refresh_rule_list)
            filter_row.addWidget(rb)
        filter_row.addStretch(1)
        panel_layout.addLayout(filter_row)

        # 规则表格
        self.rule_table = QTableWidget(self.rule_panel)
        self.rule_table.setColumnCount(9)
        self.rule_table.setHorizontalHeaderLabels(
            ["ID", "场景", "元素", "动作", "作用", "置信度", "命中", "启用", "来源"]
        )
        self.rule_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; gridline-color: #444444; }"
            "QHeaderView::section { background-color: #333333; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rule_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.rule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rule_table.setColumnWidth(0, 40)
        self.rule_table.setColumnWidth(1, 90)
        self.rule_table.setColumnWidth(2, 90)
        self.rule_table.setColumnWidth(3, 60)
        self.rule_table.setColumnWidth(4, 80)
        self.rule_table.setColumnWidth(5, 50)
        self.rule_table.setColumnWidth(6, 40)
        self.rule_table.setColumnWidth(7, 40)
        self.rule_table.horizontalHeader().setStretchLastSection(True)
        self.rule_table.itemDoubleClicked.connect(self._open_rule_edit_dialog)
        self.rule_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rule_table.customContextMenuRequested.connect(self._show_rule_context_menu)
        panel_layout.addWidget(self.rule_table, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._refresh_rule_list)
        btn_row.addWidget(btn_refresh)

        btn_add = QPushButton("新建")
        btn_add.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_add.clicked.connect(self._open_rule_create_dialog)
        btn_row.addWidget(btn_add)
        btn_row.addStretch(1)
        panel_layout.addLayout(btn_row)

        layout.insertWidget(4, self.rule_panel)
        self.rule_panel.setVisible(False)

