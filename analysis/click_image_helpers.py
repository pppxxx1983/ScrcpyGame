from __future__ import annotations

from pathlib import Path


from log_manager import LogManager
from analysis.image_metrics import click_bbox, image_change_score




class ClickImageHelpersMixin:
    def _image_change_score(self, first_path: Path, second_path: Path, center=None) -> dict:
        try:
            return image_change_score(first_path, second_path, center=center)
        except Exception as e:
            LogManager().append(f"[WARN] compare frames failed: {e}")
            return {}

    def _click_bbox(self, image_size: tuple[int, int], data: dict) -> list[int]:
        return click_bbox(image_size, data)

