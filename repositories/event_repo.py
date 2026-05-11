"""EventRepository Mixin for AgentDataManager."""
from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from log_manager import LogManager


class EventRepository:
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

