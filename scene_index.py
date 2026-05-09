import base64
import json
import sqlite3
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from llm_client import QwenVLClient


DEFAULT_DB = Path("screenshots") / "scene_index.sqlite"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# 全局视觉模型客户端（qwen-vl-max）
_qwen_client = QwenVLClient()


def _bits_to_hex(bits: np.ndarray) -> str:
    value = 0
    for bit in bits.astype(bool).flatten():
        value = (value << 1) | int(bit)
    width = (bits.size + 3) // 4
    return f"{value:0{width}x}"


def _hamming_hex(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def image_fingerprint(image_path: Path) -> dict:
    image = Image.open(image_path).convert("L")
    ah = np.asarray(image.resize((8, 8), Image.Resampling.LANCZOS), dtype=np.uint8)
    dh = np.asarray(image.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.uint8)
    return {
        "ahash": _bits_to_hex(ah > ah.mean()),
        "dhash": _bits_to_hex(dh[:, 1:] > dh[:, :-1]),
        "width": image.width,
        "height": image.height,
    }


def confidence_from_distance(distance: int, bits: int = 64) -> float:
    return round(max(0.0, 1.0 - distance / bits), 6)


class SceneIndex:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_key TEXT NOT NULL,
                    dhash TEXT NOT NULL,
                    ahash TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    image_path TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_dhash ON scenes(dhash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_scene_key ON scenes(scene_key)")

    def find_best(self, fingerprint: dict) -> dict | None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, scene_key, dhash, ahash, description, image_path, hits FROM scenes"
            ).fetchall()

        best = None
        for row in rows:
            scene_id, scene_key, dhash, ahash, description, image_path, hits = row
            d_dist = _hamming_hex(fingerprint["dhash"], dhash)
            a_dist = _hamming_hex(fingerprint["ahash"], ahash)
            distance = min(64, int(d_dist * 0.75 + a_dist * 0.25))
            confidence = confidence_from_distance(distance)
            candidate = {
                "id": scene_id,
                "scene_key": scene_key,
                "distance": distance,
                "confidence": confidence,
                "description": description,
                "image_path": image_path,
                "hits": hits,
            }
            if best is None or candidate["confidence"] > best["confidence"]:
                best = candidate
        return best

    def ensure_scene(
        self,
        image_path: Path,
        threshold: float = 0.92,
        describe_model: str = "qwen3-vl:2b",
    ) -> dict:
        image_path = Path(image_path)
        fp = image_fingerprint(image_path)
        best = self.find_best(fp)
        if best and best["confidence"] >= threshold:
            self._record_hit(best["id"])
            return {
                "matched": True,
                "confidence": best["confidence"],
                "scene_id": best["id"],
                "scene_key": best["scene_key"],
                "description": best["description"],
                "distance": best["distance"],
                "model": None,
            }

        # 暂时跳过视觉描述（ollama/qwen-vl-max），避免网络阻塞和 CPU 占用
        description = ""
        scene_id = self._insert_scene(image_path, fp, description)
        return {
            "matched": False,
            "confidence": best["confidence"] if best else 0.0,
            "nearest_scene_id": best["id"] if best else None,
            "scene_id": scene_id,
            "scene_key": fp["dhash"],
            "description": description,
            "distance": best["distance"] if best else None,
            "model": None,
        }

    def _record_hit(self, scene_id: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with self._connect() as conn:
            conn.execute(
                "UPDATE scenes SET hits = hits + 1, updated_at = ? WHERE id = ?",
                (now, scene_id),
            )

    def _insert_scene(self, image_path: Path, fingerprint: dict, description: str) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO scenes (
                    scene_key, dhash, ahash, description, image_path,
                    width, height, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint["dhash"],
                    fingerprint["dhash"],
                    fingerprint["ahash"],
                    description,
                    str(image_path),
                    fingerprint["width"],
                    fingerprint["height"],
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)


def describe_image_with_qwen(image_path: Path, model: str = "qwen-vl-max") -> str:
    """使用 qwen-vl-max 解读画面（优先），若未配置 key 则 fallback 到 ollama。"""
    if _qwen_client.is_ready():
        return _qwen_client.describe_image(image_path)
    # fallback: ollama
    return describe_image_with_ollama(image_path, model="qwen3-vl:2b")


def describe_image_with_ollama(image_path: Path, model: str = "qwen3-vl:2b") -> str:
    image_path = Path(image_path)
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "请判断这张游戏截图的关键画面状态，用一句中文描述。"
                    "不要写推理过程，不要超过60字。"
                ),
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 120},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"[ollama_error] {e}"

    message = result.get("message", {})
    text = (message.get("content") or "").strip()
    if not text:
        text = (message.get("thinking") or "").strip()
    text = _clean_description(text)
    elapsed = time.perf_counter() - started
    return f"{text} [model={model}, elapsed={elapsed:.3f}s]"


def _clean_description(text: str) -> str:
    text = text.replace("<think>", "").replace("</think>", "").strip()
    if "\n\n" in text:
        text = text.split("\n\n", 1)[0].strip()
    text = " ".join(text.split())
    for marker in ["关键点是", "关键画面是", "这是", "图片是", "截图是"]:
        pos = text.find(marker)
        if pos >= 0:
            text = text[pos:].strip(" ：:，,。")
            break
    for marker in ["首先", "用户", "需要我", "我得", "先看"]:
        if text.startswith(marker):
            parts = text.split("。")
            text = parts[-1] if parts else text
            text = text.strip(" ：:，,。")
            break
    if " [model=" in text:
        text = text.split(" [model=", 1)[0].strip()
    if len(text) > 90:
        text = text[:90].rstrip(" ，,。") + "..."
    return text


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--threshold", type=float, default=0.92)
    parser.add_argument("--model", default="qwen3-vl:2b")
    args = parser.parse_args()

    result = SceneIndex().ensure_scene(
        Path(args.image),
        threshold=args.threshold,
        describe_model=args.model,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
