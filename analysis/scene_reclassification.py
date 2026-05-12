from __future__ import annotations

import threading
from pathlib import Path
from datetime import datetime


from log_manager import LogManager
from scene_index import SceneIndex




from PySide6.QtWidgets import QTreeWidgetItem
class SceneReclassificationMixin:
    def _reclassify_scene(self, item: QTreeWidgetItem, engine: str):
        """用指定引擎重新识别场景，更新数据库。在后台线程执行。"""
        row_id = item.data(0, 256)
        image_path_str = item.data(0, 257)
        old_name = item.text(0)
        if not image_path_str:
            self._set_status("审核: 该场景没有图片路径")
            return
        image_path = Path(image_path_str)
        if not image_path.exists():
            self._set_status(f"审核: 图片不存在 {image_path}")
            return

        self._set_status(f"审核: 正在用 {engine} 重新识别 '{old_name}'...")

        def _run():
            try:
                from scene_index import SceneIndex, classify_image_with_ollama, classify_image_with_qwen
                from datetime import datetime

                if engine == "ollama":
                    result = classify_image_with_ollama(image_path)
                    if not result:
                        # Ollama 未运行/不可用，自动 fallback 到 qwen-vl-max
                        result = classify_image_with_qwen(image_path)
                else:
                    result = classify_image_with_qwen(image_path)

                if not result or not result.get("name") or result.get("name") == "未知":
                    self._set_status(f"审核: {engine} 重新识别失败，结果无效")
                    return

                new_name = result["name"]
                desc = result.get("desc", "")
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                si = SceneIndex()
                with si._connect() as conn:
                    conn.execute(
                        "UPDATE scenes SET scene_key = ?, description = ?, model_name = ?, updated_at = ? WHERE id = ?",
                        (new_name, desc, engine, now, row_id),
                    )

                self._set_status(f"审核: '{old_name}' → '{new_name}' ({engine})")
                self._refresh_audit_list()
            except Exception as e:
                import traceback
                LogManager().append(f"[Audit] 重新识别失败:\n{traceback.format_exc()}")
                self._set_status(f"审核: 重新识别失败 - {e}")

        threading.Thread(target=_run, daemon=True).start()

