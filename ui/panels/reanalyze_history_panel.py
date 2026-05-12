from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QBrush

from reanalyze_logger import get_logger




from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout
class ReanalyzeHistoryPanelMixin:
    def _show_reanalyze_history(self):
        """打开 Reanalyze 历史记录对话框。"""
        from reanalyze_logger import get_logger

        logger = get_logger()
        records = logger.read_all(limit=200)
        stats = logger.get_stats()

        dialog = QDialog(self)
        dialog.setWindowTitle("GPT-5.5 Reanalyze 历史记录")
        dialog.resize(960, 720)
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(12, 12, 12, 12)
        dialog_layout.setSpacing(8)

        # 统计信息
        stats_label = QLabel(
            f"总计调用: {stats['total_calls']} | 成功: {stats['success']} | 失败: {stats['failed']} | "
            f"总对象数: {stats['total_objects']} | 平均耗时: {stats['avg_duration_ms']:.0f}ms"
        )
        stats_label.setStyleSheet("color: #9cdcfe; font-size: 12px; padding: 4px;")
        dialog_layout.addWidget(stats_label)

        # 历史记录列表
        history_table = QTableWidget(dialog)
        history_table.setColumnCount(8)
        history_table.setHorizontalHeaderLabels(
            ["时间", "场景", "模型", "对象数", "修改数", "耗时(ms)", "状态", "图片路径"]
        )
        history_table.setColumnWidth(0, 150)
        history_table.setColumnWidth(1, 100)
        history_table.setColumnWidth(2, 120)
        history_table.setColumnWidth(3, 55)
        history_table.setColumnWidth(4, 55)
        history_table.setColumnWidth(5, 70)
        history_table.setColumnWidth(6, 55)
        history_table.setColumnWidth(7, 240)
        history_table.setStyleSheet(
            "QTableWidget { background-color: #252526; color: #cccccc; "
            "border: 1px solid #3c3c3c; }"
            "QHeaderView::section { background-color: #3c3c3c; color: #cccccc; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0e639c; }"
        )
        history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        history_table.horizontalHeader().setStretchLastSection(True)
        history_table.setRowCount(len(records))

        for row, rec in enumerate(records):
            ts = rec.get("timestamp", "")
            folder = rec.get("folder", "")
            model = rec.get("model", "")
            obj_count = rec.get("object_count", 0)
            duration = rec.get("duration_ms", 0)
            success = rec.get("success", False)
            img_path = rec.get("image_path", "")

            mod_count = rec.get("modified_count", 0)
            history_table.setItem(row, 0, QTableWidgetItem(ts))
            history_table.setItem(row, 1, QTableWidgetItem(Path(folder).name))
            history_table.setItem(row, 2, QTableWidgetItem(model))
            history_table.setItem(row, 3, QTableWidgetItem(str(obj_count)))
            mod_item = QTableWidgetItem(str(mod_count))
            if mod_count > 0:
                mod_item.setForeground(QBrush(QColor("#ffcc00")))
            history_table.setItem(row, 4, mod_item)
            history_table.setItem(row, 5, QTableWidgetItem(f"{duration:.0f}"))
            status_item = QTableWidgetItem("成功" if success else "失败")
            status_item.setForeground(QBrush(QColor("#6a9955" if success else "#f44747")))
            history_table.setItem(row, 6, status_item)
            history_table.setItem(row, 7, QTableWidgetItem(img_path))

        dialog_layout.addWidget(history_table, 1)

        # 详情区域
        detail_label = QLabel("选中记录详情：")
        detail_label.setStyleSheet("color: #cccccc; font-weight: bold; padding-top: 8px;")
        dialog_layout.addWidget(detail_label)

        detail_text = QTextEdit(dialog)
        detail_text.setReadOnly(True)
        detail_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; padding: 6px; font-family: Consolas, monospace; font-size: 12px; }"
        )
        detail_text.setMaximumHeight(280)
        dialog_layout.addWidget(detail_text)

        def on_selection_changed():
            rows = history_table.selectionModel().selectedRows()
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(records):
                rec = records[row]
                lines = [
                    f"时间: {rec.get('timestamp', '')}",
                    f"图片: {rec.get('image_path', '')}",
                    f"场景: {rec.get('folder', '')}",
                    f"模型: {rec.get('model', '')}",
                    f"成功: {rec.get('success', False)}",
                    f"对象数: {rec.get('object_count', 0)}",
                    f"修改数: {rec.get('modified_count', 0)}",
                    f"耗时: {rec.get('duration_ms', 0):.2f}ms",
                    "",
                    "--- Objects ---",
                ]
                for oi, obj in enumerate(rec.get("objects", [])):
                    mod_flag = "[改]" if obj.get("modified") else "[原]"
                    lines.append(
                        f"{oi+1}. {mod_flag} {obj.get('class_name','')} | "
                        f"role={obj.get('role','')} | "
                        f"bbox={obj.get('bbox_xyxy','')} | "
                        f"src={obj.get('source','')}"
                    )
                lines.extend([
                    "",
                    "--- Prompt ---",
                    rec.get("prompt", "")[:2000],
                    "",
                    "--- Raw Response ---",
                    rec.get("raw_response", "")[:3000],
                ])
                if rec.get("error"):
                    lines.extend(["", "--- Error ---", rec["error"]])
                detail_text.setPlainText("\n".join(lines))

        history_table.itemSelectionChanged.connect(on_selection_changed)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_open_image = QPushButton("打开图片", dialog)
        btn_open_image.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )

        def _open_selected_image():
            rows = history_table.selectionModel().selectedRows()
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(records):
                img_path = records[row].get("image_path", "")
                if img_path and Path(img_path).exists():
                    import os
                    os.startfile(img_path)

        btn_open_image.clicked.connect(_open_selected_image)
        btn_row.addWidget(btn_open_image)

        btn_open_folder = QPushButton("打开文件夹", dialog)
        btn_open_folder.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )

        def _open_selected_folder():
            rows = history_table.selectionModel().selectedRows()
            if not rows:
                return
            row = rows[0].row()
            if 0 <= row < len(records):
                folder = records[row].get("folder", "")
                if folder and Path(folder).exists():
                    import os
                    os.startfile(folder)

        btn_open_folder.clicked.connect(_open_selected_folder)
        btn_row.addWidget(btn_open_folder)

        btn_refresh = QPushButton("刷新", dialog)
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )

        def _refresh_history():
            nonlocal records, stats
            records = logger.read_all(limit=200)
            stats = logger.get_stats()
            stats_label.setText(
                f"总计调用: {stats['total_calls']} | 成功: {stats['success']} | 失败: {stats['failed']} | "
                f"总对象数: {stats['total_objects']} | 平均耗时: {stats['avg_duration_ms']:.0f}ms"
            )
            history_table.setRowCount(len(records))
            for row, rec in enumerate(records):
                ts = rec.get("timestamp", "")
                folder = rec.get("folder", "")
                model = rec.get("model", "")
                obj_count = rec.get("object_count", 0)
                duration = rec.get("duration_ms", 0)
                success = rec.get("success", False)
                img_path = rec.get("image_path", "")
                mod_count = rec.get("modified_count", 0)

                history_table.setItem(row, 0, QTableWidgetItem(ts))
                history_table.setItem(row, 1, QTableWidgetItem(Path(folder).name))
                history_table.setItem(row, 2, QTableWidgetItem(model))
                history_table.setItem(row, 3, QTableWidgetItem(str(obj_count)))
                mod_item = QTableWidgetItem(str(mod_count))
                if mod_count > 0:
                    mod_item.setForeground(QBrush(QColor("#ffcc00")))
                history_table.setItem(row, 4, mod_item)
                history_table.setItem(row, 5, QTableWidgetItem(f"{duration:.0f}"))
                status_item = QTableWidgetItem("成功" if success else "失败")
                status_item.setForeground(QBrush(QColor("#6a9955" if success else "#f44747")))
                history_table.setItem(row, 6, status_item)
                history_table.setItem(row, 7, QTableWidgetItem(img_path))
            detail_text.clear()

        btn_refresh.clicked.connect(_refresh_history)
        btn_row.addWidget(btn_refresh)

        btn_close = QPushButton("关闭", dialog)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_close.clicked.connect(dialog.close)
        btn_row.addWidget(btn_close)
        btn_row.addStretch(1)

        dialog_layout.addLayout(btn_row)
        dialog.exec()

