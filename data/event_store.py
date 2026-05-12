from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


def build_recording_event(op_dir: Path, data: dict, recording_context: dict) -> dict:
    return {
        "recording_kind": recording_context.get("kind", ""),
        "video_offset_ms": recording_context.get("video_offset_ms"),
        "timestamp_ms": int(time.time() * 1000),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "event_key": op_dir.name if op_dir else "",
        "folder_path": str(op_dir) if op_dir else "",
        "video_path": recording_context.get("video_path", ""),
        "session_id": recording_context.get("session_id", ""),
        "action_type": data.get("action_type", ""),
        "duration_ms": data.get("duration_ms", 0),
        "touch": data.get("touch", {}),
        "change": data.get("change", {}),
        "scene_index": data.get("scene_index", {}),
        "after_scene_index": data.get("after_scene_index", {}),
        "click_target": data.get("click_target", {}),
        "images": data.get("images", {}),
    }


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
