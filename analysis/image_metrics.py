from __future__ import annotations

from pathlib import Path


def image_change_score(first_path: Path, second_path: Path, center=None) -> dict:
    from PIL import Image
    import numpy as np

    first = Image.open(first_path).convert("RGB")
    second = Image.open(second_path).convert("RGB").resize(first.size)

    def score(a, b):
        a = a.resize((160, 90))
        b = b.resize((160, 90))
        aa = np.asarray(a, dtype=np.int16)
        bb = np.asarray(b, dtype=np.int16)
        return round(float(np.mean(np.abs(aa - bb)) / 255.0), 6)

    result = {"global": score(first, second)}
    if center:
        x, y = center
        radius = 90
        left = max(0, int(x - radius))
        top = max(0, int(y - radius))
        right = min(first.width, int(x + radius))
        bottom = min(first.height, int(y + radius))
        if right > left and bottom > top:
            result["local"] = score(
                first.crop((left, top, right, bottom)),
                second.crop((left, top, right, bottom)),
            )
    return result


def click_bbox(image_size: tuple[int, int], data: dict) -> list[int]:
    width, height = image_size
    touch = data.get("touch", {})
    start = touch.get("frame_start", {})
    end = touch.get("frame_end", start)
    sx, sy = int(start.get("x", 0)), int(start.get("y", 0))
    ex, ey = int(end.get("x", sx)), int(end.get("y", sy))
    if "swipe" in data.get("action_type", ""):
        pad = max(48, int(min(width, height) * 0.05))
        x1, x2 = sorted((sx, ex))
        y1, y2 = sorted((sy, ey))
        x1 -= pad
        y1 -= pad
        x2 += pad
        y2 += pad
    else:
        box_size = max(96, min(180, int(min(width, height) * 0.14)))
        half = box_size // 2
        x1, y1 = sx - half, sy - half
        x2, y2 = sx + half, sy + half
    return [
        max(0, min(width - 1, int(x1))),
        max(0, min(height - 1, int(y1))),
        max(1, min(width, int(x2))),
        max(1, min(height, int(y2))),
    ]
