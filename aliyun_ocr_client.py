"""
阿里云在线 OCR 客户端（基于 DashScope qwen-vl-max）
- 零本地 CPU 占用，彻底解决卡顿
- 大模型 OCR，对游戏 UI 艺术字、图标混排理解能力更强
- 接口和本地 OCRClient 兼容，可直接替换
"""

import os
import base64
import json
import urllib.request
from pathlib import Path
from typing import List, Optional


class AliyunOCRClient:
    """阿里云 DashScope qwen-vl-max 视觉 OCR"""

    DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-vl-max"):
        # 优先传入，其次环境变量，最后兜底（用户提供的 Key）
        self.api_key = (
            api_key
            or os.environ.get("DASHSCOPE_API_KEY", "")
            or "sk-b368216722514ad1956826669fe15b05"
        )
        self.model = model
        self.base_url = self.DEFAULT_URL

    def recognize(self, image_path: Path) -> List[dict]:
        """识别图片中的文字，返回兼容 OCRClient 的格式。"""
        if not self.api_key:
            return [{"text": "[aliyun_ocr_error] DASHSCOPE_API_KEY not set", "score": 0.0, "box": []}]

        image_path = Path(image_path)
        if not image_path.exists():
            return []

        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "请识别图片中的所有文字，按从上到下、从左到右的顺序逐行输出。"
                                "只输出文字本身，不要解释、不要推理、不要添加额外内容。"
                                "如果图片中没有文字，请输出'无文字'。"
                            ),
                        },
                    ],
                }
            ],
            "max_tokens": 2048,
            "temperature": 0,
        }

        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choice = result.get("choices", [{}])[0]
                message = choice.get("message", {})
                text = (message.get("content") or "").strip()
        except Exception as e:
            return [{"text": f"[aliyun_ocr_error] {e}", "score": 0.0, "box": []}]

        if not text or text == "无文字":
            return []

        # 按行解析，兼容本地 OCRClient 的输出格式
        # qwen-vl-max 不返回 bbox，box 为空，score 固定为 1.0
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if line:
                items.append({"text": line, "score": 1.0, "box": []})
        return items

    def to_text(self, image_path: Optional[Path] = None) -> str:
        """识别并返回纯文本。"""
        if image_path is None:
            return ""
        items = self.recognize(image_path)
        return "\n".join([i["text"] for i in items if not i["text"].startswith("[aliyun_ocr_error]")])


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python aliyun_ocr_client.py <image_path>")
        sys.exit(1)
    client = AliyunOCRClient()
    result = client.recognize(Path(sys.argv[1]))
    for item in result:
        print(f"[{item['score']:.2f}] {item['text']}")
