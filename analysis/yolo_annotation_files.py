from __future__ import annotations

import shutil
from pathlib import Path
from datetime import datetime


from log_manager import LogManager




class YoloAnnotationFilesMixin:
    def _write_yolo_event_annotation(self, op_dir: Path, data: dict) -> dict:
        try:
            import shutil
            from PIL import Image
            from agent_data import GAME_DATA_DIR

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"error": "before image missing"}
            image_path = op_dir / before_name
            if not image_path.exists():
                return {"error": f"image not found: {image_path}"}

            with Image.open(image_path) as img:
                width, height = img.size

            touch = data.get("touch", {})
            start = touch.get("frame_start", {})
            end = touch.get("frame_end", start)
            sx, sy = int(start.get("x", 0)), int(start.get("y", 0))
            ex, ey = int(end.get("x", sx)), int(end.get("y", sy))

            click_target = data.get("click_target", {})
            if click_target.get("status") == "needs_model_or_manual":
                return {
                    "status": "waiting_for_label",
                    "reason": click_target.get("reason", "click target is not identified"),
                }
            target_bbox = click_target.get("bbox_xyxy")
            if target_bbox and len(target_bbox) == 4:
                x1, y1, x2, y2 = [int(v) for v in target_bbox]
            else:
                action_type = data.get("action_type", "")
                if "swipe" in action_type:
                    pad = max(48, int(min(width, height) * 0.05))
                    x1, x2 = sorted((sx, ex))
                    y1, y2 = sorted((sy, ey))
                    x1 -= pad
                    y1 -= pad
                    x2 += pad
                    y2 += pad
                else:
                    box_size = max(64, min(128, int(min(width, height) * 0.09)))
                    half = box_size // 2
                    x1, y1 = sx - half, sy - half
                    x2, y2 = sx + half, sy + half

            class_name = click_target.get("element_name") or "tap_target"
            objects = [{
                "class_name": class_name,
                "bbox_xyxy": [x1, y1, x2, y2],
                "source": click_target.get("status", "click_target"),
                "role": "clicked_target",
            }]
            for obj in data.get("gpt_yolo_objects", {}).get("objects", []):
                name = obj.get("class_name") or obj.get("name")
                bbox = obj.get("bbox_xyxy")
                if not name or not bbox or len(bbox) != 4:
                    continue
                objects.append({
                    "class_name": name,
                    "bbox_xyxy": bbox,
                    "source": "gpt-5.5",
                    "role": obj.get("role", "ui_element"),
                })
            for obj in data.get("yolo_detected_objects", {}).get("objects", []):
                name = obj.get("class_name") or obj.get("name")
                bbox = obj.get("bbox_xyxy")
                if not name or not bbox or len(bbox) != 4:
                    continue
                objects.append({
                    "class_name": name,
                    "bbox_xyxy": bbox,
                    "source": "trained_yolo",
                    "role": obj.get("role", "ui_element"),
                })

            label_lines = []
            normalized_objects = []
            seen = set()
            for obj in objects:
                bx1, by1, bx2, by2 = [int(v) for v in obj["bbox_xyxy"]]
                bx1 = max(0, min(width - 1, bx1))
                by1 = max(0, min(height - 1, by1))
                bx2 = max(bx1 + 1, min(width, bx2))
                by2 = max(by1 + 1, min(height, by2))
                key = (obj["class_name"], bx1 // 8, by1 // 8, bx2 // 8, by2 // 8)
                if key in seen:
                    continue
                seen.add(key)
                class_id = self._ensure_yolo_class(obj["class_name"])
                x_center = ((bx1 + bx2) / 2) / width
                y_center = ((by1 + by2) / 2) / height
                box_w = (bx2 - bx1) / width
                box_h = (by2 - by1) / height
                label_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}")
                normalized_objects.append({
                    "class_id": class_id,
                    "class_name": obj["class_name"],
                    "bbox_xyxy": [int(bx1), int(by1), int(bx2), int(by2)],
                    "source": obj.get("source", ""),
                    "role": obj.get("role", ""),
                })
            label_text = "\n".join(label_lines) + "\n"

            event_key = op_dir.name
            local_yolo_dir = op_dir / "yolo"
            local_images = local_yolo_dir / "images"
            local_labels = local_yolo_dir / "labels"
            local_images.mkdir(parents=True, exist_ok=True)
            local_labels.mkdir(parents=True, exist_ok=True)
            local_image = local_images / f"{event_key}.png"
            local_label = local_labels / f"{event_key}.txt"
            shutil.copy2(str(image_path), str(local_image))
            local_label.write_text(label_text, encoding="utf-8")
            classes_text = self._yolo_classes_text()
            (local_yolo_dir / "classes.txt").write_text(classes_text, encoding="utf-8")

            return {
                "status": "candidate",
                "review_state": "pending",
                "class_id": normalized_objects[0]["class_id"] if normalized_objects else 0,
                "class_name": normalized_objects[0]["class_name"] if normalized_objects else class_name,
                "image_width": width,
                "image_height": height,
                "bbox_xyxy": normalized_objects[0]["bbox_xyxy"] if normalized_objects else [int(x1), int(y1), int(x2), int(y2)],
                "objects": normalized_objects,
                "label": label_text.strip(),
                "local_image": str(local_image),
                "local_label": str(local_label),
            }
        except Exception as e:
            LogManager().append(f"[WARN] write yolo annotation failed: {e}")
            return {"error": str(e)}

    def _promote_yolo_event_annotation(self, op_dir: Path, data: dict) -> dict:
        try:
            import shutil
            from datetime import datetime
            from agent_data import GAME_DATA_DIR

            yolo = data.get("yolo") if isinstance(data.get("yolo"), dict) else {}
            local_image_value = yolo.get("local_image") or ""
            local_label_value = yolo.get("local_label") or ""
            local_image = Path(local_image_value) if local_image_value else None
            local_label = Path(local_label_value) if local_label_value else None
            if local_image is None or local_label is None or not local_image.exists() or not local_label.exists():
                yolo = self._write_yolo_event_annotation(op_dir, data)
                local_image_value = yolo.get("local_image") or ""
                local_label_value = yolo.get("local_label") or ""
                local_image = Path(local_image_value) if local_image_value else None
                local_label = Path(local_label_value) if local_label_value else None
            if local_image is None or local_label is None or not local_image.exists() or not local_label.exists():
                return {"status": "error", "error": "local yolo candidate missing"}

            event_key = op_dir.name
            dataset_images = GAME_DATA_DIR / "yolo_events" / "images" / "train"
            dataset_labels = GAME_DATA_DIR / "yolo_events" / "labels" / "train"
            dataset_images.mkdir(parents=True, exist_ok=True)
            dataset_labels.mkdir(parents=True, exist_ok=True)

            dataset_image = dataset_images / f"{event_key}{local_image.suffix or '.png'}"
            dataset_label = dataset_labels / f"{event_key}.txt"
            shutil.copy2(str(local_image), str(dataset_image))
            shutil.copy2(str(local_label), str(dataset_label))
            (GAME_DATA_DIR / "yolo_events" / "classes.txt").write_text(
                self._yolo_classes_text(),
                encoding="utf-8",
            )
            (GAME_DATA_DIR / "yolo_events" / "data.yaml").write_text(
                self._yolo_data_yaml(),
                encoding="utf-8",
            )

            promoted = dict(yolo)
            promoted.update({
                "status": "approved",
                "review_state": "approved",
                "approved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "dataset_image": str(dataset_image),
                "dataset_label": str(dataset_label),
            })
            return promoted
        except Exception as e:
            LogManager().append(f"[WARN] promote yolo annotation failed: {e}")
            return {"status": "error", "error": str(e)}

    def _yolo_objects_from_event(self, data: dict) -> list[dict]:
        yolo = data.get("yolo", {}) if isinstance(data.get("yolo"), dict) else {}
        objects = []
        for obj in yolo.get("objects") or []:
            if obj.get("bbox_xyxy"):
                objects.append(dict(obj))
        if not objects and yolo.get("bbox_xyxy"):
            objects.append({
                "class_name": yolo.get("class_name") or "tap_target",
                "bbox_xyxy": yolo.get("bbox_xyxy"),
                "role": "clicked_target",
                "source": yolo.get("status") or "yolo",
            })
        return objects

