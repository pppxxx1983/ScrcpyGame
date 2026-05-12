from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt

from log_manager import LogManager
from scene_index import SceneIndex






from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QRadioButton, QTreeWidget, QVBoxLayout, QWidget
class AuditSetupPanelMixin:
    def _setup_audit_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.audit_panel = QWidget(self.side_panel)
        self.audit_panel.setObjectName("auditPanel")
        panel_layout = QVBoxLayout(self.audit_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("场景审核")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)

        # 审核状态过滤 radio button（互斥单选）
        kind_row = QHBoxLayout()
        self.rb_audit_scene = QRadioButton("Scene")
        self.rb_audit_scene.setChecked(True)
        self.rb_audit_scene.setStyleSheet("color: #cccccc;")
        self.rb_audit_yolo = QRadioButton("YOLO")
        self.rb_audit_yolo.setStyleSheet("color: #cccccc;")
        self.rb_audit_kind_group = QButtonGroup(self)
        self.rb_audit_kind_group.setExclusive(True)
        self.rb_audit_kind_group.addButton(self.rb_audit_scene)
        self.rb_audit_kind_group.addButton(self.rb_audit_yolo)
        self.rb_audit_scene.toggled.connect(self._refresh_audit_list)
        self.rb_audit_yolo.toggled.connect(self._refresh_audit_list)
        kind_row.addWidget(self.rb_audit_scene)
        kind_row.addWidget(self.rb_audit_yolo)
        kind_row.addStretch(1)
        panel_layout.addLayout(kind_row)

        filter_row = QHBoxLayout()
        self.rb_audit_group = QButtonGroup(self)
        self.rb_audit_group.setExclusive(True)
        self.rb_unreviewed = QRadioButton("未审核")
        self.rb_unreviewed.setChecked(True)
        self.rb_unreviewed.setStyleSheet("color: #cccccc;")
        self.rb_unreviewed.toggled.connect(self._refresh_audit_list)
        self.rb_audit_group.addButton(self.rb_unreviewed)
        filter_row.addWidget(self.rb_unreviewed)
        self.rb_approved = QRadioButton("审核通过")
        self.rb_approved.setStyleSheet("color: #cccccc;")
        self.rb_approved.toggled.connect(self._refresh_audit_list)
        self.rb_audit_group.addButton(self.rb_approved)
        filter_row.addWidget(self.rb_approved)
        filter_row.addStretch(1)
        panel_layout.addLayout(filter_row)

        btn_refresh = QPushButton("刷新列表", self.audit_panel)
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._refresh_audit_list)

        btn_history = QPushButton("Reanalyze 历史", self.audit_panel)
        btn_history.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_history.clicked.connect(self._show_reanalyze_history)

        audit_btn_row = QHBoxLayout()
        audit_btn_row.addWidget(btn_refresh)
        audit_btn_row.addWidget(btn_history)
        panel_layout.addLayout(audit_btn_row)

        # 批量操作按钮行（YOLO 模式显示）
        self.batch_btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        self.btn_select_all.clicked.connect(self._audit_select_all)
        self.batch_btn_row.addWidget(self.btn_select_all)

        self.btn_batch_approve = QPushButton("批量批准")
        self.btn_batch_approve.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; border: 1px solid #555555; padding: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        self.btn_batch_approve.clicked.connect(self._batch_approve_selected)
        self.batch_btn_row.addWidget(self.btn_batch_approve)

        self.btn_batch_compile = QPushButton("批量编译")
        self.btn_batch_compile.setStyleSheet(
            "QPushButton { background-color: #6a9955; color: white; border: 1px solid #555555; padding: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #7ab868; }"
        )
        self.btn_batch_compile.clicked.connect(self._batch_compile_selected)
        self.batch_btn_row.addWidget(self.btn_batch_compile)
        self.batch_btn_row.addStretch(1)
        panel_layout.addLayout(self.batch_btn_row)

        self.audit_list = QTreeWidget(self.audit_panel)
        self.audit_list.setObjectName("auditList")
        self.audit_list.setHeaderLabels(["场景", "类型", "命中", "模型", "状态", "创建时间"])
        self.audit_list.setStyleSheet(
            "QTreeWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; padding: 4px; }"
            "QTreeWidget::item { padding: 4px; border-bottom: 1px solid #333333; }"
            "QTreeWidget::item:selected { background-color: #0e639c; color: white; }"
            "QTreeWidget::item:hover { background-color: #2a2d2e; }"
        )
        self.audit_list.itemClicked.connect(self._open_audit_item)
        self.audit_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.audit_list.customContextMenuRequested.connect(self._show_audit_context_menu)
        panel_layout.addWidget(self.audit_list, 1)

        layout.insertWidget(2, self.audit_panel)
        self.audit_panel.setVisible(False)

