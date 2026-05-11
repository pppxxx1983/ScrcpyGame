"""SessionRepository Mixin for AgentDataManager."""
from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from log_manager import LogManager


class SessionRepository:
        def start_session(self) -> str:
            """开始新 session，返回 session_key。"""
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_session_id = ts
            self.current_session_dir = self.game_dir / "sessions" / ts
            (self.current_session_dir / "clicks").mkdir(parents=True, exist_ok=True)
            (self.current_session_dir / "frames").mkdir(parents=True, exist_ok=True)
            self.current_session_events_path = self.current_session_dir / "operations.jsonl"
            self.current_session_meta_path = self.current_session_dir / "recording_meta.json"

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
                "operations_path": str(self.current_session_events_path),
                "recording_meta_path": str(self.current_session_meta_path),
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
            self.current_session_events_path = None
            self.current_session_meta_path = None
            self.click_counter = 0

        def is_session_active(self) -> bool:
            return self.current_session_id is not None

        # ------------------------------------------------------------------
        # Click 事件
        # ------------------------------------------------------------------

        def get_click_dir(self) -> Optional[Path]:
            if self.current_session_dir:
                return self.current_session_dir / "clicks"
            return None

        def get_video_path(self) -> Optional[Path]:
            if self.current_session_id:
                return self.game_dir / "raw_videos" / f"{self.current_session_id}.mp4"
            return None

