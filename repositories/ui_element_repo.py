"""UiElementRepository Mixin for AgentDataManager."""
from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from log_manager import LogManager


class UiElementRepository:
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

