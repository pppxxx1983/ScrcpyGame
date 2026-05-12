from __future__ import annotations

import json
import re
from pathlib import Path


from log_manager import LogManager




class GptYoloAnnotationMixin:
    def _analyze_yolo_objects_with_gpt55(self, op_dir: Path, data: dict, scene_result: dict | None) -> dict:
        try:
            from llm_client import QwenVLClient
            from PIL import Image

            before_name = data.get("images", {}).get("before")
            if not before_name:
                return {"status": "no_before_image", "objects": []}
            before_path = op_dir / before_name
            if not before_path.exists():
                return {"status": "before_image_missing", "objects": []}

            with Image.open(before_path) as img:
                width, height = img.size

            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            scene_text = ""
            if scene_result:
                scene_text = scene_result.get("description") or scene_result.get("scene_key") or ""
            prompt = (
                "你是游戏 UI 的 YOLO 标注助手。请分析整张截图，尽量多标注可点击、可识别、对自动化有用的 UI 元素。"
                "必须重点标注用户点击点所在的图标/按钮，也要标注周围其它按钮、图标、菜单、卡片、文字按钮、关闭按钮、开始按钮、奖励入口等。"
                "不要标注背景、纯装饰、无法稳定复现的光效。bbox 用原图像素坐标，不要用归一化坐标。"
                "元素名要短，适合作为 YOLO class，例如 start_button、close_button、plant_card、shop_icon。"
                "只输出 JSON，不要解释："
                '{"objects":[{"class_name":"英文或拼音短类名","name":"中文名","bbox_xyxy":[x1,y1,x2,y2],'
                '"role":"clicked_target/ui_element","action_effect":"点击作用","confidence":0.0}]}'
                f"\n图像尺寸：{width}x{height}"
                f"\n用户点击点：({click_x},{click_y})"
                f"\n当前场景线索：{scene_text}"
            )
            raw = QwenVLClient(model="openai/gpt-5.5").describe_image(before_path, prompt=prompt, timeout=180)
            parsed = {}
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(1))
            else:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
            user_intent = ""
            if isinstance(parsed, dict):
                user_intent = str(parsed.get("user_intent") or "").strip()
                if user_intent:
                    LogManager().append(f"[GPT-5.5 Reanalyze] user_intent: {user_intent}")
                    data["gpt_user_intent"] = user_intent
            objects = []
            for obj in parsed.get("objects", []) if isinstance(parsed, dict) else []:
                bbox = obj.get("bbox_xyxy") or obj.get("bbox")
                name = obj.get("class_name") or obj.get("name")
                if not name or not bbox or len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                x1 = max(0, min(width - 1, x1))
                y1 = max(0, min(height - 1, y1))
                x2 = max(x1 + 1, min(width, x2))
                y2 = max(y1 + 1, min(height, y2))
                safe_name = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(name)).strip("_")[:32]
                objects.append({
                    "class_name": safe_name or "ui_element",
                    "name": obj.get("name", ""),
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "role": obj.get("role", "ui_element"),
                    "action_effect": obj.get("action_effect", ""),
                    "confidence": obj.get("confidence", 0.5),
                })
            LogManager().append(f"[EventUnknown] gpt-5.5 YOLO 标注候选 {op_dir.name}: {len(objects)}")
            return {
                "status": "ok" if objects else "empty",
                "model": "openai/gpt-5.5",
                "objects": objects,
                "raw": raw[:800],
            }
        except Exception as e:
            LogManager().append(f"[WARN] gpt yolo objects failed: {e}")
            return {"status": "error", "objects": [], "error": str(e)}

