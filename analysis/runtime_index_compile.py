from __future__ import annotations

from pathlib import Path


from log_manager import LogManager
from scene_index import image_fingerprint




class RuntimeIndexCompileMixin:
    def _compile_runtime_index_from_review(
        self,
        folder: Path,
        data: dict,
        image_path: Path,
        approved_objects: list[dict],
        source: str = "human_review",
    ) -> dict:
        """Write approved scene UI and action hints into the realtime SQLite index."""
        try:
            from PIL import Image
            from agent_data import AgentDataManager
            from scene_index import image_fingerprint

            dm = AgentDataManager()
            scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
            after_scene = data.get("after_scene_index", {}) if isinstance(data.get("after_scene_index"), dict) else {}
            scene_id = scene.get("scene_id") if scene.get("matched") else None
            scene_key = scene.get("scene_key") or folder.name
            next_scene_id = after_scene.get("scene_id") if after_scene.get("matched") else None
            next_scene_key = after_scene.get("scene_key") or ""
            user_intent = str(data.get("gpt_user_intent") or "").strip()
            action_type = str(data.get("action_type") or "tap").strip()
            click_target = data.get("click_target", {}) if isinstance(data.get("click_target"), dict) else {}

            compiled_elements = 0
            compiled_rules = 0
            crop_dir = folder / "runtime_crops"
            crop_dir.mkdir(parents=True, exist_ok=True)

            with Image.open(image_path).convert("RGB") as img:
                width, height = img.size
                for idx, obj in enumerate(approved_objects):
                    bbox = obj.get("bbox_xyxy") or []
                    if len(bbox) != 4:
                        continue
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    x1 = max(0, min(width - 1, x1))
                    y1 = max(0, min(height - 1, y1))
                    x2 = max(x1 + 1, min(width, x2))
                    y2 = max(y1 + 1, min(height, y2))
                    class_name = self._safe_yolo_class_name(obj.get("class_name") or "ui_element")
                    crop_path = crop_dir / f"{idx + 1:03d}_{class_name}.png"
                    img.crop((x1, y1, x2, y2)).save(str(crop_path))
                    fingerprint = image_fingerprint(crop_path)
                    class_id = int(obj.get("class_id") if obj.get("class_id") is not None else self._ensure_yolo_class(class_name))
                    confidence = float(obj.get("confidence") or 0.9)
                    role = str(obj.get("role") or "ui_element")
                    action_effect = str(obj.get("action_effect") or click_target.get("action_effect") or "")
                    element_id = dm.upsert_ui_element(
                        scene_id=scene_id,
                        scene_key=scene_key,
                        element_type=role,
                        element_name=class_name,
                        text=str(obj.get("name") or obj.get("text") or ""),
                        bbox_xyxy=[x1, y1, x2, y2],
                        source=source,
                        confidence=confidence,
                        fingerprint=fingerprint,
                        image_path=crop_path,
                        yolo_class_id=class_id,
                        action_effect=action_effect,
                    )
                    compiled_elements += 1

                    is_clicked = role == "clicked_target"
                    if not is_clicked:
                        tx = data.get("touch", {}).get("frame_start", {}).get("x")
                        ty = data.get("touch", {}).get("frame_start", {}).get("y")
                        try:
                            is_clicked = x1 <= int(tx) <= x2 and y1 <= int(ty) <= y2
                        except Exception:
                            is_clicked = False
                    if is_clicked or action_effect:
                        rule_key = "|".join([
                            str(scene_id or scene_key),
                            action_type,
                            class_name,
                            str(next_scene_id or next_scene_key),
                        ])
                        dm.upsert_runtime_rule(
                            rule_key=rule_key,
                            scene_id=scene_id,
                            scene_key=scene_key,
                            element_id=element_id,
                            element_name=class_name,
                            action_type=action_type,
                            action_effect=action_effect,
                            user_intent=user_intent,
                            bbox_xyxy=[x1, y1, x2, y2],
                            next_scene_id=next_scene_id,
                            next_scene_key=next_scene_key,
                            source_event=folder.name,
                            source=source,
                            confidence=confidence,
                        )
                        compiled_rules += 1

            return {"elements": compiled_elements, "rules": compiled_rules}
        except Exception as e:
            LogManager().append(f"[RuntimeIndex] compile failed {folder.name}: {e}")
            return {"error": str(e), "elements": 0, "rules": 0}

