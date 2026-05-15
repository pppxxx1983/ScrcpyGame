"""
Unit tests for event_store module.
"""
import pytest
import json
import tempfile
from pathlib import Path
from data.event_store import build_recording_event, append_jsonl


class TestEventStore:
    """Test cases for event_store functions."""

    def test_build_recording_event_basic(self):
        """Test basic event construction."""
        op_dir = Path("screenshots/op_123")
        data = {
            "action_type": "click",
            "duration_ms": 150,
            "touch": {"x": 100, "y": 200},
        }
        recording_context = {
            "kind": "session",
            "video_offset_ms": 5000,
            "video_path": "/path/to/video.mp4",
            "session_id": "sess_001",
        }

        event = build_recording_event(op_dir, data, recording_context)

        assert event["event_key"] == "op_123"
        assert event["folder_path"] == str(op_dir)
        assert event["action_type"] == "click"
        assert event["duration_ms"] == 150
        assert event["touch"] == {"x": 100, "y": 200}
        assert event["recording_kind"] == "session"
        assert event["video_offset_ms"] == 5000

    def test_build_recording_event_empty_op_dir(self):
        """Test event construction with empty op_dir."""
        data = {}
        recording_context = {"kind": "test"}

        event = build_recording_event(Path(""), data, recording_context)

        assert event["event_key"] == ""
        assert event["folder_path"] in ("", ".")

    def test_append_jsonl(self):
        """Test JSONL file append operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "events.jsonl"

            row1 = {"id": 1, "type": "click"}
            append_jsonl(jsonl_path, row1)

            row2 = {"id": 2, "type": "swipe"}
            append_jsonl(jsonl_path, row2)

            assert jsonl_path.exists()

            with open(jsonl_path, encoding="utf-8") as f:
                lines = f.readlines()

            assert len(lines) == 2
            assert json.loads(lines[0]) == row1
            assert json.loads(lines[1]) == row2

    def test_append_jsonl_creates_parent_dir(self):
        """Test that append_jsonl creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "subdir" / "nested" / "events.jsonl"

            assert not jsonl_path.parent.exists()
            append_jsonl(jsonl_path, {"test": True})
            assert jsonl_path.parent.exists()

    def test_append_jsonl_unicode(self):
        """Test JSONL with unicode characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "unicode.jsonl"

            row = {"text": "中文测试 🎮 🎯", "emoji": "🔴"}
            append_jsonl(jsonl_path, row)

            with open(jsonl_path, encoding="utf-8") as f:
                loaded = json.loads(f.readline())

            assert loaded["text"] == row["text"]
            assert loaded["emoji"] == row["emoji"]
