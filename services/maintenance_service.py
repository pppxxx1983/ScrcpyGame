from __future__ import annotations

import shutil
import time
from pathlib import Path


from log_manager import LogManager
from scene_index import UnknownFolderProcessor


from PySide6.QtWidgets import QMessageBox
class MaintenanceServiceMixin:
    def _clear_database(self):
        """清理数据库、game_agent_data、screenshots 的所有内容。"""
        reply = QMessageBox.question(
            self, "确认清库",
            "确定要清库吗？\n\n这将删除所有截图、事件记录和场景数据，不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # 先停止 unknown 处理器，释放数据库和文件句柄
            self._unknown_processor.stop()
            import time
            time.sleep(0.5)

            # 1. 清理 screenshots
            screenshot_dir = Path("screenshots")
            if screenshot_dir.exists():
                for item in screenshot_dir.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        import shutil
                        shutil.rmtree(item)

            # 2. 清理 game_agent_data
            game_data_dir = Path("game_agent_data")
            if game_data_dir.exists():
                import shutil
                shutil.rmtree(game_data_dir)

            # 3. 重置 AgentDataManager 单例，让 ExecutionEngine 重新初始化数据库
            from agent_data import AgentDataManager
            AgentDataManager._instance = None
            self.execution_engine.dm = AgentDataManager()

            # 4. 重新创建 UnknownFolderProcessor（确保 SceneIndex 也是新的）
            self._unknown_processor = UnknownFolderProcessor(interval=5, allow_cloud_fallback=True)
            self._unknown_processor.start()

            # 5. 刷新 UI
            self._refresh_events()
            self._refresh_audit_list()

            self._set_status("状态: 清库完成")
            LogManager().append("[ClearDB] 数据库已清空")
        except Exception as e:
            LogManager().append(f"[ClearDB] 清库失败: {e}")
            self._set_status(f"状态: 清库失败 - {e}")

