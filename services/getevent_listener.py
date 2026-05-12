from __future__ import annotations

import re
import socket
import threading

import scrcpy

from log_manager import LogManager




class GeteventListenerMixin:
    def _get_touch_input_info(self, device):
        try:
            output = device.shell("getevent -lp", timeout=5)
        except Exception as e:
            LogManager().append(f"[GetEvent] getevent -lp failed: {e}")
            return None

        devices = {}
        current = None
        for line in output.splitlines():
            match = re.search(r"add device \d+:\s+(\S+)", line)
            if match:
                current = match.group(1)
                devices.setdefault(current, {})
                continue
            if not current:
                continue

            if "ABS_MT_POSITION_X" in line or re.search(r"\b0035\b", line):
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["x"] = parsed
                    devices[current]["mt_x"] = True
            elif "ABS_MT_POSITION_Y" in line or re.search(r"\b0036\b", line):
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["y"] = parsed
                    devices[current]["mt_y"] = True
            elif "ABS_X" in line and "x" not in devices[current]:
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["x"] = parsed
            elif "ABS_Y" in line and "y" not in devices[current]:
                parsed = self._parse_abs_range(line)
                if parsed:
                    devices[current]["y"] = parsed

        for path, info in devices.items():
            if "x" in info and "y" in info and info.get("mt_x") and info.get("mt_y"):
                LogManager().append(f"[GetEvent] touch device: {path}, x={info['x']}, y={info['y']}")
                return path, info["x"][0], info["x"][1], info["y"][0], info["y"][1]

        for path, info in devices.items():
            if "x" in info and "y" in info:
                LogManager().append(f"[GetEvent] touch device: {path}, x={info['x']}, y={info['y']}")
                return path, info["x"][0], info["x"][1], info["y"][0], info["y"][1]

        LogManager().append("[GetEvent] no touch input device found")
        return None

    def _start_getevent_listener(self, device_serial: str):
        self._stop_getevent_listener()
        self._getevent_stop = threading.Event()
        self._getevent_generation += 1
        generation = self._getevent_generation
        self._getevent_thread = threading.Thread(
            target=self._getevent_loop,
            args=(device_serial, self._getevent_stop, generation),
            daemon=True,
        )
        self._getevent_thread.start()

    def _stop_getevent_listener(self):
        self._getevent_generation += 1
        if hasattr(self, "_getevent_stop") and self._getevent_stop:
            self._getevent_stop.set()
        conn = getattr(self, "_getevent_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._getevent_conn = None

    def _getevent_value(line: str):
        parts = line.strip().split()
        if not parts:
            return None
        value = parts[-1]
        if value == "DOWN":
            return 1
        if value == "UP":
            return 0
        try:
            return int(value, 16)
        except ValueError:
            try:
                return int(value)
            except ValueError:
                return None

    def _getevent_loop(self, device_serial: str, stop_event: threading.Event, generation: int):
        try:
            from adbutils import adb
            from adbutils.errors import AdbTimeout

            device = adb.device(serial=device_serial)
            touch_info = self._get_touch_input_info(device)
            if not touch_info:
                return

            path = touch_info[0]
            conn = device.shell(["getevent", "-lt", path], stream=True, timeout=None, encoding=None)
            self._getevent_conn = conn
            try:
                conn.conn.settimeout(0.05)
            except Exception:
                pass
            LogManager().append(f"[GetEvent] listening physical touches on {path}")

            buffer = ""
            raw_x = None
            raw_y = None
            is_down = False
            active = False

            while not stop_event.is_set():
                if generation != self._getevent_generation:
                    break
                try:
                    chunk = conn.recv(128)
                except (socket.timeout, AdbTimeout):
                    continue
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")
                lines = buffer.splitlines()
                if buffer and not buffer.endswith(("\n", "\r")):
                    buffer = lines.pop() if lines else buffer
                else:
                    buffer = ""

                for line in lines:
                    value = self._getevent_value(line)
                    if value is None:
                        continue

                    if "ABS_MT_POSITION_X" in line or re.search(r"\b0035\b", line):
                        raw_x = value
                    elif "ABS_MT_POSITION_Y" in line or re.search(r"\b0036\b", line):
                        raw_y = value
                    elif "BTN_TOUCH" in line or re.search(r"\b014a\b", line):
                        is_down = value != 0
                    elif "ABS_MT_TRACKING_ID" in line or re.search(r"\b0039\b", line):
                        is_down = value != 0xFFFFFFFF

                    if "SYN_REPORT" in line or re.search(r"\b0000\s+0000\b", line):
                        device_x, device_y = self._raw_touch_to_device(raw_x, raw_y, touch_info)
                        if device_x is None:
                            continue
                        if is_down and not active:
                            active = True
                            self._on_physical_touch(device_x, device_y, scrcpy.ACTION_DOWN)
                        elif is_down and active:
                            self._on_physical_touch(device_x, device_y, scrcpy.ACTION_MOVE)
                        elif not is_down and active:
                            active = False
                            self._on_physical_touch(device_x, device_y, scrcpy.ACTION_UP)
        except Exception as e:
            if not stop_event.is_set():
                LogManager().append(f"[GetEvent] listener stopped: {e}")
        finally:
            if generation == self._getevent_generation and getattr(self, "_getevent_conn", None) is not None:
                try:
                    self._getevent_conn.close()
                except Exception:
                    pass
                self._getevent_conn = None

