from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime


from log_manager import LogManager
from scene_index import SceneIndex




class TouchIndexWriterMixin:
    def _write_touch_index(
        self,
        op_dir: Path,
        action_type: str,
        duration_ms: int,
        start,
        end,
        frame_start,
        frame_end,
        pressed_delay_ms: int,
        after_delay_ms: int,
    ) -> None:
        try:
            import json
            from datetime import datetime

            before_path = op_dir / "before.png"
            pressed_path = op_dir / "pressed.png"
            after_path = op_dir / "after.png"
            after_300ms_path = op_dir / "after_300ms.png"

            # 优先使用 after.png，session 模式下使用 after_300ms.png
            compare_after_path = after_path if after_path.exists() else after_300ms_path

            before_pressed = (
                self._image_change_score(before_path, pressed_path, frame_start)
                if before_path.exists() and pressed_path.exists()
                else {}
            )
            before_after = (
                self._image_change_score(before_path, compare_after_path, frame_start)
                if before_path.exists() and compare_after_path.exists()
                else {}
            )

            local_change = before_pressed.get("local", before_pressed.get("global", 0.0))
            global_change = before_pressed.get("global", 0.0)
            pressed_changed = local_change >= 0.025 or global_change >= 0.006
            if duration_ms < pressed_delay_ms:
                pressed_state = "too_fast_to_capture_pressed"
            elif pressed_changed:
                pressed_state = "visual_change_detected"
            else:
                pressed_state = "no_visual_change_detected"

            data = {
                "status": "raw_captured",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "action_type": action_type,
                "duration_ms": duration_ms,
                "pressed_delay_ms": pressed_delay_ms,
                "after_delay_ms": after_delay_ms,
                "touch": {
                    "start": {"x": start[0], "y": start[1]},
                    "end": {"x": end[0], "y": end[1]},
                    "frame_start": {"x": frame_start[0], "y": frame_start[1]},
                    "frame_end": {"x": frame_end[0], "y": frame_end[1]},
                },
                "images": {
                    "before": "before.png",
                    "pressed": "pressed.png" if pressed_path.exists() else None,
                    "after": "after.png" if after_path.exists() else None,
                },
                "change": {
                    "before_pressed": before_pressed,
                    "before_after": before_after,
                    "pressed_state": pressed_state,
                },
            }
            recording_ctx = self._active_recording_context()
            if recording_ctx:
                data["recording"] = {
                    "kind": recording_ctx.get("kind", ""),
                    "video_path": recording_ctx.get("video_path", ""),
                    "events_path": recording_ctx.get("events_path", ""),
                    "meta_path": recording_ctx.get("meta_path", ""),
                    "video_offset_ms": recording_ctx.get("video_offset_ms"),
                    "started_timestamp_ms": recording_ctx.get("started_timestamp_ms"),
                    "session_id": recording_ctx.get("session_id", ""),
                }
            if op_dir.parent.name == "event_unknown":
                index_path = op_dir / "index.json"
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                (op_dir / ".ready").write_text(
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    encoding="utf-8",
                )
                LogManager().append(f"[EventUnknown] 原始事件已入队: {op_dir.name}")
                self._append_recording_event(op_dir, data)
                self._bridge.overlay_changed.emit({"scene": "", "rule": "", "status": "待处理"})
                self._bridge.events_changed.emit()
                return
            if before_path.exists():
                try:
                    from scene_index import SceneIndex

                    data["scene_index"] = SceneIndex().ensure_scene(
                        before_path,
                        threshold=0.92,
                    )
                    if not data["scene_index"].get("matched"):
                        queued = self._queue_scene_for_unknown_processor(before_path, op_dir.name, "before")
                        if queued:
                            data["scene_index"]["queued_unknown"] = queued
                except Exception as e:
                    data["scene_index"] = {"error": str(e)}
            if compare_after_path.exists():
                try:
                    from scene_index import SceneIndex

                    after_scene = SceneIndex().ensure_scene(compare_after_path, threshold=0.92)
                    if not after_scene.get("matched"):
                        queued = self._queue_scene_for_unknown_processor(compare_after_path, op_dir.name, "after")
                        if queued:
                            after_scene["queued_unknown"] = queued
                    data["after_scene_index"] = after_scene
                except Exception as e:
                    data["after_scene_index"] = {"error": str(e)}
            data["click_target"] = self._analyze_click_target(
                op_dir,
                data,
                data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
            )
            data["yolo"] = self._write_yolo_event_annotation(op_dir, data)
            index_path = op_dir / "index.json"
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            scene_name = ""
            if isinstance(data.get("scene_index"), dict):
                scene_name = data["scene_index"].get("scene_key") or ""
            click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
            click_status = click_target.get("status", "")
            rule_name = click_target.get("element_name", "") if click_status == "runtime_rule_matched" else ""
            self._bridge.overlay_changed.emit({
                "scene": scene_name,
                "rule": rule_name,
                "status": "规则命中" if rule_name else ("待审核" if data.get("status") == "raw_captured" else str(data.get("status", ""))),
            })
            try:
                from agent_data import AgentDataManager

                event_id = AgentDataManager().record_physical_event(
                    event_key=op_dir.name,
                    action_type=action_type,
                    timestamp_ms=int(time.time() * 1000),
                    duration_ms=duration_ms,
                    touch=data["touch"],
                    folder_path=op_dir,
                    images=data["images"],
                    index_path=index_path,
                    yolo=data.get("yolo"),
                )
                data["db"] = {"physical_event_id": event_id}
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                LogManager().append(f"[WARN] record physical event db failed: {e}")
            self._append_recording_event(op_dir, data)
        except Exception as e:
            LogManager().append(f"[WARN] write touch index failed: {e}")

