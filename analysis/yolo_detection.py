from __future__ import annotations

from pathlib import Path


from log_manager import LogManager




class YoloDetectionMixin:
    def _detect_yolo_objects(self, op_dir: Path, data: dict) -> dict:
        try:
            from agent_data import GAME_DATA_DIR
            from ultralytics import YOLO

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"status": "no_before_image", "objects": []}
            before_path = op_dir / before_name
            if not before_path.exists():
                return {"status": "before_image_missing", "objects": []}

            model_path = GAME_DATA_DIR / "yolo_events" / "runs" / "train" / "weights" / "best.pt"
            if not model_path.exists():
                return {"status": "no_model", "objects": []}

            model = YOLO(str(model_path))
            results = model.predict(str(before_path), conf=0.25, verbose=False)
            objects = []
            for result in results:
                names = getattr(result, "names", {}) or {}
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    xyxy = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0].item()) if box.cls is not None else 0
                    conf = float(box.conf[0].item()) if box.conf is not None else 0.0
                    objects.append({
                        "class_id": cls_id,
                        "class_name": str(names.get(cls_id, f"class_{cls_id}")),
                        "bbox_xyxy": [int(v) for v in xyxy],
                        "confidence": round(conf, 4),
                        "source": "yolo",
                    })
            return {"status": "ok", "model": str(model_path), "objects": objects}
        except ImportError:
            return {"status": "ultralytics_missing", "objects": []}
        except Exception as e:
            LogManager().append(f"[WARN] yolo detect failed: {e}")
            return {"status": "error", "objects": [], "error": str(e)}

    def _yolo_object_at_touch(self, data: dict, pad: int = 8) -> dict | None:
        touch = data.get("touch", {})
        start = touch.get("frame_start", {})
        try:
            x = int(start.get("x", 0))
            y = int(start.get("y", 0))
        except Exception:
            return None

        best = None
        for obj in data.get("detected_yolo_objects", {}).get("objects", []):
            bbox = obj.get("bbox_xyxy")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            if x1 - pad <= x <= x2 + pad and y1 - pad <= y <= y2 + pad:
                area = max(1, (x2 - x1) * (y2 - y1))
                score = float(obj.get("confidence") or 0.0)
                rank = (score, -area)
                if best is None or rank > best[0]:
                    best = (rank, obj)
        return best[1] if best else None

    def _detect_yolo_click_target(self, image_path: Path, data: dict) -> dict | None:
        try:
            from agent_data import GAME_DATA_DIR

            weights_dir = GAME_DATA_DIR / "yolo_events" / "runs" / "detect" / "train" / "weights"
            model_path = weights_dir / "best.pt"
            if not model_path.exists():
                model_path = weights_dir / "last.pt"
            if not model_path.exists():
                return None
            try:
                from ultralytics import YOLO
            except Exception:
                return None

            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            model = YOLO(str(model_path))
            results = model.predict(str(image_path), conf=0.25, verbose=False)
            if not results:
                return None
            names = getattr(results[0], "names", {}) or {}
            objects = []
            best = None
            boxes = getattr(results[0], "boxes", None)
            if boxes is None:
                return None
            for box in boxes:
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = [int(v) for v in xyxy]
                conf = float(box.conf[0]) if getattr(box, "conf", None) is not None else 0.0
                class_id = int(box.cls[0]) if getattr(box, "cls", None) is not None else 0
                class_name = str(names.get(class_id, f"class_{class_id}"))
                obj = {
                    "class_id": class_id,
                    "class_name": class_name,
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "confidence": conf,
                    "source": "trained_yolo",
                }
                objects.append(obj)
                if x1 <= click_x <= x2 and y1 <= click_y <= y2:
                    area = max(1, (x2 - x1) * (y2 - y1))
                    score = conf / area
                    if best is None or score > best[0]:
                        best = (score, obj)
            if not best:
                return None
            obj = best[1]
            return {
                "status": "yolo_matched",
                "element_name": obj["class_name"],
                "element_type": "ui_element",
                "action_effect": "",
                "bbox_xyxy": obj["bbox_xyxy"],
                "confidence": obj["confidence"],
                "model_path": str(model_path),
                "objects": objects,
            }
        except Exception as e:
            LogManager().append(f"[YOLO] click detect failed: {e}")
            return None

