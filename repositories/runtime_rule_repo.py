"""RuntimeRuleRepository Mixin for AgentDataManager."""
from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from log_manager import LogManager


class RuntimeRuleRepository:
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

