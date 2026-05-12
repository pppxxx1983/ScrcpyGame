from __future__ import annotations

import threading
import time
from pathlib import Path
from datetime import datetime

import scrcpy

from log_manager import LogManager






class ProjectedTouchInputMixin:
    def _on_touch(self, frame_x: int, frame_y: int, action: int):
        if not self._projection_control_enabled:
            return
        device_x, device_y = self._map_frame_to_device(frame_x, frame_y)
        if device_x is None:
            return

        session_active = self.execution_engine.dm.is_session_active()

        if action == 0:          # DOWN
            from datetime import datetime

            self._touch_start = (device_x, device_y)
            self._touch_last = (device_x, device_y)
            self._touch_frame_start = (frame_x, frame_y)
            self._touch_frame_last = (frame_x, frame_y)
            self._touch_time = time.time()

            if session_active:
                click_dir = self.execution_engine.dm.get_click_dir()
                idx = self.execution_engine.dm.click_counter + 1
                op_dir = click_dir / f"click_{idx:06d}"
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                op_dir = Path("screenshots") / f"op_{ts}"

            op_dir.mkdir(parents=True, exist_ok=True)
            self._op_dir_for_touch = op_dir

            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_DOWN)
            frame = self.video_widget._frame if self.video_widget else None
            self._save_video_frame_async("before", op_dir, frame)

            def _capture_pressed():
                time.sleep(0.08)
                self._save_video_frame_sync("pressed", op_dir)

            threading.Thread(
                target=_capture_pressed,
                daemon=True
            ).start()
        elif action == 2:        # MOVE
            self._touch_last = (device_x, device_y)
            self._touch_frame_last = (frame_x, frame_y)
            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_MOVE)
        elif action == 1:        # UP
            if self._touch_start is None:
                return
            sx, sy = self._touch_start
            ex, ey = self._touch_last
            frame_start = self._touch_frame_start or (frame_x, frame_y)
            frame_end = self._touch_frame_last or (frame_x, frame_y)
            duration_ms = int((time.time() - self._touch_time) * 1000)
            self._send_scrcpy_touch(frame_x, frame_y, scrcpy.ACTION_UP)

            dx = abs(ex - sx)
            dy = abs(ey - sy)
            is_tap = dx < 8 and dy < 8
            op_dir = self._op_dir_for_touch
            self._op_dir_for_touch = None

            def _exec():
                try:
                    if session_active and op_dir:
                        # Session 模式：委托给 ExecutionEngine
                        self.execution_engine.on_click_up(
                            sx, sy, op_dir,
                            lambda: self.video_widget._frame if self.video_widget else None
                        )
                        # 同时保留 index.json（向后兼容）
                        self._write_touch_index(
                            op_dir,
                            "tap" if is_tap else "swipe",
                            duration_ms,
                            (sx, sy),
                            (ex, ey),
                            frame_start,
                            frame_end,
                            80,
                            120,
                        )
                    else:
                        # 非 Session 模式：原有逻辑
                        if is_tap:
                            if op_dir:
                                time.sleep(0.12)
                                self._save_video_frame_sync("after", op_dir)
                                self._write_touch_index(
                                    op_dir,
                                    "tap",
                                    duration_ms,
                                    (sx, sy),
                                    (ex, ey),
                                    frame_start,
                                    frame_end,
                                    80,
                                    120,
                                )
                        else:
                            if op_dir:
                                time.sleep(0.12)
                                self._save_video_frame_sync("after", op_dir)
                                self._write_touch_index(
                                    op_dir,
                                    "swipe",
                                    duration_ms,
                                    (sx, sy),
                                    (ex, ey),
                                    frame_start,
                                    frame_end,
                                    80,
                                    120,
                                )
                except Exception:
                    pass

            threading.Thread(target=_exec, daemon=True).start()
            self._touch_start = None
            self._touch_frame_start = None
            self._touch_frame_last = None

