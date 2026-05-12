from __future__ import annotations

import json
import time
from pathlib import Path


from log_manager import LogManager
from scene_index import SceneIndex




class EventUnknownProcessorMixin:
    def _process_event_unknown_folder(self, op_dir: Path):
        index_path = op_dir / "index.json"
        if not index_path.exists():
            return
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            LogManager().append(f"[EventUnknown] index 读取失败 {op_dir.name}: {e}")
            return
        if not self._event_unknown_should_process(op_dir, data):
            return

        data["auto_process_attempts"] = int(data.get("auto_process_attempts") or 0) + 1
        data["auto_process_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        data["status"] = "processing"
        index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        LogManager().append(f"[EventUnknown] 开始处理 {op_dir.name}")

        before_path = op_dir / (data.get("images", {}).get("before") or "before.png")
        after_name = data.get("images", {}).get("after") or "after_300ms.png"
        after_path = op_dir / after_name

        if before_path.exists():
            try:
                from scene_index import SceneIndex

                data["scene_index"] = SceneIndex().ensure_scene(before_path, threshold=0.92)
                if not data["scene_index"].get("matched"):
                    queued = self._queue_scene_for_unknown_processor(before_path, op_dir.name, "before")
                    if queued:
                        data["scene_index"]["queued_unknown"] = queued
            except Exception as e:
                data["scene_index"] = {"error": str(e)}

        if after_path.exists():
            try:
                from scene_index import SceneIndex

                after_scene = SceneIndex().ensure_scene(after_path, threshold=0.92)
                if not after_scene.get("matched"):
                    queued = self._queue_scene_for_unknown_processor(after_path, op_dir.name, "after")
                    if queued:
                        after_scene["queued_unknown"] = queued
                data["after_scene_index"] = after_scene
            except Exception as e:
                data["after_scene_index"] = {"error": str(e)}

        data["detected_yolo_objects"] = self._detect_yolo_objects(op_dir, data)
        data["click_target"] = self._analyze_click_target(
            op_dir,
            data,
            data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
        )
        click_status = data.get("click_target", {}).get("status")
        if click_status == "runtime_rule_matched":
            if data["click_target"].get("user_intent"):
                data["gpt_user_intent"] = data["click_target"]["user_intent"]
            data["gpt_yolo_objects"] = {
                "status": "skipped_runtime_rule",
                "objects": [],
                "reason": "runtime rule matched",
            }
        elif click_status == "yolo_matched":
            data["gpt_yolo_objects"] = {"status": "skipped_yolo_hit", "objects": []}
        else:
            data["gpt_yolo_objects"] = self._analyze_yolo_objects_with_gpt55(
            op_dir,
            data,
            data.get("scene_index") if isinstance(data.get("scene_index"), dict) else None,
            )
        data["yolo"] = self._write_yolo_event_annotation(op_dir, data)
        try:
            from agent_data import AgentDataManager

            event_id = AgentDataManager().record_physical_event(
                event_key=op_dir.name,
                action_type=data.get("action_type", ""),
                timestamp_ms=int(time.time() * 1000),
                duration_ms=int(data.get("duration_ms") or 0),
                touch=data.get("touch", {}),
                folder_path=op_dir,
                images=data.get("images", {}),
                index_path=index_path,
                yolo=data.get("yolo"),
            )
            data["db"] = {"physical_event_id": event_id}
        except Exception as e:
            data["db"] = {"error": str(e)}
            LogManager().append(f"[EventUnknown] 入库失败 {op_dir.name}: {e}")

        target_status = "review_pending"
        click_status = data.get("click_target", {}).get("status")
        gpt_status = data.get("gpt_yolo_objects", {}).get("status") if isinstance(data.get("gpt_yolo_objects"), dict) else ""
        if click_status in ("error", "no_before_image", "before_image_missing"):
            target_status = "needs_model_or_manual"
        elif click_status == "needs_model_or_manual" and gpt_status not in ("ok",):
            target_status = "needs_model_or_manual"
        data["status"] = target_status
        index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        LogManager().append(f"[EventUnknown] 处理完成 {op_dir.name} -> {target_status}")
        scene_name = ""
        if isinstance(data.get("scene_index"), dict):
            scene_name = data["scene_index"].get("scene_key") or ""
        click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}
        rule_name = click_target.get("element_name", "") if click_target.get("status") == "runtime_rule_matched" else ""
        self._bridge.overlay_changed.emit({
            "scene": scene_name,
            "rule": rule_name,
            "status": "规则命中" if rule_name else ("待审核" if target_status == "review_pending" else target_status),
        })
        self._bridge.events_changed.emit()

