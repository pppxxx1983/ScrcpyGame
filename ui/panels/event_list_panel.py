from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime


from log_manager import LogManager




from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget
class EventListPanelMixin:
    def _setup_file_panel(self):
        if not self.side_panel:
            return
        layout = self.side_panel.layout()
        if layout is None:
            return

        self.file_panel = QWidget(self.side_panel)
        self.file_panel.setObjectName("filePanel")
        panel_layout = QVBoxLayout(self.file_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("事件队列")
        title.setStyleSheet("font-weight: bold; color: #cccccc; padding: 2px;")
        panel_layout.addWidget(title)


        refresh_btn = QPushButton("刷新事件")
        refresh_btn.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        refresh_btn.clicked.connect(self._refresh_events)
        panel_layout.addWidget(refresh_btn)

        # 搜索框
        search_row = QHBoxLayout()
        self.edit_event_search = QLineEdit()
        self.edit_event_search.setPlaceholderText("搜索事件...")
        self.edit_event_search.setStyleSheet(
            "QLineEdit { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 4px; }"
        )
        self.edit_event_search.textChanged.connect(self._on_event_search_changed)
        search_row.addWidget(self.edit_event_search)
        btn_clear_search = QPushButton("×")
        btn_clear_search.setFixedWidth(28)
        btn_clear_search.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 2px; }"
            "QPushButton:hover { background-color: #f44747; color: white; }"
        )
        btn_clear_search.clicked.connect(lambda: self.edit_event_search.clear())
        search_row.addWidget(btn_clear_search)
        panel_layout.addLayout(search_row)

        self.event_stats_label = QLabel("事件统计: waiting")
        self.event_stats_label.setWordWrap(True)
        self.event_stats_label.setStyleSheet("background-color: #111111; color: #dcdcaa; border: 1px solid #333333; padding: 6px; font-weight: bold;")
        panel_layout.addWidget(self.event_stats_label)

        self.list_events = QListWidget(self.file_panel)
        self.list_events.setObjectName("listEvents")
        self.list_events.setStyleSheet(
            "QListWidget { background-color: #3c3c3c; color: #cccccc; "
            "border: 1px solid #555555; padding: 4px; }"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background-color: #0e639c; color: white; }"
            "QListWidget::item:hover { background-color: #2a2d2e; }"
        )
        self.list_events.itemDoubleClicked.connect(self._open_event_tab)
        panel_layout.addWidget(self.list_events)

        layout.insertWidget(1, self.file_panel)
        self.file_panel.setVisible(False)
        self._refresh_events()

    def _refresh_events(self):
        if self.list_events is None:
            return
        self.list_events.clear()
        added = 0
        stats = {"total": 0, "pending": 0, "processing": 0, "approved": 0, "rule_hits": 0, "runtime_indexed": 0, "recorded": 0, "boxes": 0}
        try:
            root = Path("screenshots")
            if root.exists():
                physical_folders = []
                event_roots = [root, root / "event_unknown", root / "event_review"]
                for event_root in event_roots:
                    if not event_root.exists():
                        continue
                    physical_folders.extend(
                        p for p in event_root.iterdir()
                        if p.is_dir() and p.name.startswith("physical_") and (p / "index.json").exists()
                    )
                physical_folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for folder in physical_folders:
                    try:
                        data = json.loads((folder / "index.json").read_text(encoding="utf-8"))
                    except Exception:
                        data = {}
                    stats["total"] += 1
                    action_type = data.get("action_type", "physical")
                    status = data.get("status", folder.parent.name if folder.parent != root else "")
                    if status in ("raw_captured", "needs_model_or_manual", "review_pending", "event_unknown"):
                        stats["pending"] += 1
                    elif status == "processing":
                        stats["processing"] += 1
                    elif status == "review_approved":
                        stats["approved"] += 1
                    status_text = {
                        "raw_captured": "待处理",
                        "processing": "处理中",
                        "review_pending": "已处理",
                        "review_approved": "已审核",
                        "needs_model_or_manual": "待人工",
                        "event_unknown": "待处理",
                        "event_review": "已处理",
                    }.get(status, status or "未知")
                    yolo_state = data.get("yolo", {}).get("status")
                    obj_count = len(data.get("yolo", {}).get("objects") or [])
                    stats["boxes"] += obj_count
                    if obj_count:
                        mark = f"{obj_count}框"
                    elif data.get("yolo", {}).get("bbox_xyxy"):
                        mark = "1框"
                    elif yolo_state == "waiting_for_label":
                        mark = "无框"
                    else:
                        mark = "-"
                    touch = data.get("touch", {})
                    start = touch.get("start", {})
                    item = QListWidgetItem(
                        f"{action_type} [{status_text}/{mark}]  ({start.get('x', '-')},{start.get('y', '-')})  {folder.name}"
                    )
                    badges = []
                    if data.get("click_target", {}).get("status") == "runtime_rule_matched":
                        stats["rule_hits"] += 1
                    runtime_stats = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
                    if runtime_stats.get("elements", 0) or runtime_stats.get("rules", 0):
                        stats["runtime_indexed"] += 1
                    if isinstance(data.get("recording"), dict) and data["recording"].get("video_offset_ms") is not None:
                        stats["recorded"] += 1
                    click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
                    if click_target.get("status") == "runtime_rule_matched":
                        badges.append(f"规则:{click_target.get('element_name', '') or 'hit'}")
                    runtime_index = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
                    if runtime_index:
                        badges.append(f"索引:E{runtime_index.get('elements', 0)}/R{runtime_index.get('rules', 0)}")
                    recording = data.get("recording", {}) if isinstance(data.get("recording"), dict) else {}
                    if recording.get("video_offset_ms") is not None:
                        badges.append(f"录像@{self._format_seconds(recording.get('video_offset_ms'))}")
                    if badges:
                        item.setText(item.text() + "  |  " + "  ".join(badges))
                    item.setData(256, {"type": "physical_folder", "folder": str(folder)})
                    self.list_events.addItem(item)
                    added += 1

            db_path = Path("game_agent_data") / "games" / "my_game" / "agent.db"
            if not db_path.exists():
                self._update_event_stats_label(stats)
                if added:
                    return
                self.list_events.addItem("暂无事件数据")
                return
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, index_no, x, y, timestamp_ms,
                       before_image, after_300ms_image, after_800ms_image
                FROM click_event
                ORDER BY timestamp_ms DESC
                """
            )
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                self._update_event_stats_label(stats)
                if added:
                    return
                self.list_events.addItem("暂无事件记录")
                return

            for row in rows:
                row_id, session_id, idx, x, y, ts, before_img, after_300, after_800 = row
                from datetime import datetime
                dt = datetime.fromtimestamp(ts / 1000).strftime("%m-%d %H:%M:%S")
                text = f"{session_id} #{idx:03d}  ({x},{y})  {dt}"
                item = QListWidgetItem(text)
                item.setData(256, {
                    "id": row_id,
                    "session_id": session_id,
                    "index_no": idx,
                    "x": x,
                    "y": y,
                    "before_image": before_img,
                    "after_300ms_image": after_300,
                    "after_800ms_image": after_800,
                })
                self.list_events.addItem(item)
            self._update_event_stats_label(stats)
        except Exception as e:
            LogManager().append(f"[Event] 刷新事件列表失败: {e}")
            self.list_events.addItem(f"刷新失败: {e}")

    def _on_event_search_changed(self, text: str):
        text = text.strip().lower()
        for i in range(self.list_events.count()):
            item = self.list_events.item(i)
            if item:
                item.setHidden(bool(text) and text not in item.text().lower())

    def _update_event_stats_label(self, stats: dict):
        label = getattr(self, "event_stats_label", None)
        if not label:
            return
        text = (
            f"事件 {stats.get('total', 0)} | 待审核 {stats.get('pending', 0)} | "
            f"处理中 {stats.get('processing', 0)} | 已审核 {stats.get('approved', 0)}\n"
            f"规则命中 {stats.get('rule_hits', 0)} | 已编译 {stats.get('runtime_indexed', 0)} | "
            f"录像同步 {stats.get('recorded', 0)} | 框 {stats.get('boxes', 0)}"
        )
        label.setText(text)
        if stats.get("pending", 0) > 0:
            color = "#ffcc00"
        elif stats.get("rule_hits", 0) or stats.get("runtime_indexed", 0):
            color = "#4ec9b0"
        else:
            color = "#dcdcaa"
        label.setStyleSheet(
            f"background-color: #111111; color: {color}; border: 1px solid #333333; "
            "padding: 6px; font-weight: bold;"
        )

