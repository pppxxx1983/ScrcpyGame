from __future__ import annotations

import json
import re
from pathlib import Path






class LlmClickDescriptionMixin:
    def _describe_click_target_with_llm(
        self,
        image_path: Path,
        data: dict,
        scene_result: dict | None,
        fallback_crop_path: Path | None = None,
        fallback_bbox: list[int] | None = None,
    ) -> dict:
        try:
            from llm_client import QwenVLClient
            from PIL import Image

            scene_text = ""
            if scene_result:
                scene_text = scene_result.get("description") or scene_result.get("scene_key") or ""
            touch = data.get("touch", {}).get("frame_start", {})
            click_x = int(touch.get("x", 0))
            click_y = int(touch.get("y", 0))
            with Image.open(image_path) as img:
                width, height = img.size
            vision_width, vision_height = self._llm_vision_image_size(width, height)
            scale_x = width / max(1, vision_width)
            scale_y = height / max(1, vision_height)
            prompt = (
                "这是一张游戏截图。请根据用户点击点，精确找出被点击的 UI 元素完整边界。"
                "bbox_xyxy 必须使用原图像素坐标 [x1,y1,x2,y2]，要框住完整按钮/图标/可点击区域，"
                "不要只框点击点附近的小区域。"
                "只输出 JSON，不要解释："
                '{"element_name":"短名称","element_type":"button/icon/menu/item/unknown",'
                '"text":"图中可见文字，没有就空字符串","action_effect":"点击作用",'
                '"bbox_xyxy":[x1,y1,x2,y2],"confidence":0.0}'
                f"\n图像尺寸：{width}x{height}"
                f"\n用户点击点：({click_x},{click_y})"
                f"\n当前场景线索：{scene_text}"
            )
            raw = QwenVLClient().describe_image(image_path, prompt=prompt)
            parsed = {}
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(1))
            else:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
            if not isinstance(parsed, dict):
                parsed = {}
            bbox = parsed.get("bbox_xyxy") or parsed.get("bbox")
            if bbox and len(bbox) == 4:
                raw_x1, raw_y1, raw_x2, raw_y2 = [float(v) for v in bbox]
                x1 = int(round(raw_x1 * scale_x))
                y1 = int(round(raw_y1 * scale_y))
                x2 = int(round(raw_x2 * scale_x))
                y2 = int(round(raw_y2 * scale_y))
                parsed["bbox_xyxy_model"] = [raw_x1, raw_y1, raw_x2, raw_y2]
                parsed["bbox_xyxy"] = [
                    max(0, min(width - 1, x1)),
                    max(0, min(height - 1, y1)),
                    max(1, min(width, x2)),
                    max(1, min(height, y2)),
                ]
                if parsed["bbox_xyxy"][2] <= parsed["bbox_xyxy"][0] or parsed["bbox_xyxy"][3] <= parsed["bbox_xyxy"][1]:
                    parsed["bbox_xyxy"] = fallback_bbox or []
            elif fallback_bbox:
                parsed["bbox_xyxy"] = fallback_bbox
            parsed["parse_ok"] = bool(parsed)
            parsed["raw"] = raw[:500]
            parsed["source"] = "gpt-5.5"
            return parsed
        except Exception as e:
            if fallback_crop_path:
                try:
                    raw = QwenVLClient().describe_image(
                        fallback_crop_path,
                        prompt=(
                            "这是一张游戏截图中用户点击位置附近的局部裁剪图。"
                            "请判断被点击的图标/按钮是什么，以及点击它通常会产生什么作用。"
                            "只输出 JSON，不要解释："
                            '{"element_name":"短名称","element_type":"button/icon/menu/item/unknown",'
                            '"text":"图中可见文字，没有就空字符串","action_effect":"点击作用","confidence":0.0}'
                        ),
                    )
                    m = re.search(r"\{.*\}", raw, re.DOTALL)
                    parsed = json.loads(m.group(0)) if m else {}
                    parsed["bbox_xyxy"] = fallback_bbox or []
                    parsed["parse_ok"] = bool(parsed)
                    parsed["raw"] = raw[:500]
                    parsed["source"] = "gpt-5.5-crop-fallback"
                    return parsed
                except Exception:
                    pass
            return {
                "element_name": "tap_target",
                "element_type": "unknown",
                "action_effect": "",
                "bbox_xyxy": fallback_bbox or [],
                "confidence": 0.2,
                "source": "fallback",
                "error": str(e),
            }

