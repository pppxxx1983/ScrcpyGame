from __future__ import annotations

from pathlib import Path


from log_manager import LogManager
from data.event_store import append_jsonl, build_recording_event




class RecordingEventMixin:
    def _active_recording_context(self) -> dict:
        if hasattr(self, "execution_engine") and self.execution_engine:
            return self.execution_engine.get_recording_context()
        return {}

    def _append_recording_event(self, op_dir: Path, data: dict) -> None:
        ctx = self._active_recording_context()
        events_path = Path(ctx.get("events_path", "")) if ctx.get("events_path") else None
        if not events_path:
            return
        try:
            append_jsonl(events_path, build_recording_event(op_dir, data, ctx))
            if hasattr(self.execution_engine, "_write_recording_meta"):
                self.execution_engine._write_recording_meta(finished=False)
        except Exception as e:
            LogManager().append(f"[WARN] append recording event failed: {e}")

