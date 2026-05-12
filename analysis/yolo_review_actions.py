from __future__ import annotations

import json
import shutil
import time
from pathlib import Path


from log_manager import LogManager
from scene_index import SceneIndex




class YoloReviewActionsMixin:
    def _approve_physical_event(self, folder: Path):
        index_path = folder / "index.json"
        if not index_path.exists():
            self._set_status(f"YOLO review: index not found {folder.name}")
            return
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            promoted = self._promote_yolo_event_annotation(folder, data)
            if promoted.get("status") == "error":
                self._set_status(f"YOLO review: approve failed - {promoted.get('error')}")
                return

            data["yolo"] = promoted
            data["status"] = "review_approved"
            index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            try:
                from agent_data import AgentDataManager

                AgentDataManager().record_physical_event(
                    event_key=folder.name,
                    action_type=data.get("action_type", ""),
                    timestamp_ms=int(time.time() * 1000),
                    duration_ms=int(data.get("duration_ms") or 0),
                    touch=data.get("touch", {}),
                    folder_path=folder,
                    images=data.get("images", {}),
                    index_path=index_path,
                    yolo=promoted,
                )
            except Exception as e:
                LogManager().append(f"[WARN] update approved physical event db failed: {e}")

            self._set_status(f"YOLO review: approved {folder.name}, training started")
            self._bridge.events_changed.emit()
            self._open_physical_event_tab(folder)
            self._start_yolo_training_async()
        except Exception as e:
            self._set_status(f"YOLO review: approve failed - {e}")

    def _save_yolo_review(self, folder: Path, data: dict, image_path: Path, objects: list[dict], approved: bool = False) -> str:
        try:
            import shutil
            from PIL import Image
            from agent_data import GAME_DATA_DIR, AgentDataManager

            with Image.open(image_path) as img:
                width, height = img.size

            normalized = []
            review_objects = []
            label_lines = []
            for obj in objects:
                bbox = obj.get("bbox_xyxy") or []
                if len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                x1 = max(0, min(width - 1, x1))
                y1 = max(0, min(height - 1, y1))
                x2 = max(x1 + 1, min(width, x2))
                y2 = max(y1 + 1, min(height, y2))
                class_name = self._safe_yolo_class_name(obj.get("class_name") or "ui_element")
                class_id = self._ensure_yolo_class(class_name)
                clean = dict(obj)
                clean.update({
                    "class_id": class_id,
                    "class_name": class_name,
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "review_status": "approved" if clean.get("review_approved") else "candidate",
                })
                review_objects.append(clean)
                if clean.get("review_approved", False):
                    label_lines.append(
                        f"{class_id} {((x1 + x2) / 2) / width:.6f} {((y1 + y2) / 2) / height:.6f} "
                        f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}"
                    )
                    normalized.append(clean)

            event_key = folder.name
            label_text = "\n".join(label_lines) + ("\n" if label_lines else "")
            local_yolo_dir = folder / "yolo"
            local_images = local_yolo_dir / "images"
            local_labels = local_yolo_dir / "labels"
            local_images.mkdir(parents=True, exist_ok=True)
            local_labels.mkdir(parents=True, exist_ok=True)
            local_image = local_images / f"{event_key}.png"
            local_label = local_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(local_image))
            local_label.write_text(label_text, encoding="utf-8")
            (local_yolo_dir / "classes.txt").write_text(self._yolo_classes_text(), encoding="utf-8")

            dataset_images = GAME_DATA_DIR / "yolo_events" / "images" / "train"
            dataset_labels = GAME_DATA_DIR / "yolo_events" / "labels" / "train"
            dataset_images.mkdir(parents=True, exist_ok=True)
            dataset_labels.mkdir(parents=True, exist_ok=True)
            dataset_image = dataset_images / f"{event_key}.png"
            dataset_label = dataset_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(dataset_image))
            dataset_label.write_text(label_text, encoding="utf-8")
            (GAME_DATA_DIR / "yolo_events" / "classes.txt").write_text(self._yolo_classes_text(), encoding="utf-8")
            (GAME_DATA_DIR / "yolo_events" / "data.yaml").write_text(self._yolo_data_yaml(), encoding="utf-8")

            data["yolo"] = {
                "status": "review_approved" if approved else "review_edited",
                "image_width": width,
                "image_height": height,
                "objects": review_objects,
                "approved_objects": normalized,
                "bbox_xyxy": normalized[0]["bbox_xyxy"] if normalized else None,
                "class_name": normalized[0]["class_name"] if normalized else "ui_element",
                "label": label_text.strip(),
                "local_image": str(local_image),
                "local_label": str(local_label),
                "dataset_image": str(dataset_image),
                "dataset_label": str(dataset_label),
            }
            data["status"] = "review_approved" if approved else "review_pending"
            data["review"] = {
                "type": "yolo_event",
                "approved": bool(approved),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            index_path = folder / "index.json"
            index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            AgentDataManager().record_physical_event(
                event_key=folder.name,
                action_type=data.get("action_type", ""),
                timestamp_ms=int(time.time() * 1000),
                duration_ms=int(data.get("duration_ms") or 0),
                touch=data.get("touch", {}),
                folder_path=folder,
                images=data.get("images", {}),
                index_path=index_path,
                yolo=data.get("yolo"),
            )

            # 审核通过时，将场景注册到 SceneIndex hash 库，提升后续识别速度
            if approved:
                try:
                    scene_idx = SceneIndex()
                    scene_name = folder.name
                    scene_desc = ""
                    si = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
                    scene_desc = si.get("description") or si.get("scene_key") or ""
                    user_intent = data.get("gpt_user_intent", "")
                    description = " | ".join(filter(None, [scene_desc, user_intent])) or scene_name
                    reg_result = scene_idx.register_from_review(
                        image_path=image_path,
                        scene_name=scene_name,
                        description=description,
                        threshold=0.96,
                    )
                    if reg_result.get("registered"):
                        data["scene_index"] = {
                            "matched": True,
                            "confidence": reg_result.get("confidence", 1.0),
                            "scene_id": reg_result.get("scene_id"),
                            "scene_key": reg_result.get("scene_key") or scene_name,
                            "description": description,
                        }
                    if reg_result.get("registered"):
                        if reg_result.get("existed"):
                            LogManager().append(
                                f"[SceneIndex] Review-approved scene '{scene_name}' already in index "
                                f"(confidence={reg_result['confidence']:.3f}), hit +1"
                            )
                        else:
                            LogManager().append(
                                f"[SceneIndex] Review-approved scene '{scene_name}' registered as new entry "
                                f"(id={reg_result['scene_id']})"
                            )
                except Exception as reg_err:
                    LogManager().append(f"[SceneIndex] Failed to register review scene: {reg_err}")

                data["runtime_index"] = self._compile_runtime_index_from_review(
                    folder=folder,
                    data=data,
                    image_path=image_path,
                    approved_objects=normalized,
                    source="human_review",
                )
                index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                self._bridge.overlay_changed.emit({
                    "scene": data.get("scene_index", {}).get("scene_key", "") if isinstance(data.get("scene_index"), dict) else "",
                    "rule": "",
                    "status": f"索引 E{data['runtime_index'].get('elements', 0)} R{data['runtime_index'].get('rules', 0)}",
                })

            runtime = data.get("runtime_index", {}) if isinstance(data.get("runtime_index"), dict) else {}
            runtime_text = ""
            if runtime:
                runtime_text = f", runtime=E{runtime.get('elements', 0)}/R{runtime.get('rules', 0)}"
            return f"YOLO audit saved: {len(normalized)} boxes, status={data['status']}{runtime_text}"
        except Exception as e:
            LogManager().append(f"[Audit] YOLO save failed: {e}")
            return f"YOLO audit save failed: {e}"

