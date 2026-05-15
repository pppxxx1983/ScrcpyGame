"""
场景索引 + Ollama 8b 自动分类
- 用 scrcpy 有损帧做 hash 查找
- 找不到 → 保存到 unknown/，后台 Ollama 8b 识别后分类
- 找到了 → 在截图左上角显示名字，增加 hits
"""

import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from llm_client import QwenVLClient
from log_manager import LogManager


DEFAULT_DB = Path("game_agent_data") / "games" / "my_game" / "scene_index.sqlite"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3-vl:8b"

# 全局视觉模型客户端（ofox gpt-5.5）
_qwen_client = QwenVLClient()

_OLLAMA_STARTED = False
_OLLAMA_LOCK = threading.Lock()


def ensure_ollama_running(timeout: float = 30.0) -> bool:
    """检查 Ollama 服务是否运行，没运行则自动启动。返回是否成功。"""
    global _OLLAMA_STARTED

    with _OLLAMA_LOCK:
        if _OLLAMA_STARTED:
            return True

        # 1. 先检查服务是否已在运行
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    _OLLAMA_STARTED = True
                    return True
        except Exception:
            pass

        LogManager().append("[Ollama] 服务未运行，尝试自动启动...")

        # 2. 尝试启动 ollama serve
        try:
            # Windows 后台启动，隐藏窗口
            startupinfo = None
            if hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except FileNotFoundError:
            LogManager().append("[Ollama] 未找到 ollama 命令，请确保已安装并加入 PATH")
            return False
        except Exception as e:
            LogManager().append(f"[Ollama] 启动失败: {e}")
            return False

        # 3. 等待服务就绪
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:11434/",
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        _OLLAMA_STARTED = True
                        LogManager().append("[Ollama] 服务已启动")
                        return True
            except Exception:
                pass
            time.sleep(0.5)

        LogManager().append(f"[Ollama] 等待服务启动超时 ({timeout}s)")
        return False


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


# ── Ollama 8b 分类 ──────────────────────────────────────────────────────────

def classify_image_with_ollama(image_path: Path) -> dict:
    """用 Ollama 8b 模型识别图片，返回 {name, desc}。失败返回空 dict。"""
    if not ensure_ollama_running():
        return {}
    image_path = Path(image_path)
    if not image_path.exists():
        return {}

    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "分析这张游戏截图，只输出以下格式（不要解释）：\n"
        "名字:XXXX\n"
        "说明:XXXXXXXXXX\n"
        "\n"
        "名字要求：\n"
        "- 尽量4个字以内\n"
        "- 如：手机桌面、广告弹窗、logo、loading、登录界面、选人界面、"
        "游戏大厅、战斗画面、结算界面、设置菜单、背包界面、商城界面、"
        "任务列表、公告弹窗、网络断开、更新提示\n"
        "\n"
        "说明要求：\n"
        "- 一句话描述画面内容\n"
        "- 不超过30字"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个严格遵循格式要求的助手。"
                    "你只允许按用户指定的格式输出，"
                    "禁止输出任何解释、思考过程、分析步骤或其他多余内容。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 200},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        LogManager().append(f"[Ollama] classify error: {e}")
        return {}

    message = result.get("message", {})
    text = (message.get("content") or "").strip()
    if not text:
        text = (message.get("thinking") or "").strip()

    # 解析名字和说明
    name = ""
    desc = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("名字:") or line.startswith("名称:"):
            name = line.split(":", 1)[1].strip()[:10]
        elif line.startswith("说明:") or line.startswith("描述:"):
            desc = line.split(":", 1)[1].strip()[:50]

    # 清理名字：去掉非法字符，限制长度
    name = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    if len(name) > 10:
        name = name[:10]
    if not name:
        name = "未知"

    return {"name": name, "desc": desc, "raw": text}


def classify_image_with_qwen(image_path: Path) -> dict:
    """用 qwen-vl-max 识别图片，返回 {name, desc, raw}。失败返回空 dict。"""
    image_path = Path(image_path)
    if not image_path.exists():
        return {}

    prompt = (
        "分析这张游戏截图，只输出以下格式（不要解释）：\n"
        "名字:XXXX\n"
        "说明:XXXXXXXXXX\n"
        "\n"
        "名字要求：\n"
        "- 尽量4个字以内\n"
        "- 如：手机桌面、广告弹窗、logo、loading、登录界面、选人界面、"
        "游戏大厅、战斗画面、结算界面、设置菜单、背包界面、商城界面、"
        "任务列表、公告弹窗、网络断开、更新提示\n"
        "\n"
        "说明要求：\n"
        "- 一句话描述画面内容\n"
        "- 不超过30字"
    )

    text = _qwen_client.describe_image(image_path, prompt=prompt)
    if not text or text.startswith("[qwen_vl_error]"):
        return {}

    # 用和 Ollama 一样的解析逻辑
    name = ""
    desc = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("名字:") or line.startswith("名称:"):
            name = line.split(":", 1)[1].strip()[:10]
        elif line.startswith("说明:") or line.startswith("描述:"):
            desc = line.split(":", 1)[1].strip()[:50]

    # 清理名字：去掉非法字符，限制长度
    name = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    if len(name) > 10:
        name = name[:10]
    if not name:
        name = "未知"

    return {"name": name, "desc": desc, "raw": text}


def _draw_name_on_image(image_path: Path, name: str, output_path: Path = None) -> Path:
    """在图片左上角绘制识别名字，返回新图片路径。"""
    image_path = Path(image_path)
    img = Image.open(image_path).convert("RGBA")

    # 创建半透明黑色背景的文字层
    txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)

    # 尝试加载字体，失败用默认
    try:
        font = ImageFont.truetype("simhei.ttf", 32)
    except Exception:
        try:
            font = ImageFont.truetype("msyh.ttc", 32)
        except Exception:
            font = ImageFont.load_default()

    text = f"[{name}]"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    padding = 8
    bg_x1, bg_y1 = 10, 10
    bg_x2, bg_y2 = bg_x1 + text_w + padding * 2, bg_y1 + text_h + padding * 2

    # 画半透明黑底
    draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=(0, 0, 0, 180))
    # 画白色文字
    draw.text((bg_x1 + padding, bg_y1 + padding), text, font=font, fill=(255, 255, 255, 255))

    # 合并
    result = Image.alpha_composite(img, txt_layer)
    result = result.convert("RGB")

    if output_path is None:
        output_path = image_path.parent / f"{image_path.stem}_tagged{image_path.suffix}"
    result.save(str(output_path))
    return output_path


# ── 后台 unknown 处理器 ──────────────────────────────────────────────────────

class UnknownFolderProcessor:
    """后台线程：持续扫描 unknown 文件夹，用 Ollama 8b 识别并分类。"""

    def __init__(self, interval: int = 5, allow_cloud_fallback: bool = False):
        self.interval = interval
        self.allow_cloud_fallback = allow_cloud_fallback
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._si = SceneIndex()

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        LogManager().append("[UnknownProcessor] 后台分类线程已启动")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        unknown_dir = Path("screenshots") / "unknown"
        while not self._stop.is_set():
            self._process_once(unknown_dir)
            self._stop.wait(self.interval)

    def _process_once(self, unknown_dir: Path):
        if not unknown_dir.exists():
            return
        pngs = list(unknown_dir.glob("*.png"))
        if not pngs:
            return

        for img_path in pngs:
            if self._stop.is_set():
                break

            # 1. 先算 hash，看库里是否已有匹配
            fp = image_fingerprint(img_path)
            best = self._si.find_best(fp)
            threshold = 0.92

            if best and best["confidence"] >= threshold:
                # hash 匹配到已知场景，直接复用名字，无需调用 Ollama
                name = best.get("description", "")[:4] if best.get("description") else best["scene_key"][:8]
                if not name:
                    name = "已知"
                desc = best.get("description", "")
                # hash 匹配到已知场景，直接复用名字
                self._si._record_hit(best["id"])
                is_new = False
                cost = 0.0
            else:
                # 2. hash 未匹配，调用 Ollama 8b 识别；云端 fallback 只在显式开启时使用
                t0 = time.perf_counter()
                result = classify_image_with_ollama(img_path)
                if not result or not result.get("name") or result.get("name") == "未知":
                    if self.allow_cloud_fallback:
                        LogManager().append(f"[UnknownProcessor] {img_path.name} Ollama 未返回有效结果，fallback 到 qwen-vl-max")
                        result = classify_image_with_qwen(img_path)
                        if result and result.get("raw"):
                            LogManager().append(f"[UnknownProcessor] {img_path.name} qwen raw: {result['raw'][:120]}")
                    else:
                        LogManager().append(f"[UnknownProcessor] {img_path.name} Ollama 未返回有效结果，skip cloud fallback")
                cost = time.perf_counter() - t0
                fail_json = img_path.parent / f"{img_path.stem}.json"

                def _incr_fail(reason: str) -> bool:
                    """增加失败计数，超过阈值返回 True（表示已移入 unknown_error）。"""
                    fail_count = 1
                    if fail_json.exists():
                        try:
                            data = json.loads(fail_json.read_text(encoding="utf-8"))
                            fail_count = data.get("fail_count", 0) + 1
                        except Exception:
                            pass
                    if fail_count >= 3:
                        error_dir = Path("screenshots") / "unknown_error"
                        error_dir.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.move(str(img_path), str(error_dir / img_path.name))
                            fail_json.unlink(missing_ok=True)
                            LogManager().append(
                                f"[UnknownProcessor] {img_path.name} {reason}，"
                                f"失败 {fail_count} 次，移入 unknown_error/"
                            )
                        except Exception:
                            pass
                        return True
                    fail_json.write_text(
                        json.dumps({"fail_count": fail_count, "reason": reason}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    LogManager().append(
                        f"[UnknownProcessor] {img_path.name} {reason}，保留重试 ({fail_count}/3)"
                    )
                    return False

                if not result:
                    if _incr_fail("Ollama 无响应"):
                        continue
                    continue

                name = result.get("name", "")
                desc = result.get("desc", "")
                raw = result.get("raw", "")

                # 记录原始输出，方便排查模型到底回了什么
                if raw:
                    LogManager().append(f"[UnknownProcessor] {img_path.name} raw: {raw[:120]}")

                if not name or name == "未知":
                    if _incr_fail(f"识别结果为'{name}'"):
                        continue
                    continue

                # 识别成功，清理失败记录
                if fail_json.exists():
                    fail_json.unlink(missing_ok=True)

                LogManager().append(
                    f"[UnknownProcessor] {img_path.name} → '{name}' ({cost:.1f}s)"
                )
                is_new = True

            # 3. 分类到对应文件夹，并从 unknown 删除原图
            target_dir = Path("screenshots") / name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / img_path.name
            try:
                shutil.move(str(img_path), str(target_path))
            except Exception:
                # move 失败则复制后删除原图
                try:
                    shutil.copy2(str(img_path), str(target_path))
                    os.remove(str(img_path))
                except Exception:
                    pass

            # 清理失败记录（hash 匹配成功时也清理）
            _fj = img_path.parent / f"{img_path.stem}.json"
            if _fj.exists():
                _fj.unlink(missing_ok=True)

            # 4. 如果是 Ollama 新识别的，hash 入库
            if is_new:
                fp = image_fingerprint(target_path)
                self._si._insert_scene(
                    target_path, fp, desc,
                    name=name,
                    model_name=OLLAMA_MODEL,
                    recognize_cost=round(cost, 2),
                )


# ── SceneIndex 数据库操作 ───────────────────────────────────────────────────

class SceneIndex:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 自动迁移：旧路径在 screenshots/ 下，如果新路径没有但旧路径有，复制过去
        old_db = Path("screenshots") / "scene_index.sqlite"
        if not self.db_path.exists() and old_db.exists():
            import shutil
            shutil.copy2(str(old_db), str(self.db_path))
            LogManager().append(f"[SceneIndex] 数据库已从 {old_db} 迁移到 {self.db_path}")

        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def list_all_scenes(self) -> list[dict]:
        """返回所有场景记录。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, scene_key, description, image_path, hits, review_status, scene_type, created_at FROM scenes ORDER BY hits DESC"
            ).fetchall()
        return [
            {
                "id": row[0],
                "scene_key": row[1],
                "description": row[2],
                "image_path": row[3],
                "hits": row[4],
                "review_status": row[5],
                "scene_type": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

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
                    model_name TEXT NOT NULL DEFAULT '',
                    recognize_cost REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    scene_level TEXT NOT NULL DEFAULT '',
                    scene_state TEXT NOT NULL DEFAULT '',
                    scene_context TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_dhash ON scenes(dhash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_scene_key ON scenes(scene_key)")
            for col_def in [
                ("model_name", "TEXT NOT NULL DEFAULT ''"),
                ("recognize_cost", "REAL NOT NULL DEFAULT 0"),
                ("review_status", "INTEGER NOT NULL DEFAULT 0"),
                ("scene_level", "TEXT NOT NULL DEFAULT ''"),
                ("scene_state", "TEXT NOT NULL DEFAULT ''"),
                ("scene_context", "TEXT NOT NULL DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE scenes ADD COLUMN {col_def[0]} {col_def[1]}")
                except Exception:
                    pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_level ON scenes(scene_level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_state ON scenes(scene_state)")

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
                "hits": best["hits"],
            }

        # 未匹配到，返回未匹配信息
        return {
            "matched": False,
            "confidence": best["confidence"] if best else 0.0,
            "nearest_scene_id": best["id"] if best else None,
            "scene_key": fp["dhash"],
            "description": "",
            "distance": best["distance"] if best else None,
        }

    def _record_hit(self, scene_id: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with self._connect() as conn:
            conn.execute(
                "UPDATE scenes SET hits = hits + 1, updated_at = ? WHERE id = ?",
                (now, scene_id),
            )

    def _insert_scene(
        self,
        image_path: Path,
        fingerprint: dict,
        description: str,
        name: str = "",
        model_name: str = "",
        recognize_cost: float = 0.0,
        review_status: int = 0,
    ) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        # scene_key 存人可读的名称，dhash 存 hash 值
        scene_key = name if name else fingerprint["dhash"]
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO scenes (
                    scene_key, dhash, ahash, description, image_path,
                    width, height, model_name, recognize_cost, review_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_key,
                    fingerprint["dhash"],
                    fingerprint["ahash"],
                    description,
                    str(image_path),
                    fingerprint["width"],
                    fingerprint["height"],
                    model_name,
                    recognize_cost,
                    review_status,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def register_from_review(
        self,
        image_path: Path,
        scene_name: str = "",
        description: str = "",
        threshold: float = 0.96,
    ) -> dict:
        """
        将人工审核通过的场景注册到 hash 索引。
        如果已有相似度 >= threshold 的记录，只增加 hits 不重复插入。
        返回 {registered: bool, scene_id: int, existed: bool, confidence: float}
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return {"registered": False, "error": "image not found", "confidence": 0.0}

        fp = image_fingerprint(image_path)
        best = self.find_best(fp)

        if best and best["confidence"] >= threshold:
            # 已有足够相似的记录，增加命中计数
            self._record_hit(best["id"])
            return {
                "registered": True,
                "scene_id": best["id"],
                "existed": True,
                "confidence": best["confidence"],
                "scene_key": best["scene_key"],
            }

        # 插入新记录，标记为人工审核通过（review_status=1）
        scene_id = self._insert_scene(
            image_path=image_path,
            fingerprint=fp,
            description=description,
            name=scene_name,
            model_name="human_review",
            review_status=1,
        )
        return {
            "registered": True,
            "scene_id": scene_id,
            "existed": False,
            "confidence": 1.0,
            "scene_key": scene_name if scene_name else fp["dhash"],
        }


# ── 兼容旧接口 ──────────────────────────────────────────────────────────────

def describe_image_with_qwen(image_path: Path, model: str = "qwen-vl-max") -> str:
    """使用 qwen-vl-max 解读画面（优先），若未配置 key 则 fallback 到 ollama。"""
    if _qwen_client.is_ready():
        return _qwen_client.describe_image(image_path)
    return describe_image_with_ollama(image_path, model="qwen3-vl:2b")


def describe_image_with_ollama(image_path: Path, model: str = "qwen3-vl:2b") -> str:
    if not ensure_ollama_running():
        return "[ollama_error] 服务未启动"
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
    args = parser.parse_args()

    result = SceneIndex().ensure_scene(Path(args.image), threshold=args.threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def update_scene_classification(scene_id: int, scene_level: str, scene_state: str = "", scene_context: str = "") -> bool:
    """更新场景的分类信息"""
    si = SceneIndex()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with si._connect() as conn:
            conn.execute(
                "UPDATE scenes SET scene_level = ?, scene_state = ?, scene_context = ?, updated_at = ? WHERE id = ?",
                (scene_level, scene_state, scene_context, now, scene_id),
            )
        return True
    except Exception as e:
        LogManager().append(f"[SceneIndex] update_scene_classification failed: {e}")
        return False


def get_scenes_by_level(scene_level: str) -> list[dict]:
    """根据场景层级获取所有场景"""
    si = SceneIndex()
    try:
        with si._connect() as conn:
            rows = conn.execute(
                "SELECT id, scene_key, description, scene_level, scene_state, hits, created_at FROM scenes WHERE scene_level = ? ORDER BY hits DESC",
                (scene_level,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "scene_key": r[1],
                "description": r[2],
                "scene_level": r[3],
                "scene_state": r[4],
                "hits": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        LogManager().append(f"[SceneIndex] get_scenes_by_level failed: {e}")
        return []


def get_scene_classification_stats() -> dict:
    """获取场景分类统计信息"""
    si = SceneIndex()
    stats = {
        "by_level": {},
        "by_state": {},
        "total": 0,
        "unclassified": 0,
    }
    try:
        with si._connect() as conn:
            rows = conn.execute(
                "SELECT scene_level, scene_state, COUNT(*) as count FROM scenes GROUP BY scene_level, scene_state"
            ).fetchall()

            total = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
            unclassified = conn.execute(
                "SELECT COUNT(*) FROM scenes WHERE scene_level = '' OR scene_level IS NULL"
            ).fetchone()[0]

            stats["total"] = total
            stats["unclassified"] = unclassified

            for row in rows:
                level, state, count = row
                if level not in stats["by_level"]:
                    stats["by_level"][level] = {"total": 0, "states": {}}
                stats["by_level"][level]["total"] += count
                if state:
                    stats["by_level"][level]["states"][state] = count
    except Exception as e:
        LogManager().append(f"[SceneIndex] get_scene_classification_stats failed: {e}")

    return stats
