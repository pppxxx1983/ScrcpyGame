"""
本地 OCR 客户端（基于 RapidOCR + ONNX Runtime）
- 无需联网，纯本地推理
- 支持中英文混合识别
- 首次运行时自动下载模型（约 30MB）
"""

from pathlib import Path
from typing import List, Optional

import numpy as np


class OCRClient:
    """
    OCR 文字识别客户端（单例）。

    使用示例:
        ocr = OCRClient()
        result = ocr.recognize(Path("screenshot.png"))
        # result -> [{"text": "开始游戏", "box": [...], "score": 0.98}, ...]
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        from rapidocr_onnxruntime import RapidOCR

        self.engine = RapidOCR()

    def recognize(self, image_path: Path) -> List[dict]:
        """
        识别图片中的文字。

        返回:
            [
                {"text": "开始游戏", "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "score": 0.98},
                ...
            ]
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return []

        result, _ = self.engine(str(image_path))
        if not result:
            return []

        items = []
        for item in result:
            box, text, score = item[0], item[1], item[2]
            items.append(
                {
                    "text": text,
                    "box": box,
                    "score": round(float(score), 4),
                }
            )
        return items

    def recognize_frame(self, frame: np.ndarray) -> List[dict]:
        """直接从 numpy 数组(BGR/RGB)识别文字。"""
        result, _ = self.engine(frame)
        if not result:
            return []

        items = []
        for item in result:
            box, text, score = item[0], item[1], item[2]
            items.append(
                {
                    "text": text,
                    "box": box,
                    "score": round(float(score), 4),
                }
            )
        return items

    def to_text(
        self,
        image_path: Optional[Path] = None,
        frame: Optional[np.ndarray] = None,
        min_score: float = 0.5,
    ) -> str:
        """
        识别并返回纯文本（按从上到下、从左到右排序）。

        参数:
            image_path: 图片路径（与 frame 二选一）
            frame: numpy 数组（与 image_path 二选一）
            min_score: 置信度阈值，低于此值的文字将被过滤
        """
        if frame is not None:
            items = self.recognize_frame(frame)
        elif image_path is not None:
            items = self.recognize(image_path)
        else:
            return ""

        filtered = [i for i in items if i["score"] >= min_score]
        if not filtered:
            return ""

        # 先按 y 排序（从上到下），再按 x 排序（从左到右）
        filtered.sort(key=lambda x: (x["box"][0][1], x["box"][0][0]))
        return "\n".join([i["text"] for i in filtered])
