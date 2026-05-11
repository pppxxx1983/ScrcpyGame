"""
GPT-5.5 Reanalyze 历史记录管理器
集中保存每次 Reanalyze 调用的完整信息：
- 时间戳
- 图片路径、场景文件夹
- 发送的完整 prompt
- 返回的原始结果
- 解析后的对象列表
- 使用的模型、耗时、是否成功
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


DEFAULT_HISTORY_FILE = Path("game_agent_data") / "reanalyze_history.jsonl"


class ReanalyzeLogger:
    """Reanalyze 调用历史记录器，追加写入 JSONL，便于按时间顺序读取。"""

    def __init__(self, history_file: Optional[Path] = None):
        self.history_file = Path(history_file) if history_file else DEFAULT_HISTORY_FILE
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def append(
        self,
        *,
        image_path: str,
        folder: str,
        prompt: str,
        raw_response: str,
        model: str = "",
        objects: Optional[list[dict]] = None,
        error: str = "",
        duration_ms: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        追加一条记录到历史文件，返回写入的记录字典。
        """
        modified_count = sum(1 for o in (objects or []) if o.get("modified")) if objects else 0
        record = {
            "timestamp": self._now(),
            "unix_time": time.time(),
            "image_path": str(image_path),
            "folder": str(folder),
            "prompt": prompt,
            "raw_response": raw_response,
            "model": model,
            "object_count": len(objects) if objects else 0,
            "modified_count": modified_count,
            "objects": objects or [],
            "success": not bool(error),
            "error": error,
            "duration_ms": round(duration_ms, 2),
            "metadata": metadata or {},
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self.history_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return record

    def read_all(self, limit: int = 0, reverse: bool = True) -> list[dict]:
        """
        读取所有历史记录。
        :param limit: 0 表示不限制
        :param reverse: True 表示按时间倒序（最新的在前）
        """
        records = []
        if not self.history_file.exists():
            return records
        with self.history_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if reverse:
            records.reverse()
        if limit > 0:
            records = records[:limit]
        return records

    def read_for_image(self, image_path: str) -> list[dict]:
        """读取某张图片的所有历史记录，按时间倒序。"""
        image_path = str(image_path)
        results = []
        if not self.history_file.exists():
            return results
        with self.history_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("image_path") == image_path:
                        results.append(rec)
                except json.JSONDecodeError:
                    continue
        results.reverse()
        return results

    def read_for_folder(self, folder: str) -> list[dict]:
        """读取某个文件夹的所有历史记录，按时间倒序。"""
        folder = str(folder)
        results = []
        if not self.history_file.exists():
            return results
        with self.history_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("folder") == folder:
                        results.append(rec)
                except json.JSONDecodeError:
                    continue
        results.reverse()
        return results

    def get_stats(self) -> dict:
        """返回统计信息。"""
        records = self.read_all(reverse=False)
        total = len(records)
        success = sum(1 for r in records if r.get("success"))
        failed = total - success
        total_objects = sum(r.get("object_count", 0) for r in records)
        avg_duration = (
            round(sum(r.get("duration_ms", 0) for r in records) / max(1, total), 2)
            if total else 0
        )
        models = {}
        for r in records:
            m = r.get("model") or "unknown"
            models[m] = models.get(m, 0) + 1
        return {
            "total_calls": total,
            "success": success,
            "failed": failed,
            "total_objects": total_objects,
            "avg_duration_ms": avg_duration,
            "models": models,
        }

    def clear(self):
        """清空历史记录文件。"""
        if self.history_file.exists():
            self.history_file.unlink()


# 全局单例
_default_logger: Optional[ReanalyzeLogger] = None


def get_logger() -> ReanalyzeLogger:
    global _default_logger
    if _default_logger is None:
        _default_logger = ReanalyzeLogger()
    return _default_logger
