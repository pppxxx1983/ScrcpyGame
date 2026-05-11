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
from rl_optimizer import RLOptimizer, AdaptivePolicy


class DecisionEngine:
    """
    自动化决策引擎。

    使用示例:
        engine = DecisionEngine()
        result = engine.run_step(Path("screenshot.png"), goal="通过第一关")
        # result["scene_description"] -> 画面描述
        # result["decision"] -> {"action": "tap", "params": {...}, "reasoning": "..."}
    """

    def __init__(self, rl_path: Optional[Path] = None):
        self.vision = QwenVLClient()
        self.decision = DeepSeekClient()
        self.ocr = OCRClient()
        self.history: List[Dict[str, Any]] = []
        self.rl = RLOptimizer(rl_path or Path("game_agent_data/rl_policy.json"))
        self.adaptive = AdaptivePolicy(self.rl)
        self._last_state_action: Optional[Tuple[str, str]] = None

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
        candidate_actions: Optional[List[dict]] = None,
        state_key: str = "",
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
        # Adaptive re-ranking if candidates provided
        if candidate_actions and state_key:
            ranked = self.adaptive.rank_actions(state_key, candidate_actions)
            if ranked:
                best = ranked[0]
                result["action"] = best.get("action_type", "tap")
                result["params"] = {
                    "rx": best.get("x", 0.5) / 1000.0,
                    "ry": best.get("y", 0.5) / 1000.0,
                }
                result["reasoning"] = f"[Adaptive] {best.get('element_name','')} (rule confidence {best.get('confidence',0):.2f})"
                result["_adaptive_selected"] = best.get("rule_key") or best.get("element_name")
                self._last_state_action = (state_key, result["_adaptive_selected"])
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

    def feedback(self, success: bool, next_state_key: str = ""):
        """接收执行结果反馈，更新RL策略 (TODO #27)。"""
        if not self._last_state_action:
            return
        state_key, action_key = self._last_state_action
        reward = 1.0 if success else -1.0
        self.rl.update(state_key, action_key, reward, next_state_key or None)
        LogManager().append(
            f"[RL] update state={state_key} action={action_key} reward={reward}"
        )
        self._last_state_action = None

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
