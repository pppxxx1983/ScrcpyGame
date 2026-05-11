"""Historical Batch Migration Tool (TODO #26).
Migrate old-format events/scenes to the current agent.db schema.
"""
from __future__ import annotations

import json
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from log_manager import LogManager


@dataclass
class MigrationReport:
    migrated_events: int = 0
    migrated_scenes: int = 0
    migrated_actions: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


class HistoricalMigrationTool:
    """Migrate legacy data formats into the current SQLite schema."""

    def __init__(self, db_path: Path, backup: bool = True):
        self.db_path = db_path
        self.backup = backup
        self.report = MigrationReport()

    def _ensure_backup(self):
        if self.backup and self.db_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.db_path.with_suffix(f".db.backup.{ts}")
            shutil.copy2(str(self.db_path), str(backup_path))
            LogManager().append(f"[Migration] backup created: {backup_path}")

    def migrate_from_legacy_jsonl(self, jsonl_path: Path) -> MigrationReport:
        """Migrate old operations.jsonl format into physical_event / click_event tables."""
        self._ensure_backup()
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Ensure tables exist
        self._ensure_schema(cur)

        if not jsonl_path.exists():
            self.report.errors.append(f"JSONL not found: {jsonl_path}")
            return self.report

        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception as e:
                    self.report.skipped += 1
                    self.report.errors.append(f"JSON parse error: {e}")
                    continue
                self._migrate_one_event(cur, data)

        conn.commit()
        conn.close()
        LogManager().append(
            f"[Migration] Done: events={self.report.migrated_events}, "
            f"scenes={self.report.migrated_scenes}, actions={self.report.migrated_actions}, "
            f"skipped={self.report.skipped}, errors={len(self.report.errors)}"
        )
        return self.report

    def migrate_legacy_scenes_folder(self, scenes_dir: Path) -> MigrationReport:
        """Migrate old scene image folders into scene_sample / scene_hash tables."""
        self._ensure_backup()
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        self._ensure_schema(cur)

        if not scenes_dir.exists():
            self.report.errors.append(f"Scenes dir not found: {scenes_dir}")
            return self.report

        for folder in scenes_dir.iterdir():
            if not folder.is_dir():
                continue
            scene_key = folder.name
            # Check if scene exists
            cur.execute("SELECT id FROM scene WHERE name = ?", (scene_key,))
            row = cur.fetchone()
            if row:
                scene_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO scene (name, description) VALUES (?, ?)",
                    (scene_key, f"Migrated from {folder}"),
                )
                scene_id = cur.lastrowid
                self.report.migrated_scenes += 1

            for img_file in folder.glob("*.png"):
                try:
                    from PIL import Image
                    from scene_index import image_fingerprint

                    fp = image_fingerprint(img_file)
                    cur.execute(
                        "INSERT INTO scene_sample (scene_id, image_path, width, height) VALUES (?, ?, ?, ?)",
                        (scene_id, str(img_file), fp["width"], fp["height"]),
                    )
                    sample_id = cur.lastrowid
                    cur.execute(
                        "INSERT INTO scene_hash (sample_id, region_name, phash, dhash, ahash, weight) VALUES (?, ?, ?, ?, ?, ?)",
                        (sample_id, "full", "", fp["dhash"], fp["ahash"], 1.0),
                    )
                except Exception as e:
                    self.report.errors.append(f"Scene image failed {img_file}: {e}")

        conn.commit()
        conn.close()
        LogManager().append(f"[Migration] Scenes migrated: {self.report.migrated_scenes}")
        return self.report

    def _ensure_schema(self, cur: sqlite3.Cursor):
        """Create tables if they don't exist (safe for old DBs)."""
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT,
                game_name TEXT,
                video_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scene (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS scene_sample (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER,
                image_path TEXT,
                width INTEGER,
                height INTEGER
            );
            CREATE TABLE IF NOT EXISTS scene_hash (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER,
                region_name TEXT,
                phash TEXT,
                dhash TEXT,
                ahash TEXT,
                weight REAL
            );
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
            );
            CREATE TABLE IF NOT EXISTS physical_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT,
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
                yolo_image TEXT,
                yolo_label TEXT
            );
            CREATE TABLE IF NOT EXISTS action (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_scene_id INTEGER,
                to_scene_id INTEGER,
                action_name TEXT,
                x INTEGER,
                y INTEGER,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ui_element (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER,
                scene_key TEXT,
                element_type TEXT,
                element_name TEXT,
                text TEXT,
                x1 INTEGER,
                y1 INTEGER,
                x2 INTEGER,
                y2 INTEGER,
                source TEXT,
                confidence REAL,
                dhash TEXT,
                ahash TEXT,
                image_path TEXT,
                yolo_class_id INTEGER,
                action_effect TEXT
            );
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
                enabled INTEGER DEFAULT 1
            );
            """
        )

    def _migrate_one_event(self, cur: sqlite3.Cursor, data: dict):
        action_type = data.get("action_type", "tap")
        ts = data.get("timestamp_ms") or int(datetime.now().timestamp() * 1000)
        touch = data.get("touch", {})
        start = touch.get("frame_start", {})
        end = touch.get("frame_end", start)
        x = int(start.get("x", 0))
        y = int(start.get("y", 0))
        folder = data.get("folder_path", "")
        images = data.get("images", {})

        try:
            cur.execute(
                """
                INSERT INTO physical_event (
                    event_key, action_type, timestamp_ms, duration_ms,
                    frame_start_x, frame_start_y, frame_end_x, frame_end_y,
                    folder_path, before_image, pressed_image, after_image
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("event_key", ""),
                    action_type,
                    ts,
                    data.get("duration_ms", 0),
                    x, y,
                    int(end.get("x", x)), int(end.get("y", y)),
                    str(folder),
                    images.get("before", ""),
                    images.get("pressed", ""),
                    images.get("after", ""),
                ),
            )
            self.report.migrated_events += 1
        except Exception as e:
            self.report.errors.append(f"Insert event failed: {e}")
            self.report.skipped += 1


def run_cli_migration(agent_db: Path, jsonl: Path | None = None, scenes_dir: Path | None = None):
    """CLI entry point for migration."""
    tool = HistoricalMigrationTool(agent_db, backup=True)
    if jsonl:
        tool.migrate_from_legacy_jsonl(jsonl)
    if scenes_dir:
        tool.migrate_legacy_scenes_folder(scenes_dir)
    return tool.report
