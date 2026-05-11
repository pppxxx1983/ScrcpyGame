from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QSpinBox,
    QDialog,
    QDoubleSpinBox,
    QCheckBox,
)

class RuleEditDialog(QDialog):
    def __init__(self, rule: dict, parent=None, is_create: bool = False):
        super().__init__(parent)
        self.setWindowTitle("新建规则" if is_create else f"编辑规则 #{rule.get('id', '')}")
        self.resize(480, 520)
        self._rule = dict(rule)
        self._is_create = is_create
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        def add_row(label_text: str, widget):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("color: #cccccc;")
            row.addWidget(lbl)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        self.edit_scene_key = QLineEdit(self._rule.get("scene_key", ""))
        self.edit_scene_key.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        add_row("场景", self.edit_scene_key)

        self.edit_element_name = QLineEdit(self._rule.get("element_name", ""))
        self.edit_element_name.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        add_row("元素", self.edit_element_name)

        self.combo_action_type = QComboBox()
        self.combo_action_type.addItems(["tap", "swipe", "long_press", "scroll", "other"])
        self.combo_action_type.setCurrentText(self._rule.get("action_type", "tap"))
        self.combo_action_type.setStyleSheet("QComboBox { background-color: #3c3c3c; color: #cccccc; }")
        add_row("动作", self.combo_action_type)

        self.edit_action_effect = QLineEdit(self._rule.get("action_effect", ""))
        self.edit_action_effect.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        add_row("作用", self.edit_action_effect)

        self.edit_user_intent = QLineEdit(self._rule.get("user_intent", ""))
        self.edit_user_intent.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        add_row("意图", self.edit_user_intent)

        self.edit_next_scene_key = QLineEdit(self._rule.get("next_scene_key", ""))
        self.edit_next_scene_key.setStyleSheet("QLineEdit { background-color: #3c3c3c; color: #cccccc; }")
        add_row("目标场景", self.edit_next_scene_key)

        bbox = self._rule.get("bbox_xyxy") or [0, 0, 100, 100]
        bbox_layout = QHBoxLayout()
        bbox_lbl = QLabel("BBox")
        bbox_lbl.setFixedWidth(70)
        bbox_lbl.setStyleSheet("color: #cccccc;")
        bbox_layout.addWidget(bbox_lbl)
        self.spin_bbox = {}
        for i, name in enumerate(["x1", "y1", "x2", "y2"]):
            spin = QSpinBox()
            spin.setRange(0, 9999)
            spin.setValue(int(bbox[i]) if i < len(bbox) else 0)
            spin.setStyleSheet("QSpinBox { background-color: #3c3c3c; color: #cccccc; }")
            bbox_layout.addWidget(QLabel(name))
            bbox_layout.addWidget(spin)
            self.spin_bbox[name] = spin
        layout.addLayout(bbox_layout)

        self.spin_confidence = QDoubleSpinBox()
        self.spin_confidence.setRange(0.0, 1.0)
        self.spin_confidence.setDecimals(2)
        self.spin_confidence.setSingleStep(0.05)
        self.spin_confidence.setValue(float(self._rule.get("confidence", 0.9)))
        self.spin_confidence.setStyleSheet("QDoubleSpinBox { background-color: #3c3c3c; color: #cccccc; }")
        add_row("置信度", self.spin_confidence)

        self.chk_enabled = QCheckBox("启用")
        self.chk_enabled.setChecked(bool(self._rule.get("enabled", True)))
        self.chk_enabled.setStyleSheet("color: #cccccc;")
        layout.addWidget(self.chk_enabled)

        # 显示只读信息
        info = QLabel(
            f"ID: {self._rule.get('id', 'new')}  |  "
            f"来源: {self._rule.get('source', '')}  |  "
            f"命中: {self._rule.get('hits', 0)}  |  "
            f"事件: {self._rule.get('source_event', '')[:20]}"
        )
        info.setStyleSheet("color: #888888; font-size: 11px; padding-top: 8px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_ok.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)
        layout.addStretch(1)

    def get_data(self) -> dict:
        return {
            "rule_key": self._rule.get("rule_key", ""),
            "scene_key": self.edit_scene_key.text().strip(),
            "element_name": self.edit_element_name.text().strip(),
            "action_type": self.combo_action_type.currentText(),
            "action_effect": self.edit_action_effect.text().strip(),
            "user_intent": self.edit_user_intent.text().strip(),
            "next_scene_key": self.edit_next_scene_key.text().strip(),
            "bbox_xyxy": [
                self.spin_bbox["x1"].value(),
                self.spin_bbox["y1"].value(),
                self.spin_bbox["x2"].value(),
                self.spin_bbox["y2"].value(),
            ],
            "confidence": self.spin_confidence.value(),
            "enabled": self.chk_enabled.isChecked(),
        }

