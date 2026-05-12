from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from datetime import datetime


from log_manager import LogManager




class FrameCaptureMixin:
    def _flush_pending_frame(self):
        """主线程 QTimer：消费最新帧，做 BGR→RGB、显示、录制、FPS 统计。"""
        frame = self._pending_frame
        if frame is None:
            return
        self._pending_frame = None
        if self.video_widget is None:
            return

        import numpy as np
        rgb = np.ascontiguousarray(frame[..., ::-1])
        try:
            self.video_widget.set_frame(rgb)
        except RuntimeError:
            pass

        # 录制写入
        self.execution_engine.write_frame(frame, rgb)
        self._update_video_feedback_overlay()

        # FPS 统计
        now = time.time()
        if now - self._frame_flush_last_time >= 1.0:
            fps = self._frame_flush_count
            self._frame_flush_count = 0
            self._frame_flush_last_time = now
            fh, fw = frame.shape[:2]
            self._set_status(f"状态: 已连接 | FPS: {fps} | Frame: {fw}x{fh}", log=False)

    def _take_screenshot_sync(self, label: str, action_type: str = "", op_dir: Path = None) -> Path:
        """同步截取设备屏幕并保存到指定操作目录。调用者需确保在后台线程中执行"""
        if self._adb_device is None:
            return None
        try:
            import json
            from datetime import datetime
            now = datetime.now()
            ts = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]
            time_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            screenshot_dir = Path("screenshots")
            screenshot_dir.mkdir(exist_ok=True)

            if op_dir is None:
                op_dir = screenshot_dir / f"op_{ts}"
                op_dir.mkdir(exist_ok=True)

            local_path = op_dir / f"{label}.png"
            with self._screenshot_lock:
                img = self._adb_device.screenshot()
            if img:
                img.save(str(local_path))

            if label == "after":
                index_path = op_dir / "index.json"
                data = {
                    "time": time_str,
                    "action_type": action_type,
                    "before": "before.png",
                    "after": "after.png"
                }
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

            return op_dir
        except Exception:
            return None

    def _save_video_frame_sync(self, label: str, op_dir: Path) -> Path:
        """Save the latest scrcpy video frame as a PNG without waiting for adb screencap."""
        try:
            from PIL import Image

            frame = self.video_widget._frame if self.video_widget else None
            if frame is None:
                return None
            op_dir.mkdir(parents=True, exist_ok=True)
            local_path = op_dir / f"{label}.png"
            Image.fromarray(frame.copy()).save(str(local_path))
            return local_path
        except Exception as e:
            LogManager().append(f"[WARN] save frame failed: {e}")
            return None

    def _save_video_frame_async(self, label: str, op_dir: Path, frame=None) -> None:
        """Save a video frame in the background so input delivery is not blocked."""
        if frame is None:
            frame = self.video_widget._frame if self.video_widget else None
        if frame is None:
            return
        def _save():
            try:
                from PIL import Image

                op_dir.mkdir(parents=True, exist_ok=True)
                Image.fromarray(frame.copy()).save(str(op_dir / f"{label}.png"))
            except Exception as e:
                LogManager().append(f"[WARN] save frame failed: {e}")

        threading.Thread(target=_save, daemon=True).start()

