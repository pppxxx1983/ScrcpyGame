"""
游戏决策引擎
- 感知: qwen-vl-max 解读当前画面
- 决策: deepseek 根据画面描述 + 历史记录做出下一步操作决策
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from llm_client import QwenVLClient, DeepSeekClient
from ocr_client import OCRClient
from log_manager import LogManager


class DecisionEngine:
    """
    自动化决策引擎。

    使用示例:
        engine = DecisionEngine()
        result = engine.run_step(Path("screenshot.png"), goal="通过第一关")
        # result["scene_description"] -> 画面描述
        # result["decision"] -> {"action": "tap", "params": {...}, "reasoning": "..."}
    """

    def __init__(self):
        self.vision = QwenVLClient()
        self.decision = DeepSeekClient()
        self.ocr = OCRClient()
        self.history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 感知层 (Vision)
    # ------------------------------------------------------------------
    def perceive(self, screenshot_path: Path) -> str:
        """用视觉模型解读当前画面，返回一句中文描述。"""
        description = self.vision.describe_image(screenshot_path)
        return description

    # ------------------------------------------------------------------
    # 决策层 (Decision)
    # ------------------------------------------------------------------
    def perceive_ocr(self, screenshot_path: Path) -> str:
        """用本地 OCR 识别屏幕文字，返回排序后的纯文本。"""
        text = self.ocr.to_text(image_path=screenshot_path)
        lines = text.split("\n") if text else []
        LogManager().append(f"[OCR] 识别到 {len(lines)} 行文字")
        return text

    def think(
        self,
        scene_description: str,
        goal: str = "",
        available_actions: Optional[List[str]] = None,
        ocr_text: str = "",
    ) -> Dict[str, Any]:
        """
        用 DeepSeek 决定下一步操作。

        返回结构化决策:
        {
            "action": "tap" | "swipe" | "scroll" | "wait" | "none",
            "params": {"x": 100, "y": 200, ...},
            "reasoning": "为什么这么做"
        }
        """
        available_actions = available_actions or [
            "tap", "swipe", "scroll", "wait"
        ]

        system_prompt = (
            "你是一位游戏自动化专家。请根据当前画面描述和历史操作，"
            "决定下一步操作。\n\n"
            "坐标使用比例值 (0.0 ~ 1.0)，其中 (0.0, 0.0) 是左上角，"
            "(1.0, 1.0) 是右下角。\n\n"
            "你必须严格按以下 JSON 格式输出，不要包含任何其他内容:\n\n"
            '{\n'
            '  "action": "tap",\n'
            '  "params": {"rx": 0.5, "ry": 0.8},\n'
            '  "reasoning": "点击屏幕中央偏下的开始按钮"\n'
            '}\n\n'
            "action 可选值: tap(点击)、swipe(滑动)、scroll(滚轮)、wait(等待)。\n"
            "params 根据 action 填写:\n"
            "- tap: {\"rx\": float(0~1), \"ry\": float(0~1)}\n"
            "- swipe: {\"rx1\": float, \"ry1\": float, \"rx2\": float, \"ry2\": float, "
            "\"duration_ms\": int}\n"
            "- scroll: {\"rx\": float, \"ry\": float, \"rdx\": float, \"rdy\": float}\n"
            "- wait: {\"duration_ms\": int}\n"
        )

        history_text = ""
        if self.history:
            recent = self.history[-5:]
            lines = []
            for h in recent:
                ts = h.get("time", "")
                act = h.get("action", "")
                reason = h.get("reasoning", "")[:60]
                lines.append(f"- [{ts}] {act} | {reason}")
            history_text = "\n".join(lines)

        ocr_section = ""
        if ocr_text:
            ocr_section = (
                f"屏幕上识别到的文字（OCR）:\n{ocr_text}\n\n"
            )

        user_prompt = (
            f"当前画面描述: {scene_description}\n\n"
            f"{ocr_section}"
            f"可用操作类型: {', '.join(available_actions)}\n\n"
            f"最近操作历史:\n{history_text or '无'}\n\n"
            f"{'当前目标: ' + goal + chr(10) if goal else ''}"
            "请输出 JSON 格式的决策:"
        )

        result = self.decision.decide(system_prompt, user_prompt)
        LogManager().append(
            f"[Decision] {result.get('action')} | "
            f"{result.get('reasoning', '')[:120]}"
        )
        return result

    # ------------------------------------------------------------------
    # 执行记录
    # ------------------------------------------------------------------
    def act(self, decision: Dict[str, Any]) -> None:
        """记录一次决策到历史。"""
        self.history.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": decision.get("action"),
            "params": decision.get("params"),
            "reasoning": decision.get("reasoning"),
        })
        # 只保留最近 50 条
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def clear_history(self) -> None:
        """清空历史决策记录。"""
        self.history.clear()

    # ------------------------------------------------------------------
    # 端到端单步
    # ------------------------------------------------------------------
    def run_step(
        self,
        screenshot_path: Path,
        goal: str = "",
    ) -> Dict[str, Any]:
        """完整执行一步: 感知(qwen) + OCR -> 决策 -> 记录"""
        description = self.perceive(screenshot_path)
        ocr_text = self.perceive_ocr(screenshot_path)
        decision = self.think(description, goal=goal, ocr_text=ocr_text)
        self.act(decision)
        return {
            "scene_description": description,
            "ocr_text": ocr_text,
            "decision": decision,
        }
