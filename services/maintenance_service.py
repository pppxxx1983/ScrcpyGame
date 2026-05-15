from __future__ import annotations

import os
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
            self._unknown_processor.stop()
            time.sleep(1.0)

            import gc
            gc.collect()

            self._close_all_db_connections()

            screenshots_dir = Path("screenshots")
            if screenshots_dir.exists():
                for item in list(screenshots_dir.iterdir()):
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                    except PermissionError:
                        pass

            game_data_dir = Path("game_agent_data")
            if game_data_dir.exists():
                for retry in range(3):
                    try:
                        shutil.rmtree(game_data_dir, ignore_errors=True)
                        break
                    except (OSError, PermissionError):
                        time.sleep(0.5)
                        gc.collect()

            for db_file in Path(".").glob("**/*.sqlite"):
                try:
                    os.chmod(db_file, 0o666)
                    db_file.unlink(missing_ok=True)
                except (OSError, PermissionError):
                    pass

            for wal_file in Path(".").glob("**/*.sqlite-wal"):
                try:
                    wal_file.unlink(missing_ok=True)
                except OSError:
                    pass
            for shm_file in Path(".").glob("**/*.sqlite-shm"):
                try:
                    shm_file.unlink(missing_ok=True)
                except OSError:
                    pass

            from agent_data import AgentDataManager
            AgentDataManager._instance = None
            self.execution_engine.dm = AgentDataManager()

            self._unknown_processor = UnknownFolderProcessor(interval=5, allow_cloud_fallback=True)
            self._unknown_processor.start()

            self._refresh_events()
            self._refresh_audit_list()

            self._set_status("状态: 清库完成")
            LogManager().append("[ClearDB] 数据库已清空")
        except Exception as e:
            LogManager().append(f"[ClearDB] 清库失败: {e}")
            self._set_status(f"状态: 清库失败 - {e}")

    def _close_all_db_connections(self):
        """强制关闭所有可能的数据库连接。"""
        import sqlite3
        for db_file in Path(".").glob("**/*.sqlite"):
            try:
                conn = sqlite3.connect(str(db_file))
                conn.execute("PRAGMA optimize")
                conn.close()
            except Exception:
                pass

