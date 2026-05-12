from __future__ import annotations

import threading
import time
from pathlib import Path
from datetime import datetime

import scrcpy

from log_manager import LogManager






class ScrcpyControlMixin:
    def _send_scrcpy_touch(self, frame_x: int, frame_y: int, action: int) -> bool:
        if not (self.client and self.client.alive):
            return False
        try:
            self.client.control.touch(frame_x, frame_y, action)
            return True
        except Exception as e:
            LogManager().append(f"[WARN] scrcpy touch failed: {e}")
            return False

    def _on_scroll(self, frame_x: int, frame_y: int, h: int, v: int):
        if not self._projection_control_enabled:
            return
        device_x, device_y = self._map_frame_to_device(frame_x, frame_y)
        if device_x is None:
            return
        ex = device_x - h * 8
        ey = device_y - v * 8
        if abs(ex - device_x) < 30 and abs(ey - device_y) < 30:
            return

        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        op_dir = Path("screenshots") / f"op_{ts}"
        op_dir.mkdir(parents=True, exist_ok=True)
        self._save_video_frame_async("before", op_dir)

        sent = False
        if self.client and self.client.alive:
            try:
                self.client.control.scroll(frame_x, frame_y, h, v)
                sent = True
            except Exception as e:
                LogManager().append(f"[WARN] scrcpy scroll failed: {e}")

        def _exec():
            try:
                if not sent and self._adb_device is not None:
                    self._adb_device.shell(f"input swipe {device_x} {device_y} {ex} {ey} 150")
                time.sleep(0.12)
                self._save_video_frame_sync("after", op_dir)
            except Exception:
                pass

        threading.Thread(target=_exec, daemon=True).start()

