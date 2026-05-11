"""StatsRepository Mixin for AgentDataManager."""
from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from log_manager import LogManager


class StatsRepository:
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

