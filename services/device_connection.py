from __future__ import annotations

import re
import threading
from typing import Optional, Tuple

import scrcpy

from log_manager import LogManager


from PySide6.QtWidgets import QLineEdit, QListWidgetItem


class DeviceConnectionMixin:
    def _update_connect_buttons(self, connected: bool) -> None:
        self._bridge.buttons_changed.emit(connected)

    def _update_connect_buttons_slot(self, connected: bool) -> None:
        if self.btn_ip:
            self.btn_ip.setText("断开连接" if connected else "IP 连接")
        if self.btn_adb:
            self.btn_adb.setText("断开连接" if connected else "连接选中设备")

    def disconnect_device(self) -> None:
        self._stop_getevent_listener()
        if self.execution_engine.is_running():
            self.execution_engine.stop()
        if self.client:
            self.client.stop()
            self.client = None
        self._update_connect_buttons(False)
        self._set_status("状态: 已断开")

    def do_ip_connect(self) -> None:
        if self.client and self.client.alive:
            self.disconnect_device()
            return
        ip = self.edit_ip.text().strip() if self.edit_ip else ""
        port = self.edit_port.text().strip() if self.edit_port else "5555"
        if not ip:
            self._set_status("状态: 请输入 IP 地址")
            return
        device = f"{ip}:{port}"
        self._set_status(f"状态: 正在连接 {device}...")
        self.connect_device(device)

    def do_refresh_adb(self) -> None:
        from adbutils import adb
        try:
            devices = adb.device_list()
            if self.list_adb:
                self.list_adb.clear()
                for d in devices:
                    try:
                        model = d.prop.model
                    except Exception:
                        model = "未知型号"
                    item = QListWidgetItem(f"{d.serial}  ({model})")
                    item.setData(256, d.serial)
                    self.list_adb.addItem(item)
            self._set_status(f"状态: 发现 {len(devices)} 个设备")
        except Exception as e:
            self._set_status(f"状态: 刷新失败 - {e}")

    def do_adb_connect(self) -> None:
        if self.client and self.client.alive:
            self.disconnect_device()
            return
        device_serial: Optional[str] = None
        if self.list_adb:
            item = self.list_adb.currentItem()
            if item:
                device_serial = item.data(256)
            elif self.list_adb.count() > 0:
                self.list_adb.setCurrentRow(0)
                device_serial = self.list_adb.item(0).data(256)
        if not device_serial:
            self._set_status("状态: 请先刷新并选择设备")
            return
        self._set_status(f"状态: 正在连接 {device_serial}...")
        self.connect_device(device_serial)

    def _get_device_resolution(self, device_serial: str) -> Optional[Tuple[int, int]]:
        """通过 adb 获取设备真实分辨率，绕过 scrcpy 库的协议解析 bug"""
        try:
            from adbutils import adb
            d = adb.device(serial=device_serial)
            # 先尝试 wm size
            output = d.shell("wm size")
            LogManager().append(f"[ADB] wm size output: {output.strip()}")
            m = re.search(r'(\d+)x(\d+)', output)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                LogManager().append(f"[ADB] parsed resolution from wm size: ({w}, {h})")
                return (w, h)
            # fallback: dumpsys
            output = d.shell("dumpsys window displays | grep -E 'init|DisplayDeviceInfo'")
            m = re.search(r'(\d+)\s*x\s*(\d+)', output)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                LogManager().append(f"[ADB] parsed resolution from dumpsys: ({w}, {h})")
                return (w, h)
        except Exception as e:
            LogManager().append(f"[ADB] get resolution failed: {e}")
        return None

    def connect_device(self, device: str) -> None:
        if self.client:
            self.client.stop()
            self.client = None

        try:
            from adbutils import adb
            d = adb.device(serial=device)
            d.shell("pkill -f 'app_process.*scrcpy' 2>/dev/null || true")
        except Exception:
            pass

        self._device_resolution = self._get_device_resolution(device)

        def on_frame(frame) -> None:
            if frame is not None:
                self._pending_frame = frame
                self._frame_flush_count += 1

        def on_init() -> None:
            cr = self.client.resolution
            LogManager().append(f"[Scrcpy] on_init, handshake resolution: {cr}")
            if cr and len(cr) == 2 and all(isinstance(v, int) and 0 < v < 10000 for v in cr):
                self._device_resolution = cr
                LogManager().append(f"[Scrcpy] using handshake resolution: {cr}")
            elif self._device_resolution is None:
                self._device_resolution = self._get_device_resolution(device)
                LogManager().append(f"[Scrcpy] fallback to adb resolution: {self._device_resolution}")
            else:
                LogManager().append(f"[Scrcpy] using pre-fetched adb resolution: {self._device_resolution}")
            self._start_getevent_listener(device)
            self._update_connect_buttons(True)
            self._set_status("状态: 已连接")

        def on_disconnect() -> None:
            self._stop_getevent_listener()
            self._update_connect_buttons(False)
            self._set_status("状态: 已断开")

        def run() -> None:
            try:
                self.client = scrcpy.Client(
                    device=device,
                    max_width=self._scrcpy_max_width,
                    bitrate=self._scrcpy_bitrate,
                    max_fps=self._scrcpy_max_fps,
                    block_frame=True,
                )
                self._adb_device = self.client.device
                self.client.add_listener(scrcpy.EVENT_INIT, on_init)
                self.client.add_listener(scrcpy.EVENT_FRAME, on_frame)
                self.client.add_listener(scrcpy.EVENT_DISCONNECT, on_disconnect)
                self.client.start(daemon_threaded=True)
            except Exception as e:
                import traceback
                self._update_connect_buttons(False)
                self._set_status(f"状态: 连接失败 - {e}")
                LogManager().append(f"[ERROR] 连接失败:\n{traceback.format_exc()}")

        threading.Thread(target=run, daemon=True).start()

    def do_auto_ip(self) -> None:
        import re
        from adbutils import adb

        try:
            device = adb.device()
            output = device.shell("ip addr show wlan0")
            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/', output)
            if not match:
                output = device.shell("ifconfig wlan0")
                match = re.search(r'addr:(\d+\.\d+\.\d+\.\d+)', output)
            if not match:
                output = device.shell("ip route")
                match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', output)

            if match:
                ip = match.group(1)
                edit_ip = self.findChild(QLineEdit, "editIp")
                if edit_ip:
                    edit_ip.setText(ip)
                self._set_status(f"状态: 已自动获取 IP {ip}")
            else:
                self._set_status("状态: 无法获取 IP，请手动输入")
        except Exception as e:
            self._set_status(f"状态: 获取 IP 失败 - {e}")

