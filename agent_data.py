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

from log_manager import LogManager

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
        self.current_session_events_path: Optional[Path] = None
        self.current_session_meta_path: Optional[Path] = None
        self.click_counter = 0

    # ------------------------------------------------------------------
    # 目录 & 数据库初始化
    # ------------------------------------------------------------------
    def _init_dirs(self):
        for sub in [
            "raw_videos",
            "sessions",
            "scenes",
            "labels",
            "crops",
            "yolo_events/images/train",
            "yolo_events/labels/train",
        ]:
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
        for col_def in [
            ("scene_key", "TEXT DEFAULT ''"),
            ("dhash", "TEXT DEFAULT ''"),
            ("ahash", "TEXT DEFAULT ''"),
            ("image_path", "TEXT DEFAULT ''"),
            ("yolo_class_id", "INTEGER DEFAULT 0"),
            ("action_effect", "TEXT DEFAULT ''"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE ui_element ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ui_element_scene_id ON ui_element(scene_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ui_element_scene_key ON ui_element(scene_key)")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS physical_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT UNIQUE,
                action_type TEXT,
                timestamp_ms INTEGER,
                duration_ms INTEGER,
                device_start_x INTEGER,
                device_start_y INTEGER,
                device_end_x INTEGER,
                device_end_y INTEGER,
                frame_start_x INTEGER,
                frame_start_y INTEGER,
                frame_end_x INTEGER,
                frame_end_y INTEGER,
                folder_path TEXT,
                before_image TEXT,
                pressed_image TEXT,
                after_image TEXT,
                index_path TEXT,
                yolo_image TEXT,
                yolo_label TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_rule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_key TEXT UNIQUE,
                scene_id INTEGER,
                scene_key TEXT,
                element_id INTEGER,
                element_name TEXT,
                action_type TEXT,
                action_effect TEXT,
                user_intent TEXT,
                bbox_json TEXT,
                next_scene_id INTEGER,
                next_scene_key TEXT,
                source_event TEXT,
                source TEXT,
                confidence REAL,
                hits INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runtime_rule_scene_id ON runtime_rule(scene_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runtime_rule_scene_key ON runtime_rule(scene_key)")
        # 兼容升级：添加 enabled 列
        try:
            cursor.execute("ALTER TABLE runtime_rule ADD COLUMN enabled INTEGER DEFAULT 1")
        except Exception:
            pass

        conn.commit()
        conn.close()

    @staticmethod
    def _hash_confidence(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        try:
            distance = (int(left, 16) ^ int(right, 16)).bit_count()
            return round(max(0.0, 1.0 - distance / 64), 6)
        except Exception:
            return 0.0

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
    def record_click(
        self,
        x: int,
        y: int,
        before_image: Optional[Path] = None,
        after_300ms_image: Optional[Path] = None,
        after_800ms_image: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """记录一次点击事件，返回 click 数据。"""
        LogManager().append(f"[AgentData] record_click called: before={before_image}, after300={after_300ms_image}, after800={after_800ms_image}")
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
        db_before = str(before_image) if before_image else None
        db_after300 = str(after_300ms_image) if after_300ms_image else None
        db_after800 = str(after_800ms_image) if after_800ms_image else None
        LogManager().append(f"[AgentData] DB insert: before={db_before}, after300={db_after300}, after800={db_after800}")
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
                db_before,
                db_after300,
                db_after800,
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

    def record_physical_event(
        self,
        event_key: str,
        action_type: str,
        timestamp_ms: int,
        duration_ms: int,
        touch: Dict[str, Any],
        folder_path: Path,
        images: Dict[str, Any],
        index_path: Path,
        yolo: Optional[Dict[str, Any]] = None,
    ) -> int:
        """记录一次物理触摸/投屏触摸事件，允许重复写入时覆盖同 event_key。"""
        start = touch.get("start", {})
        end = touch.get("end", {})
        frame_start = touch.get("frame_start", {})
        frame_end = touch.get("frame_end", {})
        yolo = yolo or {}

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO physical_event (
                event_key, action_type, timestamp_ms, duration_ms,
                device_start_x, device_start_y, device_end_x, device_end_y,
                frame_start_x, frame_start_y, frame_end_x, frame_end_y,
                folder_path, before_image, pressed_image, after_image,
                index_path, yolo_image, yolo_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
                action_type=excluded.action_type,
                timestamp_ms=excluded.timestamp_ms,
                duration_ms=excluded.duration_ms,
                device_start_x=excluded.device_start_x,
                device_start_y=excluded.device_start_y,
                device_end_x=excluded.device_end_x,
                device_end_y=excluded.device_end_y,
                frame_start_x=excluded.frame_start_x,
                frame_start_y=excluded.frame_start_y,
                frame_end_x=excluded.frame_end_x,
                frame_end_y=excluded.frame_end_y,
                folder_path=excluded.folder_path,
                before_image=excluded.before_image,
                pressed_image=excluded.pressed_image,
                after_image=excluded.after_image,
                index_path=excluded.index_path,
                yolo_image=excluded.yolo_image,
                yolo_label=excluded.yolo_label
            """,
            (
                event_key,
                action_type,
                timestamp_ms,
                duration_ms,
                start.get("x"),
                start.get("y"),
                end.get("x"),
                end.get("y"),
                frame_start.get("x"),
                frame_start.get("y"),
                frame_end.get("x"),
                frame_end.get("y"),
                str(folder_path),
                str(folder_path / images["before"]) if images.get("before") else None,
                str(folder_path / images["pressed"]) if images.get("pressed") else None,
                str(folder_path / images["after"]) if images.get("after") else None,
                str(index_path),
                yolo.get("dataset_image"),
                yolo.get("dataset_label"),
            ),
        )
        row_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return row_id

    def find_ui_element_by_hash(self, fingerprint: Dict[str, Any], threshold: float = 0.88) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT id, scene_id, scene_key, element_type, element_name, text,
                   x1, y1, x2, y2, source, confidence, dhash, ahash,
                   image_path, yolo_class_id, action_effect
            FROM ui_element
            WHERE dhash IS NOT NULL AND dhash != ''
            """
        ).fetchall()
        conn.close()

        best = None
        for row in rows:
            d_conf = self._hash_confidence(fingerprint.get("dhash", ""), row[12])
            a_conf = self._hash_confidence(fingerprint.get("ahash", ""), row[13])
            confidence = round(d_conf * 0.75 + a_conf * 0.25, 6)
            if confidence < threshold:
                continue
            item = {
                "id": row[0],
                "scene_id": row[1],
                "scene_key": row[2],
                "element_type": row[3],
                "element_name": row[4],
                "text": row[5],
                "bbox_xyxy": [row[6], row[7], row[8], row[9]],
                "source": row[10],
                "confidence": confidence,
                "stored_confidence": row[11],
                "dhash": row[12],
                "ahash": row[13],
                "image_path": row[14],
                "yolo_class_id": row[15],
                "action_effect": row[16],
            }
            if best is None or item["confidence"] > best["confidence"]:
                best = item
        return best

    def upsert_ui_element(
        self,
        scene_id: Optional[int],
        scene_key: str,
        element_type: str,
        element_name: str,
        text: str,
        bbox_xyxy: list[int],
        source: str,
        confidence: float,
        fingerprint: Dict[str, Any],
        image_path: Path,
        yolo_class_id: int,
        action_effect: str,
    ) -> int:
        x1, y1, x2, y2 = bbox_xyxy
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        existing = cursor.execute(
            "SELECT id FROM ui_element WHERE dhash = ? AND ahash = ?",
            (fingerprint.get("dhash", ""), fingerprint.get("ahash", "")),
        ).fetchone()
        if existing:
            row_id = int(existing[0])
            cursor.execute(
                """
                UPDATE ui_element
                SET scene_id=?, scene_key=?, element_type=?, element_name=?, text=?,
                    x1=?, y1=?, x2=?, y2=?, source=?, confidence=?,
                    image_path=?, yolo_class_id=?, action_effect=?
                WHERE id=?
                """,
                (
                    scene_id,
                    scene_key,
                    element_type,
                    element_name,
                    text,
                    x1,
                    y1,
                    x2,
                    y2,
                    source,
                    confidence,
                    str(image_path),
                    yolo_class_id,
                    action_effect,
                    row_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO ui_element (
                    scene_id, scene_key, element_type, element_name, text,
                    x1, y1, x2, y2, source, confidence, dhash, ahash,
                    image_path, yolo_class_id, action_effect
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    scene_key,
                    element_type,
                    element_name,
                    text,
                    x1,
                    y1,
                    x2,
                    y2,
                    source,
                    confidence,
                    fingerprint.get("dhash", ""),
                    fingerprint.get("ahash", ""),
                    str(image_path),
                    yolo_class_id,
                    action_effect,
                ),
            )
            row_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return row_id

    def list_ui_elements_for_scene(
        self,
        scene_id: Optional[int] = None,
        scene_key: str = "",
    ) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        if scene_id is not None:
            rows = cursor.execute(
                """
                SELECT id, scene_id, scene_key, element_type, element_name, text,
                       x1, y1, x2, y2, source, confidence, image_path,
                       yolo_class_id, action_effect
                FROM ui_element
                WHERE scene_id = ?
                ORDER BY confidence DESC, id DESC
                """,
                (scene_id,),
            ).fetchall()
        else:
            rows = cursor.execute(
                """
                SELECT id, scene_id, scene_key, element_type, element_name, text,
                       x1, y1, x2, y2, source, confidence, image_path,
                       yolo_class_id, action_effect
                FROM ui_element
                WHERE scene_key = ?
                ORDER BY confidence DESC, id DESC
                """,
                (scene_key,),
            ).fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "scene_id": row[1],
                "scene_key": row[2],
                "element_type": row[3],
                "element_name": row[4],
                "text": row[5],
                "bbox_xyxy": [row[6], row[7], row[8], row[9]],
                "source": row[10],
                "confidence": row[11],
                "image_path": row[12],
                "yolo_class_id": row[13],
                "action_effect": row[14],
            }
            for row in rows
        ]

    def upsert_runtime_rule(
        self,
        rule_key: str,
        scene_id: Optional[int],
        scene_key: str,
        element_id: Optional[int],
        element_name: str,
        action_type: str,
        action_effect: str,
        user_intent: str,
        bbox_xyxy: list[int],
        next_scene_id: Optional[int],
        next_scene_key: str,
        source_event: str,
        source: str,
        confidence: float,
    ) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO runtime_rule (
                rule_key, scene_id, scene_key, element_id, element_name,
                action_type, action_effect, user_intent, bbox_json,
                next_scene_id, next_scene_key, source_event, source,
                confidence, updated_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_key) DO UPDATE SET
                scene_id=excluded.scene_id,
                scene_key=excluded.scene_key,
                element_id=excluded.element_id,
                element_name=excluded.element_name,
                action_type=excluded.action_type,
                action_effect=excluded.action_effect,
                user_intent=excluded.user_intent,
                bbox_json=excluded.bbox_json,
                next_scene_id=excluded.next_scene_id,
                next_scene_key=excluded.next_scene_key,
                source_event=excluded.source_event,
                source=excluded.source,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (
                rule_key,
                scene_id,
                scene_key,
                element_id,
                element_name,
                action_type,
                action_effect,
                user_intent,
                json.dumps(bbox_xyxy, ensure_ascii=False),
                next_scene_id,
                next_scene_key,
                source_event,
                source,
                confidence,
                now,
                now,
            ),
        )
        row = cursor.execute("SELECT id FROM runtime_rule WHERE rule_key = ?", (rule_key,)).fetchone()
        conn.commit()
        conn.close()
        return int(row[0]) if row else int(cursor.lastrowid)

    def list_runtime_rules_for_scene(
        self,
        scene_id: Optional[int] = None,
        scene_key: str = "",
    ) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        if scene_id is not None:
            rows = cursor.execute(
                """
                SELECT id, rule_key, scene_id, scene_key, element_id, element_name,
                       action_type, action_effect, user_intent, bbox_json,
                       next_scene_id, next_scene_key, source_event, source,
                       confidence, hits, enabled
                FROM runtime_rule
                WHERE scene_id = ?
                ORDER BY confidence DESC, hits DESC, updated_at DESC
                """,
                (scene_id,),
            ).fetchall()
        else:
            rows = cursor.execute(
                """
                SELECT id, rule_key, scene_id, scene_key, element_id, element_name,
                       action_type, action_effect, user_intent, bbox_json,
                       next_scene_id, next_scene_key, source_event, source,
                       confidence, hits, enabled
                FROM runtime_rule
                WHERE scene_key = ?
                ORDER BY confidence DESC, hits DESC, updated_at DESC
                """,
                (scene_key,),
            ).fetchall()
        conn.close()
        results = []
        for row in rows:
            try:
                bbox = json.loads(row[9] or "[]")
            except Exception:
                bbox = []
            results.append({
                "id": row[0],
                "rule_key": row[1],
                "scene_id": row[2],
                "scene_key": row[3],
                "element_id": row[4],
                "element_name": row[5],
                "action_type": row[6],
                "action_effect": row[7],
                "user_intent": row[8],
                "bbox_xyxy": bbox,
                "next_scene_id": row[10],
                "next_scene_key": row[11],
                "source_event": row[12],
                "source": row[13],
                "confidence": row[14],
                "hits": row[15],
                "enabled": bool(row[16]),
            })
        return results

    def list_all_runtime_rules(
        self,
        search: str = "",
        filter_enabled: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """列出所有 runtime_rule，支持搜索和启用状态过滤。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        params = []
        where_clauses = []
        if search:
            where_clauses.append(
                "(rule_key LIKE ? OR scene_key LIKE ? OR element_name LIKE ? OR action_type LIKE ? OR action_effect LIKE ? OR user_intent LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like, like])
        if filter_enabled is not None:
            where_clauses.append("enabled = ?")
            params.append(1 if filter_enabled else 0)
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        rows = cursor.execute(
            f"""
            SELECT id, rule_key, scene_id, scene_key, element_id, element_name,
                   action_type, action_effect, user_intent, bbox_json,
                   next_scene_id, next_scene_key, source_event, source,
                   confidence, hits, enabled, updated_at, created_at
            FROM runtime_rule
            {where_sql}
            ORDER BY updated_at DESC
            """,
            params,
        ).fetchall()
        conn.close()
        results = []
        for row in rows:
            try:
                bbox = json.loads(row[9] or "[]")
            except Exception:
                bbox = []
            results.append({
                "id": row[0],
                "rule_key": row[1],
                "scene_id": row[2],
                "scene_key": row[3],
                "element_id": row[4],
                "element_name": row[5],
                "action_type": row[6],
                "action_effect": row[7],
                "user_intent": row[8],
                "bbox_xyxy": bbox,
                "next_scene_id": row[10],
                "next_scene_key": row[11],
                "source_event": row[12],
                "source": row[13],
                "confidence": row[14],
                "hits": row[15],
                "enabled": bool(row[16]),
                "updated_at": row[17],
                "created_at": row[18],
            })
        return results

    def get_runtime_rule(self, rule_id: int) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT id, rule_key, scene_id, scene_key, element_id, element_name,
                   action_type, action_effect, user_intent, bbox_json,
                   next_scene_id, next_scene_key, source_event, source,
                   confidence, hits, enabled
            FROM runtime_rule
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        try:
            bbox = json.loads(row[9] or "[]")
        except Exception:
            bbox = []
        return {
            "id": row[0],
            "rule_key": row[1],
            "scene_id": row[2],
            "scene_key": row[3],
            "element_id": row[4],
            "element_name": row[5],
            "action_type": row[6],
            "action_effect": row[7],
            "user_intent": row[8],
            "bbox_xyxy": bbox,
            "next_scene_id": row[10],
            "next_scene_key": row[11],
            "source_event": row[12],
            "source": row[13],
            "confidence": row[14],
            "hits": row[15],
            "enabled": bool(row[16]),
        }

    def update_runtime_rule(
        self,
        rule_id: int,
        element_name: Optional[str] = None,
        action_type: Optional[str] = None,
        action_effect: Optional[str] = None,
        user_intent: Optional[str] = None,
        bbox_xyxy: Optional[list] = None,
        next_scene_key: Optional[str] = None,
        confidence: Optional[float] = None,
        enabled: Optional[bool] = None,
    ) -> bool:
        """更新 runtime_rule 的指定字段。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        fields = []
        params = []
        if element_name is not None:
            fields.append("element_name = ?")
            params.append(element_name)
        if action_type is not None:
            fields.append("action_type = ?")
            params.append(action_type)
        if action_effect is not None:
            fields.append("action_effect = ?")
            params.append(action_effect)
        if user_intent is not None:
            fields.append("user_intent = ?")
            params.append(user_intent)
        if bbox_xyxy is not None:
            fields.append("bbox_json = ?")
            params.append(json.dumps(bbox_xyxy, ensure_ascii=False))
        if next_scene_key is not None:
            fields.append("next_scene_key = ?")
            params.append(next_scene_key)
        if confidence is not None:
            fields.append("confidence = ?")
            params.append(confidence)
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not fields:
            conn.close()
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        fields.append("updated_at = ?")
        params.append(now)
        params.append(rule_id)
        cursor.execute(
            f"UPDATE runtime_rule SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()
        return True

    def delete_runtime_rule(self, rule_id: int) -> bool:
        """删除 runtime_rule。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM runtime_rule WHERE id = ?", (rule_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def toggle_runtime_rule_enabled(self, rule_id: int, enabled: bool) -> bool:
        return self.update_runtime_rule(rule_id, enabled=enabled)

    def get_runtime_rule_stats(self) -> Dict[str, Any]:
        """返回规则统计信息。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        total = cursor.execute("SELECT COUNT(*) FROM runtime_rule").fetchone()[0]
        enabled = cursor.execute("SELECT COUNT(*) FROM runtime_rule WHERE enabled = 1").fetchone()[0]
        disabled = cursor.execute("SELECT COUNT(*) FROM runtime_rule WHERE enabled = 0").fetchone()[0]
        total_hits = cursor.execute("SELECT COALESCE(SUM(hits), 0) FROM runtime_rule").fetchone()[0]
        conn.close()
        return {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
            "total_hits": total_hits,
        }

    def list_runtime_rules_top_hits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """返回命中次数最高的规则列表。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT rule_key, scene_key, element_name, action_type, hits, enabled, confidence
            FROM runtime_rule
            ORDER BY hits DESC, confidence DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {
                "rule_key": row[0],
                "scene_key": row[1],
                "element_name": row[2],
                "action_type": row[3],
                "hits": row[4],
                "enabled": bool(row[5]),
                "confidence": row[6],
            }
            for row in rows
        ]

    def get_video_path(self) -> Optional[Path]:
        if self.current_session_id:
            return self.game_dir / "raw_videos" / f"{self.current_session_id}.mp4"
        return None

    def list_actions(self) -> List[Dict[str, Any]]:
        """返回所有 action 记录（场景转移图数据）。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT id, from_scene_id, to_scene_id, action_name, x, y,
                   success_count, fail_count
            FROM action
            ORDER BY success_count DESC, id DESC
            """
        ).fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "from_scene_id": row[1],
                "to_scene_id": row[2],
                "action_name": row[3],
                "x": row[4],
                "y": row[5],
                "success_count": row[6],
                "fail_count": row[7],
            }
            for row in rows
        ]

    def get_action_stats(self) -> Dict[str, Any]:
        """返回 action 统计。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        total = cursor.execute("SELECT COUNT(*) FROM action").fetchone()[0]
        total_success = cursor.execute("SELECT COALESCE(SUM(success_count), 0) FROM action").fetchone()[0]
        total_fail = cursor.execute("SELECT COALESCE(SUM(fail_count), 0) FROM action").fetchone()[0]
        conn.close()
        return {
            "total_actions": total,
            "total_success": total_success,
            "total_fail": total_fail,
            "success_rate": round(total_success / max(1, total_success + total_fail), 4),
        }

    def get_data_quality_stats(self) -> Dict[str, Any]:
        """返回数据质量综合统计。"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # 事件统计
        total_events = cursor.execute("SELECT COUNT(*) FROM click_event").fetchone()[0]
        events_with_scene = cursor.execute(
            "SELECT COUNT(*) FROM click_event WHERE before_scene_id IS NOT NULL"
        ).fetchone()[0]

        # UI 元素统计
        total_elements = cursor.execute("SELECT COUNT(*) FROM ui_element").fetchone()[0]
        source_dist = cursor.execute(
            "SELECT source, COUNT(*) FROM ui_element GROUP BY source"
        ).fetchall()

        # 场景统计
        total_scenes = cursor.execute("SELECT COUNT(*) FROM scene").fetchone()[0]

        # 规则统计
        total_rules = cursor.execute("SELECT COUNT(*) FROM runtime_rule").fetchone()[0]
        enabled_rules = cursor.execute(
            "SELECT COUNT(*) FROM runtime_rule WHERE enabled = 1"
        ).fetchone()[0]
        total_hits = cursor.execute(
            "SELECT COALESCE(SUM(hits), 0) FROM runtime_rule"
        ).fetchone()[0]

        # Action 统计
        total_actions = cursor.execute("SELECT COUNT(*) FROM action").fetchone()[0]
        total_success = cursor.execute(
            "SELECT COALESCE(SUM(success_count), 0) FROM action"
        ).fetchone()[0]
        total_fail = cursor.execute(
            "SELECT COALESCE(SUM(fail_count), 0) FROM action"
        ).fetchone()[0]

        conn.close()
        return {
            "events": {
                "total": total_events,
                "with_scene": events_with_scene,
                "scene_coverage": round(events_with_scene / max(1, total_events), 4),
            },
            "elements": {
                "total": total_elements,
                "source_distribution": {row[0] or "unknown": row[1] for row in source_dist},
            },
            "scenes": {"total": total_scenes},
            "rules": {
                "total": total_rules,
                "enabled": enabled_rules,
                "disabled": total_rules - enabled_rules,
                "total_hits": total_hits,
            },
            "actions": {
                "total": total_actions,
                "success": total_success,
                "fail": total_fail,
                "success_rate": round(total_success / max(1, total_success + total_fail), 4),
            },
        }
