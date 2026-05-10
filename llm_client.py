"""
大模型统一客户端
- QwenVLClient: ofox.ai 视觉模型（gpt-5.5 / gpt-4o fallback）
- DeepSeekClient: DeepSeek API，负责决策

API Key 优先级:
1. 初始化时显式传入
2. 环境变量 OFOX_API_KEY / DEEPSEEK_API_KEY
"""

import os
import base64
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional

from openai import OpenAI, APIError


class QwenVLClient:
    """视觉模型客户端（默认通过 ofox.ai 调用 gpt-5.5，失败自动 fallback 到 gpt-4o）"""

    DEFAULT_URL = "https://api.ofox.ai/v1"
    FALLBACK_MODELS = ["openai/gpt-5.5", "openai/gpt-4o"]

    def __init__(self, api_key: Optional[str] = None, model: str = "openai/gpt-5.5"):
        self.api_key = api_key or os.environ.get(
            "OFOX_API_KEY", "sk-of-HfjuJzJMwyPhzpzTAygdsciwFbhnEcZFnrVOGdYcdQZppuNvpMsAFQMmzHnyzohL"
        )
        self.model = model
        self.base_url = self.DEFAULT_URL
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def is_ready(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _prepare_image(image_path: Path) -> str:
        """压缩图片并返回 base64 JPEG。"""
        from PIL import Image
        import io

        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            max_edge = 1024
            if max(img.width, img.height) > max_edge:
                ratio = max_edge / max(img.width, img.height)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return base64.b64encode(buf.getvalue()).decode("ascii")

    def _call_vision_api(
        self,
        model: str,
        image_b64: str,
        prompt: str,
        max_tokens: int,
        timeout: int,
    ) -> str:
        """发起视觉 API 请求，返回原始文本。失败则抛出异常。"""
        response = self._get_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            stream=False,
            temperature=0,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return (response.choices[0].message.content or "").strip()

    def describe_image(
        self,
        image_path: Path,
        prompt: Optional[str] = None,
        timeout: int = 180,
    ) -> str:
        """输入图片路径，返回画面描述（一句中文）。失败自动 fallback。"""
        from log_manager import LogManager

        log = LogManager()
        t0 = time.time()

        if not self.api_key:
            return "[qwen_vl_error] API key not configured"

        image_path = Path(image_path)
        if not image_path.exists():
            return "[qwen_vl_error] Image not found"

        image_b64 = self._prepare_image(image_path)
        prompt = prompt or (
            "请判断这张游戏截图的关键画面状态，用一句中文描述。"
            "不要写推理过程，不要超过60字。"
        )

        models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        last_err = ""
        for model in models:
            log.append(f"[LLM] >>> describe_image TRY | model={model} | file={image_path}")
            try:
                content = self._call_vision_api(model, image_b64, prompt, 120, timeout)
                cost = (time.time() - t0) * 1000
                log.append(
                    f"[LLM] <<< describe_image OK | model={model} | cost={cost:.1f}ms | len={len(content)}"
                )
                log.append(f"[LLM] RAW: {content[:500]}")
                return content
            except Exception as e:
                last_err = str(e)
                log.append(f"[LLM] describe_image FAIL model={model} | {e}")

        cost = (time.time() - t0) * 1000
        err = f"[qwen_vl_error] {last_err}"
        log.append(f"[LLM] <<< describe_image ALL_FAILED | cost={cost:.1f}ms | {err}")
        return err

    def analyze_scene(
        self,
        image_path: Path,
        timeout: int = 180,
    ) -> dict:
        """
        一次性分析场景：OCR + 场景描述 + 对象检测。失败自动 fallback。
        返回: {
            "scene_description": str,
            "ocr_text": [str, ...],
            "objects": [{"name": str, "bbox": [x1,y1,x2,y2]}, ...]
        }
        """
        from log_manager import LogManager

        log = LogManager()
        t0 = time.time()

        if not self.api_key:
            return {
                "scene_description": "[qwen_vl_error] API key not configured",
                "ocr_text": [],
                "objects": [],
            }

        image_path = Path(image_path)
        if not image_path.exists():
            return {"scene_description": "", "ocr_text": [], "objects": []}

        image_b64 = self._prepare_image(image_path)
        prompt = (
            "请分析这张游戏截图，输出以下三部分内容，严格按 JSON 格式：\n"
            "{\n"
            '  "scene_description": "用一句中文描述当前是什么界面/场景",\n'
            '  "ocr_text": ["识别到的文字1", "文字2", ...],\n'
            '  "objects": [\n'
            '    {"name": "元素名称", "bbox": [x1, y1, x2, y2]}\n'
            '  ]\n'
            "}\n"
            "bbox 使用 0-1000 的归一化坐标。只输出 JSON，不要解释。"
        )

        models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        last_err = ""
        text = ""
        for model in models:
            log.append(f"[LLM] >>> analyze_scene TRY | model={model} | file={image_path}")
            try:
                text = self._call_vision_api(model, image_b64, prompt, 2048, timeout)
                cost = (time.time() - t0) * 1000
                log.append(
                    f"[LLM] <<< analyze_scene OK | model={model} | cost={cost:.1f}ms | raw_len={len(text)}"
                )
                log.append(f"[LLM] RAW: {text[:800]}")
                break
            except Exception as e:
                last_err = str(e)
                log.append(f"[LLM] analyze_scene FAIL model={model} | {e}")

        if not text:
            cost = (time.time() - t0) * 1000
            err = f"[qwen_vl_error] {last_err}"
            log.append(f"[LLM] <<< analyze_scene ALL_FAILED | cost={cost:.1f}ms | {err}")
            return {
                "scene_description": err,
                "ocr_text": [],
                "objects": [],
            }

        # 提取 JSON
        try:
            m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
            else:
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
                else:
                    data = {}
        except Exception:
            log.append(f"[LLM] JSON parse failed, raw: {text[:500]}")
            data = {}

        if not isinstance(data, dict):
            data = {}

        # 解析 ocr_text
        ocr_text = data.get("ocr_text", [])
        if isinstance(ocr_text, str):
            ocr_text = [line.strip() for line in ocr_text.split("\n") if line.strip()]

        # 解析 objects
        objects = []
        for item in data.get("objects", []):
            if isinstance(item, dict) and "name" in item and "bbox" in item:
                bbox = item["bbox"]
                if len(bbox) == 4:
                    objects.append({"name": item["name"], "bbox": bbox})

        scene_desc = data.get("scene_description", "")
        log.append(f"[LLM] parsed: scene='{scene_desc[:60]}' | ocr={len(ocr_text)} | obj={len(objects)}")

        return {
            "scene_description": scene_desc,
            "ocr_text": ocr_text,
            "objects": objects,
        }


class DeepSeekClient:
    """DeepSeek 决策模型客户端（OpenAI 兼容格式）"""

    DEFAULT_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.base_url = self.DEFAULT_URL
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def is_ready(self) -> bool:
        return bool(self.api_key)

    def decide(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        输入决策上下文，返回结构化决策结果。

        返回格式:
        {
            "raw": "模型原始回复",
            "action": "tap/swipe/scroll/wait/none",
            "params": {"x": 100, "y": 200, ...},
            "reasoning": "决策理由"
        }
        """
        if not self.api_key:
            return {
                "raw": "",
                "action": "none",
                "params": {},
                "reasoning": "[deepseek_error] API key not configured (DEEPSEEK_API_KEY)",
            }

        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            raw = (response.choices[0].message.content or "").strip()
            parsed = self._parse_decision(raw)
            parsed["raw"] = raw
            return parsed
        except Exception as e:
            return {
                "raw": "",
                "action": "none",
                "params": {},
                "reasoning": f"[deepseek_error] {e}",
            }

    @staticmethod
    def _parse_decision(raw: str) -> Dict[str, Any]:
        """尝试从模型回复中解析结构化决策 JSON"""
        # 1. 尝试提取 ```json 代码块
        m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                return {
                    "action": data.get("action", "none"),
                    "params": data.get("params", {}),
                    "reasoning": data.get("reasoning", raw),
                }
            except json.JSONDecodeError:
                pass

        # 2. 尝试直接找 JSON 对象
        text = raw.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                return {
                    "action": data.get("action", "none"),
                    "params": data.get("params", {}),
                    "reasoning": data.get("reasoning", raw),
                }
            except json.JSONDecodeError:
                pass

        # 3. 兜底：返回原始文本作为 reasoning
        return {
            "action": "none",
            "params": {},
            "reasoning": raw,
        }
