from __future__ import annotations

from pathlib import Path


from log_manager import LogManager
from scene_index import image_fingerprint




class ClickTargetPipelineMixin:
    def _analyze_click_target(self, op_dir: Path, data: dict, scene_result: dict | None, collect_debug: bool = False) -> dict:
        debug_info = {
            "scene_result": scene_result,
            "click": {},
            "steps": [],
        }
        try:
            from PIL import Image
            from scene_index import image_fingerprint
            from agent_data import AgentDataManager

            before_name = data.get("images", {}).get("before")
            if not before_name:
                result = {"status": "no_before_image"}
                if collect_debug:
                    result["_debug"] = debug_info
                return result
            before_path = op_dir / before_name
            if not before_path.exists():
                result = {"status": "before_image_missing"}
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            debug_info["click"] = {"x": click_x, "y": click_y}
            dm = AgentDataManager()

            # Step 1: Runtime Rule
            step_rules = {
                "name": "runtime_rule",
                "candidates": [],
                "matched": False,
            }
            matched_rule = None
            if scene_result and scene_result.get("matched"):
                rules = dm.list_runtime_rules_for_scene(
                    scene_id=scene_result.get("scene_id"),
                    scene_key=scene_result.get("scene_key", ""),
                )
                for rule in rules:
                    bbox = rule.get("bbox_xyxy") or []
                    candidate = {
                        "id": rule.get("id"),
                        "element_name": rule.get("element_name") or "tap_target",
                        "bbox_xyxy": bbox,
                        "confidence": rule.get("confidence") or 0.9,
                        "hits": rule.get("hits", 0),
                        "enabled": rule.get("enabled", True),
                    }
                    if len(bbox) != 4:
                        candidate["reason"] = "invalid_bbox"
                        step_rules["candidates"].append(candidate)
                        continue
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    candidate["contains_click"] = x1 <= click_x <= x2 and y1 <= click_y <= y2
                    step_rules["candidates"].append(candidate)
                    if candidate["contains_click"] and matched_rule is None:
                        matched_rule = rule
                        step_rules["matched"] = True
            debug_info["steps"].append(step_rules)

            if matched_rule:
                rule = matched_rule
                bbox = rule.get("bbox_xyxy") or []
                result = {
                    "status": "runtime_rule_matched",
                    "rule_id": rule.get("id"),
                    "element_id": rule.get("element_id"),
                    "element_name": rule.get("element_name") or "tap_target",
                    "element_type": "runtime_rule",
                    "action_effect": rule.get("action_effect") or "",
                    "user_intent": rule.get("user_intent") or "",
                    "bbox_xyxy": bbox,
                    "confidence": rule.get("confidence") or 0.9,
                    "source_event": rule.get("source_event") or "",
                }
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            # Step 2: YOLO
            yolo_match = self._detect_yolo_click_target(before_path, data)
            step_yolo = {
                "name": "yolo",
                "matched": bool(yolo_match),
                "objects": yolo_match.get("objects", []) if yolo_match else [],
                "best_match": yolo_match if yolo_match else None,
            }
            debug_info["steps"].append(step_yolo)
            if yolo_match:
                data["yolo_detected_objects"] = {"objects": yolo_match.get("objects", [])}
                result = yolo_match
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            with Image.open(before_path).convert("RGB") as img:
                bbox = self._click_bbox(img.size, data)
                x1, y1, x2, y2 = bbox
                crop_dir = op_dir / "crops"
                crop_dir.mkdir(parents=True, exist_ok=True)
                crop_path = crop_dir / "click_target.png"
                img.crop((x1, y1, x2, y2)).save(str(crop_path))

            yolo_hit = self._yolo_object_at_touch(data)
            if yolo_hit:
                bbox = [int(v) for v in yolo_hit["bbox_xyxy"]]
                element_name = yolo_hit.get("class_name") or "tap_target"
                class_id = self._ensure_yolo_class(element_name)
                return {
                    "status": "yolo_matched",
                    "element_name": element_name,
                    "element_type": "ui_element",
                    "action_effect": "",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "source": "yolo",
                    "yolo_class_id": class_id,
                    "confidence": yolo_hit.get("confidence", 0.0),
                }

            fingerprint = image_fingerprint(crop_path)

            # Step 3: Hash
            matched = dm.find_ui_element_by_hash(fingerprint)
            step_hash = {
                "name": "hash",
                "matched": bool(matched),
                "fingerprint_summary": {k: str(v)[:32] for k, v in (fingerprint or {}).items()},
                "best_match": {
                    "id": matched.get("id"),
                    "element_name": matched.get("element_name"),
                    "confidence": matched.get("confidence"),
                } if matched else None,
            }
            debug_info["steps"].append(step_hash)
            if matched:
                result = {
                    "status": "hash_matched",
                    "element_id": matched["id"],
                    "element_name": matched.get("element_name") or "tap_target",
                    "action_effect": matched.get("action_effect") or "",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "hash": fingerprint,
                    "match_confidence": matched["confidence"],
                }
                if collect_debug:
                    result["_debug"] = debug_info
                return result

            # Step 4: LLM
            llm_result = self._describe_click_target_with_llm(
                before_path,
                data,
                scene_result,
                fallback_crop_path=crop_path,
                fallback_bbox=bbox,
            )
            step_llm = {
                "name": "llm",
                "matched": False,
                "result_summary": {
                    "element_name": llm_result.get("element_name"),
                    "element_type": llm_result.get("element_type"),
                    "confidence": llm_result.get("confidence"),
                    "parse_ok": llm_result.get("parse_ok", False),
                    "error": llm_result.get("error"),
                },
            }
            element_name = (llm_result.get("element_name") or "").strip()
            if (
                not element_name
                or element_name == "tap_target"
                or llm_result.get("error")
                or not llm_result.get("parse_ok", False)
            ):
                step_llm["reason"] = "low_confidence_or_parse_error"
                debug_info["steps"].append(step_llm)
                result = {
                    "status": "needs_model_or_manual",
                    "reason": "click target was not confidently identified",
                    "bbox_xyxy": bbox,
                    "crop_image": str(crop_path),
                    "hash": fingerprint,
                    "llm": llm_result,
                }
                if collect_debug:
                    result["_debug"] = debug_info
                return result
            step_llm["matched"] = True
            debug_info["steps"].append(step_llm)
            action_effect = llm_result.get("action_effect") or ""
            precise_bbox = llm_result.get("bbox_xyxy")
            if precise_bbox and len(precise_bbox) == 4:
                bbox = [int(v) for v in precise_bbox]
            class_id = self._ensure_yolo_class(element_name)
            scene_id = scene_result.get("scene_id") if scene_result else None
            scene_key = scene_result.get("scene_key", "") if scene_result else ""
            element_id = dm.upsert_ui_element(
                scene_id=scene_id,
                scene_key=scene_key,
                element_type=llm_result.get("element_type") or "click_target",
                element_name=element_name,
                text=llm_result.get("text") or "",
                bbox_xyxy=bbox,
                source=llm_result.get("source") or "gpt-5.5",
                confidence=float(llm_result.get("confidence") or 0.6),
                fingerprint=fingerprint,
                image_path=crop_path,
                yolo_class_id=class_id,
                action_effect=action_effect,
            )
            result = {
                "status": "llm_labeled",
                "element_id": element_id,
                "element_name": element_name,
                "element_type": llm_result.get("element_type") or "click_target",
                "action_effect": action_effect,
                "bbox_xyxy": bbox,
                "crop_image": str(crop_path),
                "hash": fingerprint,
                "llm": llm_result,
            }
            if collect_debug:
                result["_debug"] = debug_info
            return result
        except Exception as e:
            LogManager().append(f"[WARN] analyze click target failed: {e}")
            result = {"status": "error", "error": str(e)}
            if collect_debug:
                result["_debug"] = debug_info
            return result

