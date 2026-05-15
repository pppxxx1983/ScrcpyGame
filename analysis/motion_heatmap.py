"""
运动热力图分析器
基于帧差法检测运动区域，并随时间累积形成热力图。
"""

from typing import Optional

import numpy as np


class MotionHeatmapAnalyzer:
    """
    计算视频中动的区域和不动的区域，并生成热力图。

    原理：
    1. 将当前帧与前一帧转为灰度图做差值
    2. 差值大于阈值的区域判定为"动的区域"
    3. 运动区域累加到 heatmap，静止区域按 decay 系数衰减
    4. 最终 heatmap 经颜色映射（COLORMAP_JET）生成彩色图
    """

    def __init__(self, decay: float = 0.95, threshold: int = 25, blur_ksize: int = 15):
        self.decay = decay              # 衰减系数（0~1，越小消失越快）
        self.threshold = threshold      # 运动检测阈值（像素差值）
        self.blur_ksize = blur_ksize    # 高斯模糊核大小（奇数）
        self._prev_gray: Optional[np.ndarray] = None
        self._heatmap: Optional[np.ndarray] = None

    def update(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        传入新帧（RGB/BGR numpy array），更新热力图。
        返回彩色热力图（RGB），如果没有足够数据则返回 None。
        """
        import cv2

        if frame is None or frame.size == 0:
            return None

        # 统一转为灰度图
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        else:
            gray = frame.copy()

        h, w = gray.shape[:2]

        # 初始化热力图矩阵
        if self._heatmap is None or self._heatmap.shape != (h, w):
            self._heatmap = np.zeros((h, w), dtype=np.float32)
            self._prev_gray = None

        # 第一帧无法计算差值，只做记录
        if self._prev_gray is None:
            self._prev_gray = gray
            return None

        # 1. 帧差法：计算两帧灰度绝对差值
        diff = cv2.absdiff(self._prev_gray, gray)

        # 2. 二值化：动的区域设为 1.0，不动区域设为 0
        _, motion_mask = cv2.threshold(diff, self.threshold, 1.0, cv2.THRESH_BINARY)

        # 3. 先转 float32 再做高斯模糊，避免 uint8 精度丢失（1 经 15x15 模糊后四舍五入为 0）
        motion_mask = motion_mask.astype(np.float32)
        motion_mask = cv2.GaussianBlur(motion_mask, (self.blur_ksize, self.blur_ksize), 0)

        # 4. 衰减 + 累积：旧热度衰减，新运动叠加
        self._heatmap = self._heatmap * self.decay + motion_mask

        # 保存当前帧供下次使用
        self._prev_gray = gray

        return self.get_colormap()

    def get_colormap(self) -> Optional[np.ndarray]:
        """将当前热力图转为彩色图（RGB）返回。"""
        import cv2

        if self._heatmap is None:
            return None

        # 归一化到 0~255
        hmax = self._heatmap.max()
        if hmax < 1e-6:
            normalized = np.zeros_like(self._heatmap, dtype=np.uint8)
        else:
            normalized = (self._heatmap / hmax * 255).astype(np.uint8)

        # 应用 JET 颜色映射（OpenCV 默认输出 BGR）
        colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)

        # BGR -> RGB
        colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)

        return colored

    def reset(self):
        """重置热力图状态。"""
        self._prev_gray = None
        self._heatmap = None
