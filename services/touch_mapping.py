from __future__ import annotations



from log_manager import LogManager
from domain.coordinate_mapper import (
    device_to_frame,
    frame_to_device,
    parse_abs_range,
    raw_touch_to_device,
)




class TouchMappingMixin:
    def _map_frame_to_device(self, frame_x: int, frame_y: int):
        frame = self.video_widget._frame
        if frame is None or self._device_resolution is None:
            LogManager().append(f"[TouchMap] skip: frame={frame is not None}, resolution={self._device_resolution}")
            return None, None
        fh, fw = frame.shape[:2]
        x, y, orientation = frame_to_device(frame_x, frame_y, frame.shape, self._device_resolution)
        if orientation == "landscape":
            screen_w, screen_h = max(self._device_resolution), min(self._device_resolution)
        else:
            screen_w, screen_h = min(self._device_resolution), max(self._device_resolution)
        LogManager().append(
            f"[TouchMap] frame({fw}x{fh}) -> device({screen_w}x{screen_h}, {orientation}) | "
            f"input({frame_x},{frame_y}) -> output({x},{y})"
        )
        return x, y

    def _map_device_to_frame(self, device_x: int, device_y: int):
        frame = self.video_widget._frame if self.video_widget else None
        if frame is None or self._device_resolution is None:
            return None, None
        return device_to_frame(device_x, device_y, frame.shape, self._device_resolution)

    def _parse_abs_range(line: str):
        return parse_abs_range(line)

    def _raw_touch_to_device(self, raw_x, raw_y, touch_info):
        if raw_x is None or raw_y is None or touch_info is None or self._device_resolution is None:
            return None, None
        frame = self.video_widget._frame if self.video_widget else None
        landscape = frame is not None and frame.shape[1] > frame.shape[0]
        return raw_touch_to_device(raw_x, raw_y, touch_info, self._device_resolution, landscape)

