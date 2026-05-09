"""
游戏 AI Agent 数据管理器
- 目录结构: game_agent_data/games/my_game/
- SQLite 单文件数据库: agent.db
- 管理 session、click_event、scene、ocr_result 等
"""

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

GAME_DATA_DIR = Path("game_agent_data") / "games" / "my_game"


class AgentDataManager:
    """
    Agent 数据管理（单例）。

    目录结构:
        game_agent_data/games/my_game/
        ├── raw_videos/
        ├── sessions/YYYYMMDD_HHMMSS/
        │   ├── clicks/
        │   ├── frames/
        │   └── session.json
        ├── scenes/
        ├── labels/
        ├── crops/
        └── agent.db
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.game_dir = GAME_DATA_DIR
        self._init_dirs()
        self.db_path = self.game_dir / "agent.db"
        self._init_db()
        self.current_session_id: Optional[str] = None
        self.current_session_dir: Optional[Path] = None
        self.click_counter = 0

    # ------------------------------------------------------------------
    # 目录 & 数据库初始化
    # ------------------------------------------------------------------
    def _init_dirs(self):
        for sub in ["raw_videos", "sessions", "scenes", "labels", "crops"]:
            (self.game_dir / sub).mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT,
                game_name TEXT,
                video_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scene (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scene_sample (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER,
                image_path TEXT,
                width INTEGER,
                height INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scene_hash (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER,
                region_name TEXT,
                box_x1 INTEGER,
                box_y1 INTEGER,
                box_x2 INTEGER,
                box_y2 INTEGER,
                phash TEXT,
                dhash TEXT,
                ahash TEXT,
                weight REAL DEFAULT 1.0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER,
                text TEXT,
                score REAL,
                box_x1 INTEGER,
                box_y1 INTEGER,
                box_x2 INTEGER,
                box_y2 INTEGER
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS click_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                index_no INTEGER,
                timestamp_ms INTEGER,
                x INTEGER,
                y INTEGER,
                before_image TEXT,
                after_300ms_image TEXT,
                after_800ms_image TEXT,
                before_scene_id INTEGER,
                after_scene_id INTEGER
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS action (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_scene_id INTEGER,
                to_scene_id INTEGER,
                action_name TEXT,
                x INTEGER,
                y INTEGER,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_element (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER,
                element_type TEXT,
                element_name TEXT,
                text TEXT,
                x1 INTEGER,
                y1 INTEGER,
                x2 INTEGER,
                y2 INTEGER,
                source TEXT,
                confidence REAL
            )
            """
        )

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    def start_session(self) -> str:
        """开始新 session，返回 session_key。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_id = ts
        self.current_session_dir = self.game_dir / "sessions" / ts
        (self.current_session_dir / "clicks").mkdir(parents=True, exist_ok=True)
        (self.current_session_dir / "frames").mkdir(parents=True, exist_ok=True)

        video_path = self.game_dir / "raw_videos" / f"{ts}.mp4"

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO session (session_key, game_name, video_path) VALUES (?, ?, ?)",
            (ts, "my_game", str(video_path)),
        )
        conn.commit()
        conn.close()

        session_json = {
            "session_id": ts,
            "game_name": "my_game",
            "video_path": str(video_path),
            "created_at": datetime.now().isoformat(),
        }
        (self.current_session_dir / "session.json").write_text(
            json.dumps(session_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.click_counter = 0
        return ts

    def end_session(self):
        """结束当前 session。"""
        self.current_session_id = None
        self.current_session_dir = None
        self.click_counter = 0

    def is_session_active(self) -> bool:
        return self.current_session_id is not None

    # ------------------------------------------------------------------
    # Click 事件
    # ------------------------------------------------------------------
    def record_click(
        self,
        x: int,
        y: int,
        before_image: Optional[Path] = None,
        after_300ms_image: Optional[Path] = None,
        after_800ms_image: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """记录一次点击事件，返回 click 数据。"""
        if not self.current_session_id:
            raise RuntimeError("No active session")

        self.click_counter += 1
        idx = self.click_counter

        click_dir = self.current_session_dir / "clicks"
        click_dir.mkdir(parents=True, exist_ok=True)

        click_data = {
            "session_id": self.current_session_id,
            "click_index": idx,
            "timestamp_ms": int(time.time() * 1000),
            "click": {"x": x, "y": y},
            "before_image": before_image.name if before_image else None,
            "after_images": [],
        }

        if after_300ms_image:
            click_data["after_images"].append(after_300ms_image.name)
            click_data["after_300ms_image"] = after_300ms_image.name
        if after_800ms_image:
            click_data["after_images"].append(after_800ms_image.name)
            click_data["after_800ms_image"] = after_800ms_image.name

        click_json_path = click_dir / f"click_{idx:06d}.json"
        click_json_path.write_text(
            json.dumps(click_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO click_event
            (session_id, index_no, timestamp_ms, x, y, before_image, after_300ms_image, after_800ms_image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.current_session_id,
                idx,
                click_data["timestamp_ms"],
                x,
                y,
                str(before_image) if before_image else None,
                str(after_300ms_image) if after_300ms_image else None,
                str(after_800ms_image) if after_800ms_image else None,
            ),
        )
        conn.commit()
        conn.close()

        return click_data

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def get_click_dir(self) -> Optional[Path]:
        if self.current_session_dir:
            return self.current_session_dir / "clicks"
        return None

    def get_video_path(self) -> Optional[Path]:
        if self.current_session_id:
            return self.game_dir / "raw_videos" / f"{self.current_session_id}.mp4"
        return None
