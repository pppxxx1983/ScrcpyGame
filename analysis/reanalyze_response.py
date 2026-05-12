from __future__ import annotations

import json
import re


from log_manager import LogManager




class ReanalyzeResponseMixin:
    def _process_reanalyze_response(
        self, raw: str, width: int, height: int, scale_x: float, scale_y: float, click_x: int, click_y: int
    ) -> tuple[list[dict], str]:
        """解析 Reanalyze 的 raw response，返回 (objects, user_intent)"""
        parsed: dict = {}
        user_intent = ""
        try:
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                json_text = self._fix_json_text(m.group(1))
                parsed = json.loads(json_text)
            else:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    json_text = self._fix_json_text(m.group(0))
                    parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                user_intent = str(parsed.get("user_intent") or "").strip()
        except Exception as parse_err:
            LogManager().append(f"[Reanalyze] JSON parse warning: {parse_err}")
        objects = []
        for obj in parsed.get("objects", []) if isinstance(parsed, dict) else []:
            bbox = obj.get("bbox_xyxy") or obj.get("bbox")
            name = obj.get("class_name") or obj.get("name")
            if not name or not bbox or len(bbox) != 4:
                continue
            raw_x1, raw_y1, raw_x2, raw_y2 = [float(v) for v in bbox]
            x1 = int(round(raw_x1 * scale_x))
            y1 = int(round(raw_y1 * scale_y))
            x2 = int(round(raw_x2 * scale_x))
            y2 = int(round(raw_y2 * scale_y))
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(x1 + 1, min(width, x2))
            y2 = max(y1 + 1, min(height, y2))
            objects.append({
                "class_name": self._safe_yolo_class_name(name),
                "name": obj.get("name", ""),
                "bbox_xyxy_model": [raw_x1, raw_y1, raw_x2, raw_y2],
                "bbox_xyxy": [x1, y1, x2, y2],
                "role": obj.get("role", "ui_element"),
                "action_effect": obj.get("action_effect", ""),
                "confidence": float(obj.get("confidence") or 0.5),
                "modified": False,
            })

        def click_contains(item):
            x1, y1, x2, y2 = item["bbox_xyxy"]
            return x1 <= click_x <= x2 and y1 <= click_y <= y2

        def object_area(item):
            x1, y1, x2, y2 = item["bbox_xyxy"]
            return max(1, (x2 - x1) * (y2 - y1))

        target_candidates = [
            item for item in objects
            if click_contains(item) and str(item.get("role", "")) != "clicked_target_panel"
        ]
        panel_candidates = [
            item for item in objects
            if click_contains(item) and str(item.get("role", "")) == "clicked_target_panel"
        ]
        if target_candidates:
            target = min(target_candidates, key=object_area)
            target["role"] = "clicked_target"
        if not panel_candidates:
            larger = [
                item for item in objects
                if click_contains(item) and item is not (target_candidates[0] if target_candidates else None)
                and object_area(item) >= (object_area(target_candidates[0]) * 2 if target_candidates else 1)
            ]
            if larger:
                panel = max(larger, key=object_area)
                panel["role"] = "clicked_target_panel"
                panel["class_name"] = panel.get("class_name") or "clicked_panel"

        def sort_key(item):
            role = str(item.get("role", ""))
            if role == "clicked_target":
                return (0, object_area(item))
            if role == "clicked_target_panel":
                return (1, -object_area(item))
            return (2, -float(item.get("confidence") or 0))

        objects.sort(key=sort_key)
        return objects, user_intent

