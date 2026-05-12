from __future__ import annotations

import threading
import time
from pathlib import Path
from datetime import datetime

import scrcpy

from log_manager import LogManager






class PhysicalTouchInputMixin:
    def _on_physical_touch(self, device_x: int, device_y: int, action: int):
        frame_x, frame_y = self._map_device_to_frame(device_x, device_y)
        if frame_x is None:
            return

        if action == scrcpy.ACTION_DOWN:
            from datetime import datetime

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            op_dir = Path("screenshots") / "event_unknown" / f"physical_{ts}"
            op_dir.mkdir(parents=True, exist_ok=True)

            self._physical_touch_start = (device_x, device_y)
            self._physical_touch_last = (device_x, device_y)
            self._physical_touch_frame_start = (frame_x, frame_y)
            self._physical_touch_frame_last = (frame_x, frame_y)
            self._physical_touch_time = time.time()
            self._physical_op_dir = op_dir

            self._save_video_frame_async("before", op_dir)
            self._bridge.touch_feedback.emit([(frame_x, frame_y)], 1500)

            def _capture_pressed():
                time.sleep(0.08)
                self._save_video_frame_sync("pressed", op_dir)

            threading.Thread(target=_capture_pressed, daemon=True).start()
            LogManager().append(f"[GetEvent] DOWN device=({device_x},{device_y}) frame=({frame_x},{frame_y})")

        elif action == scrcpy.ACTION_MOVE:
            self._physical_touch_last = (device_x, device_y)
            self._physical_touch_frame_last = (frame_x, frame_y)
            if self._physical_touch_frame_start:
                self._bridge.touch_feedback.emit(
                    [self._physical_touch_frame_start, (frame_x, frame_y)],
                    1500,
                )

        elif action == scrcpy.ACTION_UP:
            if self._physical_touch_start is None:
                return

            sx, sy = self._physical_touch_start
            ex, ey = self._physical_touch_last or (device_x, device_y)
            frame_start = self._physical_touch_frame_start or (frame_x, frame_y)
            frame_end = self._physical_touch_frame_last or (frame_x, frame_y)
            duration_ms = int((time.time() - self._physical_touch_time) * 1000)
            op_dir = self._physical_op_dir

            dx = abs(ex - sx)
            dy = abs(ey - sy)
            action_type = "tap" if dx < 8 and dy < 8 else "swipe"
            self._bridge.touch_feedback.emit([frame_start, frame_end], 2000)

            def _exec():
                try:
                    if op_dir:
                        time.sleep(0.12)
                        self._save_video_frame_sync("after", op_dir)
                        self._write_touch_index(
                            op_dir,
                            f"physical_{action_type}",
                            duration_ms,
                            (sx, sy),
                            (ex, ey),
                            frame_start,
                            frame_end,
                            80,
                            120,
                        )
                        LogManager().append(
                            f"[GetEvent] UP {action_type} device=({sx},{sy})->({ex},{ey}) "
                            f"duration={duration_ms}ms -> {op_dir}"
                        )
                        self._bridge.events_changed.emit()
                except Exception as e:
                    LogManager().append(f"[GetEvent] record physical touch failed: {e}")

            threading.Thread(target=_exec, daemon=True).start()
            self._physical_touch_start = None
            self._physical_touch_last = None
            self._physical_touch_frame_start = None
            self._physical_touch_frame_last = None
            self._physical_op_dir = None

