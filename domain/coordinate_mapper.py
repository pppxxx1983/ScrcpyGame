from __future__ import annotations

import re


def oriented_screen_size(frame_width: int, frame_height: int, device_resolution: tuple[int, int]) -> tuple[int, int, str]:
    device_width, device_height = device_resolution
    if frame_width > frame_height:
        return max(device_width, device_height), min(device_width, device_height), "landscape"
    return min(device_width, device_height), max(device_width, device_height), "portrait"


def frame_to_device(frame_x: int, frame_y: int, frame_shape, device_resolution: tuple[int, int]) -> tuple[int, int, str]:
    frame_height, frame_width = frame_shape[:2]
    screen_width, screen_height, orientation = oriented_screen_size(frame_width, frame_height, device_resolution)
    x = int(frame_x * screen_width / max(1, frame_width))
    y = int(frame_y * screen_height / max(1, frame_height))
    x = max(0, min(x, screen_width - 1))
    y = max(0, min(y, screen_height - 1))
    return x, y, orientation


def device_to_frame(device_x: int, device_y: int, frame_shape, device_resolution: tuple[int, int]) -> tuple[int, int]:
    frame_height, frame_width = frame_shape[:2]
    screen_width, screen_height, _ = oriented_screen_size(frame_width, frame_height, device_resolution)
    x = int(device_x * frame_width / max(1, screen_width))
    y = int(device_y * frame_height / max(1, screen_height))
    x = max(0, min(x, frame_width - 1))
    y = max(0, min(y, frame_height - 1))
    return x, y


def parse_abs_range(line: str):
    min_match = re.search(r"\bmin\s+(-?\d+)", line)
    max_match = re.search(r"\bmax\s+(-?\d+)", line)
    if not min_match or not max_match:
        return None
    return int(min_match.group(1)), int(max_match.group(1))


def raw_touch_to_device(raw_x, raw_y, touch_info, device_resolution: tuple[int, int], landscape: bool):
    if raw_x is None or raw_y is None or touch_info is None or device_resolution is None:
        return None, None

    _, min_x, max_x, min_y, max_y = touch_info
    device_width, device_height = device_resolution
    if landscape:
        screen_width = max(device_width, device_height)
        screen_height = min(device_width, device_height)
    else:
        screen_width = min(device_width, device_height)
        screen_height = max(device_width, device_height)

    nx = (raw_x - min_x) / max(1, max_x - min_x)
    ny = (raw_y - min_y) / max(1, max_y - min_y)
    nx = max(0.0, min(1.0, nx))
    ny = max(0.0, min(1.0, ny))
    if landscape:
        return int(ny * (screen_width - 1)), int((1.0 - nx) * (screen_height - 1))
    return int(nx * (screen_width - 1)), int(ny * (screen_height - 1))
