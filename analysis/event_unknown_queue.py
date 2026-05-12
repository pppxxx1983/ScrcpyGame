from __future__ import annotations

import shutil
import time
from pathlib import Path


from log_manager import LogManager




class EventUnknownQueueMixin:
    def _queue_scene_for_unknown_processor(self, image_path: Path, event_key: str, label: str) -> str | None:
        try:
            import shutil

            if not image_path.exists():
                return None
            unknown_dir = Path("screenshots") / "unknown"
            unknown_dir.mkdir(parents=True, exist_ok=True)
            target = unknown_dir / f"{event_key}_{label}{image_path.suffix}"
            if not target.exists():
                shutil.copy2(str(image_path), str(target))
            return str(target)
        except Exception as e:
            LogManager().append(f"[WARN] queue scene unknown failed: {e}")
            return None

    def _event_unknown_should_process(self, folder: Path, data: dict) -> bool:
        status = data.get("status", "")
        if status == "review_approved":
            return False

        attempts = int(data.get("auto_process_attempts") or 0)
        if status == "processing":
            try:
                stale = time.time() - folder.stat().st_mtime > 60
            except Exception:
                stale = True
            if stale:
                LogManager().append(f"[EventUnknown] recover stale processing event: {folder.name}")
                return True
            return False

        if status in ("raw_captured", "", None):
            return True

        if status == "needs_model_or_manual":
            return attempts < 2

        if status == "review_pending":
            scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
            yolo = data.get("gpt_yolo_objects", {}) if isinstance(data.get("gpt_yolo_objects"), dict) else {}
            click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
            needs_scene = not scene or (not scene.get("matched") and not scene.get("queued_unknown"))
            needs_intent = not str(data.get("gpt_user_intent") or "").strip()
            needs_objects = yolo.get("status") in ("", None, "empty", "error", "no_before_image", "before_image_missing")
            needs_click = click_target.get("status") == "needs_model_or_manual"
            return attempts < 1 and (needs_scene or needs_intent or needs_objects or needs_click)

        return False

    def _event_unknown_loop(self):
        event_dir = Path("screenshots") / "event_unknown"
        event_dir.mkdir(parents=True, exist_ok=True)
        while not self._event_unknown_stop.is_set():
            self._process_event_unknown_once(event_dir)
            self._event_unknown_stop.wait(3)

    def _process_event_unknown_once(self, event_dir: Path):
        for folder in sorted(event_dir.glob("physical_*"), key=lambda p: p.stat().st_mtime):
            if self._event_unknown_stop.is_set():
                break
            if not folder.is_dir() or not (folder / ".ready").exists():
                continue
            self._process_event_unknown_folder(folder)

