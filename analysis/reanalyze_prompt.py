from __future__ import annotations

import re
from pathlib import Path






class ReanalyzePromptMixin:
    def _clean_llm_context_text(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        mojibake_marks = sum(text.count(mark) for mark in ["�", "锛", "绋", "鐧", "娓", "浣", "蹇", "鏍"])
        if mojibake_marks >= 2:
            return ""
        return text[:200]

    def _llm_vision_image_size(self, width: int, height: int) -> tuple[int, int]:
        max_edge = 1024
        if max(width, height) <= max_edge:
            return width, height
        ratio = max_edge / max(width, height)
        return int(width * ratio), int(height * ratio)

    def _build_reanalyze_prompt(self, image_path: Path, data: dict):
        """构建 Reanalyze prompt，返回 (prompt, width, height, vision_w, vision_h, scale_x, scale_y, click_x, click_y, scene_text)"""
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
        vision_width, vision_height = self._llm_vision_image_size(width, height)
        scale_x = width / max(1, vision_width)
        scale_y = height / max(1, vision_height)

        touch = data.get("touch", {}).get("frame_start", {})
        click_x = int(touch.get("x", 0))
        click_y = int(touch.get("y", 0))
        scene = data.get("scene_index", {}) if isinstance(data.get("scene_index"), dict) else {}
        scene_text = self._clean_llm_context_text(scene.get("description") or scene.get("scene_key") or "")
        prompt = (
            "You are a precise UI annotation engine for YOLO training. Analyze the attached game screenshot.\n"
            "Return ONLY valid JSON. Do not use markdown. Do not explain.\n"
            "Task A: Infer the player's intent for this operation. Based on the scene, the click point, and the UI "
            "state, determine what the player is trying to accomplish with this tap. Return this as user_intent "
            "(one concise Chinese sentence, max 30 chars).\n"
            "Task B: find the complete clickable UI element containing the click point. Put it FIRST in the objects "
            "array and set role to clicked_target.\n"
            "Task C: find the parent panel/dialog/card/container that contains the clicked target. Put it SECOND "
            "in the objects array and set role to clicked_target_panel. The panel box should cover the full visible "
            "panel rectangle, not the whole screen and not just the button.\n"
            "Task D: label the other visible, stable, automation-useful UI elements. Include buttons, text links, "
            "input boxes, checkboxes, tabs, close/back/confirm/cancel controls, and menu icons. Ignore background "
            "art, decoration, loading effects, and non-clickable illustrations.\n"
            "Use the coordinate system of the image sent to you for bbox_xyxy: [x1,y1,x2,y2]. Every box must cover the full "
            "clickable UI area, not a 100x100 patch around the click. Keep boxes tight but complete.\n"
            "Use short stable snake_case class_name values in English or pinyin. Limit to 30 objects.\n"
            "JSON schema: "
            '{"user_intent":"玩家想要登录游戏","objects":['
            '{"class_name":"sms_code_button","name":"get code",'
            '"bbox_xyxy":[x1,y1,x2,y2],"role":"clicked_target",'
            '"action_effect":"what tapping does","confidence":0.0},'
            '{"class_name":"login_panel","name":"login panel",'
            '"bbox_xyxy":[x1,y1,x2,y2],"role":"clicked_target_panel",'
            '"action_effect":"parent container","confidence":0.0}]}\n'
            f"Image size sent to you: {vision_width}x{vision_height}\n"
            f"The program will scale your bbox values back to the original screenshot size: {width}x{height}\n"
            f"User click point: ({click_x},{click_y})\n"
            f"Optional scene hint: {scene_text or 'none'}"
        )
        return prompt, width, height, vision_width, vision_height, scale_x, scale_y, click_x, click_y, scene_text

    def _fix_json_text(text: str) -> str:
        """修复模型返回的常见 JSON 格式错误（如 bbox_xyxy 漏掉方括号）。"""
        # 修复 "bbox_xyxy":x1,y1,x2,y2 为 "bbox_xyxy":[x1,y1,x2,y2]
        text = re.sub(
            r'"bbox_xyxy"\s*:\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)',
            r'"bbox_xyxy":[\1,\2,\3,\4]',
            text,
        )
        # 修复 "bbox":x1,y1,x2,y2 为 "bbox":[x1,y1,x2,y2]
        text = re.sub(
            r'"bbox"\s*:\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)',
            r'"bbox":[\1,\2,\3,\4]',
            text,
        )
        return text

