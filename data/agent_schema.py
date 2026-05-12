from __future__ import annotations

import sqlite3
from pathlib import Path


def init_game_dirs(game_dir: Path) -> None:
    for sub in [
        "raw_videos",
        "sessions",
        "scenes",
        "labels",
        "crops",
        "yolo_events/images/train",
        "yolo_events/labels/train",
    ]:
        (game_dir / sub).mkdir(parents=True, exist_ok=True)


def init_agent_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
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


def hash_confidence(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    try:
        distance = (int(left, 16) ^ int(right, 16)).bit_count()
        return round(max(0.0, 1.0 - distance / 64), 6)
    except Exception:
        return 0.0
